"""
Auto-Bidder -- Mixin that lets worker agents participate in the JobBoard.

Drop this into any BaseArchiveAgent subclass to have it:
1. Register itself with the JobBoard on startup
2. Evaluate incoming jobs against its tags / capabilities
3. Place a competitive bid automatically

Usage inside a worker agent::

    class MyWorkerAgent(AutoBidderMixin, BaseArchiveAgent):
        ...

    # During initialize():
    self.register_on_board()
"""

from __future__ import annotations

import logging
import time as _time
import uuid
from typing import List, Optional

from .job_board import JobBoard, RegisteredWorker, JobListing, Bid
from .config import JobType, JOB_TYPE_LABELS, AGENT_CAPABILITIES

logger = logging.getLogger(__name__)


# ── Tag Mapping ──────────────────────────────────────────────

JOB_TYPE_TAGS: dict[JobType, str] = {
    JobType.HOTEL_BOOKING:            "hotel_booking",
    JobType.RESTAURANT_BOOKING:       "restaurant_booking",
    JobType.HACKATHON_REGISTRATION:   "hackathon_registration",
    JobType.GIFT_SUGGESTION:          "gift_suggestion",
    JobType.CALL_VERIFICATION:        "call_verification",
    JobType.GENERIC:                  "generic",
    JobType.FUN_ACTIVITY:             "fun_activity",
    JobType.REFUND_CLAIM:             "refund_claim",
    JobType.RESTAURANT_BOOKING_SMART: "restaurant_booking_smart",
    JobType.SMART_SHOPPING:           "smart_shopping",
    JobType.TRIP_PLANNING:            "trip_planning",
}


def job_types_to_tags(job_types: list[JobType]) -> List[str]:
    """Convert a list of JobType enums into tag strings for the board."""
    return [JOB_TYPE_TAGS.get(jt, jt.name.lower()) for jt in job_types]


# ── Mixin ────────────────────────────────────────────────────

# Default wallet address for agents without private keys
# Solana base58 address (devnet faucet or placeholder)
DEFAULT_AGENT_WALLET = "11111111111111111111111111111111"


class AutoBidderMixin:
    """
    Mixin for BaseArchiveAgent subclasses.

    Expects the host class to have:
      - ``agent_type: str``
      - ``agent_name: str``
      - ``supported_job_types: list[JobType]``
      - ``max_concurrent_jobs: int``
      - ``active_jobs: dict``
      - ``wallet`` with ``.address``
      - ``min_profit_margin: float``
    """

    # Configurable pricing strategy
    bid_price_ratio: float = 0.80     # bid 80% of the budget by default
    bid_eta_seconds: int = 1800       # default ETA: 30 min

    # Icon mapping for internal agents (Lucide React component names)
    _AGENT_ICON_MAP: dict[str, str] = {
        "hackathon": "Calendar",
        "caller": "Phone",
        "trip_planner": "Map",
        "smart_shopper": "ShoppingCart",
        "restaurant_booker": "UtensilsCrossed",
        "refund_claim": "Receipt",
        "gift_suggestion": "Gift",
        "fun_activity": "PartyPopper",
    }

    async def register_on_board(self, db=None):
        """Register this agent on the global JobBoard and optionally persist to DB."""
        board = JobBoard.instance()

        tags = job_types_to_tags(getattr(self, "supported_job_types", []))
        wallet = getattr(self, "wallet", None)
        address = wallet.address if wallet else DEFAULT_AGENT_WALLET

        worker = RegisteredWorker(
            worker_id=getattr(self, "agent_type", "worker"),
            address=address,
            tags=tags,
            evaluator=self._evaluate_job_for_board,
            executor=self._execute_job_for_board,
            max_concurrent=getattr(self, "max_concurrent_jobs", 5),
            active_jobs=len(getattr(self, "active_jobs", {})),
        )
        board.register_worker(worker)

        # Truncate address for display (base58 is safe to slice)
        addr_display = address[:12] + "..." if len(address) > 12 else address
        logger.info(
            "%s registered on JobBoard  tags=%s  addr=%s",
            getattr(self, "agent_name", "Worker"), tags, addr_display,
        )

        # Persist to WorkerAgent table
        if db:
            agent_type = getattr(self, "agent_type", "worker")
            try:
                await db.upsert_worker_agent(
                    worker_id=agent_type,
                    name=getattr(self, "agent_name", "Worker"),
                    tags=tags,
                    version="1.0.0",
                    wallet_address=address,
                    capabilities=[c.value if hasattr(c, "value") else str(c) for c in getattr(self, "capabilities", [])],
                    status="online",
                    max_concurrent=getattr(self, "max_concurrent_jobs", 5),
                    bid_price_ratio=getattr(self, "bid_price_ratio", 0.80),
                    bid_eta_seconds=getattr(self, "bid_eta_seconds", 1800),
                    min_profit_margin=getattr(self, "min_profit_margin", 0.1),
                    icon=self._AGENT_ICON_MAP.get(agent_type),
                    source="internal",
                )
            except Exception as e:
                logger.warning("Failed to persist agent %s to DB: %s", agent_type, e)

    async def _execute_job_for_board(self, job: JobListing, winning_bid: Bid) -> dict:
        """
        Called by JobBoard after this worker wins a bid.
        Executes the job inside a Paid.ai tracing context so all LLM costs
        are attributed, then sends an outcome signal.
        """
        from .base_agent import ActiveJob

        agent_name = getattr(self, "agent_name", "Worker")
        agent_type = getattr(self, "agent_type", "worker")
        logger.info("%s executing job %s", agent_name, job.job_id)

        active_job = ActiveJob(
            job_id=int(job.job_id) if job.job_id.isdigit() else 0,
            bid_id=0,
            job_type=0,
            description=job.description,
            budget=int(job.budget_usdc * 1e6),
            deadline=job.deadline_ts,
            status="in_progress",
            metadata_uri=job.metadata.get("tool", ""),
            params=job.metadata.get("parameters", {}),
        )

        # Pre-execution: analyze similar past tasks
        task_memory = getattr(self, "task_memory", None)
        if task_memory:
            try:
                pattern = await task_memory.analyze_similar(
                    description=job.description,
                    tags=list(job.tags),
                    agent_id=agent_type,
                )
                if pattern.similar_outcomes:
                    logger.info(
                        "Pattern detected for job %s: confidence=%.2f strategy=%s",
                        job.job_id, pattern.confidence, pattern.recommended_strategy,
                    )
                active_job.params["pattern_analysis"] = pattern
            except Exception:
                logger.debug("Pre-exec analysis skipped", exc_info=True)

        # ── Paid.ai cost-tracked execution ───────────────────────
        # Try to wrap execution in paid_tracing context so LLM costs
        # are attributed to this customer/agent pair in Paid.ai dashboard.
        _paid_tracing = None
        try:
            from sota_sdk.cost import is_tracking_enabled
            if is_tracking_enabled():
                from paid.tracing import paid_tracing as _paid_tracing_cls
                _paid_tracing = _paid_tracing_cls
        except ImportError:
            pass

        poster_address = job.metadata.get("poster", job.job_id)

        # Ensure customer exists in Paid.ai before opening tracing context
        if _paid_tracing:
            try:
                from sota_sdk.cost import ensure_customer
                ensure_customer(str(poster_address))
            except Exception:
                pass

        start_ms = _time.time() * 1000
        result: dict = {}
        success = False
        execute_fn = getattr(self, "execute_job", None)

        if _paid_tracing:
            # Execute inside Paid.ai tracing context
            async with _paid_tracing(
                external_customer_id=str(poster_address),
                external_product_id=agent_type,
            ):
                if execute_fn:
                    try:
                        result = await execute_fn(active_job)
                        success = result.get("success", True) if isinstance(result, dict) else True
                        logger.info("%s completed job %s", agent_name, job.job_id)
                    except Exception as e:
                        logger.error("%s failed job %s: %s", agent_name, job.job_id, e)
                        result = {"error": str(e), "success": False}
                else:
                    result = {"error": "No execute_job method found", "success": False}

                # Send outcome signal to Paid.ai (links all auto-captured LLM costs)
                try:
                    from sota_sdk.cost import send_outcome
                    send_outcome(
                        job_id=str(job.job_id),
                        agent_name=agent_type,
                        revenue_usdc=winning_bid.amount_usdc,
                        success=success,
                        metadata={"elapsed_ms": int(_time.time() * 1000 - start_ms)},
                    )
                    logger.info("Paid.ai outcome sent: job=%s agent=%s revenue=%.2f success=%s",
                                job.job_id, agent_type, winning_bid.amount_usdc, success)
                except Exception as e:
                    logger.warning("Paid.ai send_outcome failed: %s", e)

            # Force-flush spans to ensure delivery to Paid.ai collector
            try:
                from sota_sdk.cost import flush_cost_tracking
                flush_cost_tracking()
            except Exception:
                pass
        else:
            # No Paid.ai — execute without tracing
            if execute_fn:
                try:
                    result = await execute_fn(active_job)
                    success = result.get("success", True) if isinstance(result, dict) else True
                    logger.info("%s completed job %s", agent_name, job.job_id)
                except Exception as e:
                    logger.error("%s failed job %s: %s", agent_name, job.job_id, e)
                    result = {"error": str(e), "success": False}
            else:
                result = {"error": "No execute_job method found", "success": False}

        # Persist structured outcome
        elapsed_ms = int(_time.time() * 1000 - start_ms)
        if task_memory:
            try:
                strategy = "standard"
                pa = active_job.params.get("pattern_analysis")
                if pa:
                    strategy = getattr(pa, "recommended_strategy", "standard")
                await task_memory.persist_outcome(
                    job=active_job, agent_id=agent_type,
                    result=result, elapsed_ms=elapsed_ms,
                    strategy=strategy,
                    pattern_hint=pa,
                )
            except Exception:
                logger.warning("Failed to persist task outcome", exc_info=True)

        return result

    async def _evaluate_job_for_board(self, job: JobListing) -> Optional[Bid]:
        """
        Called by the JobBoard when a new job is broadcast.
        Returns a Bid if this worker wants the job, else None.
        Uses historical pattern analysis to adjust pricing and decline risky jobs.
        """
        my_tags = set(
            t.lower()
            for t in job_types_to_tags(getattr(self, "supported_job_types", []))
        )
        job_tags = set(t.lower() for t in job.tags)

        overlap = my_tags & job_tags
        if not overlap:
            return None

        active = len(getattr(self, "active_jobs", {}))
        max_conc = getattr(self, "max_concurrent_jobs", 5)
        if active >= max_conc:
            logger.debug("%s at capacity (%d/%d), skipping job %s",
                         getattr(self, "agent_type", "?"), active, max_conc, job.job_id)
            return None

        ratio = getattr(self, "bid_price_ratio", 0.80)
        proposed = max(job.budget_usdc * ratio, 0.50)
        eta = getattr(self, "bid_eta_seconds", self.bid_eta_seconds)

        # Adaptive bidding: adjust price/ETA based on historical patterns
        bid_meta: dict = {}
        task_memory = getattr(self, "task_memory", None)
        if task_memory:
            try:
                agent_type = getattr(self, "agent_type", "worker")
                pattern = await task_memory.analyze_similar(
                    description=job.description,
                    tags=list(job.tags),
                    agent_id=agent_type,
                )
                if pattern.recommended_strategy == "decline":
                    logger.info(
                        "%s declining job %s -- confidence too low (%.2f)",
                        getattr(self, "agent_name", "Worker"), job.job_id, pattern.confidence,
                    )
                    return None

                if pattern.confidence < 0.5 and pattern.similar_outcomes:
                    proposed = max(job.budget_usdc * ratio * 1.3, 0.50)
                    eta = int(eta * 1.5)

                if pattern.similar_outcomes:
                    bid_meta["pattern_analysis"] = {
                        "confidence": pattern.confidence,
                        "success_rate": pattern.success_rate,
                        "strategy": pattern.recommended_strategy,
                        "similar_tasks": len(pattern.similar_outcomes),
                    }
            except Exception:
                logger.debug("Adaptive bidding analysis skipped", exc_info=True)

        bid = Bid(
            bid_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
            bidder_id=getattr(self, "agent_type", "worker"),
            bidder_address=getattr(self, "wallet", None) and self.wallet.address or DEFAULT_AGENT_WALLET,
            amount_usdc=round(proposed, 2),
            estimated_seconds=eta,
            tags=list(overlap),
            metadata=bid_meta,
        )

        logger.info(
            "%s bidding %.2f USDC on job %s  (tags matched: %s)",
            getattr(self, "agent_name", "Worker"),
            bid.amount_usdc, job.job_id, list(overlap),
        )
        return bid
