"""
Auto-Bidder — Mixin that lets worker agents participate in the JobBoard.

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
    JobType.HOTEL_BOOKING:          "hotel_booking",
    JobType.RESTAURANT_BOOKING:     "restaurant_booking",
    JobType.HACKATHON_REGISTRATION: "hackathon_registration",
    JobType.CALL_VERIFICATION:      "call_verification",
    JobType.GENERIC:                "generic",
}


def job_types_to_tags(job_types: list[JobType]) -> List[str]:
    """Convert a list of JobType enums into tag strings for the board."""
    return [JOB_TYPE_TAGS.get(jt, jt.name.lower()) for jt in job_types]


# ── Mixin ────────────────────────────────────────────────────

# Default wallet address for agents without private keys
# This address receives escrow payments when jobs are completed
DEFAULT_AGENT_WALLET = "0xc670ca2A23798BA5ee52dFfcEC86b3E220618225"


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

    def register_on_board(self):
        """Register this agent on the global JobBoard."""
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
        logger.info(
            "🏪 %s registered on JobBoard  tags=%s  addr=%s",
            getattr(self, "agent_name", "Worker"), tags, address[:10] + "…",
        )

    async def _execute_job_for_board(self, job: JobListing, winning_bid: Bid) -> dict:
        """
        Called by JobBoard after this worker wins a bid.
        Executes the job, persists the outcome, and returns results.
        """
        from .base_agent import ActiveJob
        
        agent_name = getattr(self, "agent_name", "Worker")
        agent_type = getattr(self, "agent_type", "worker")
        logger.info("🔄 %s executing job %s", agent_name, job.job_id)
        
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
                        "🧠 Pattern detected for job %s: confidence=%.2f strategy=%s",
                        job.job_id, pattern.confidence, pattern.recommended_strategy,
                    )
                active_job.params["pattern_analysis"] = pattern
            except Exception:
                logger.debug("Pre-exec analysis skipped", exc_info=True)

        start_ms = _time.time() * 1000
        result: dict = {}
        execute_fn = getattr(self, "execute_job", None)
        if execute_fn:
            try:
                result = await execute_fn(active_job)
                logger.info("✅ %s completed job %s", agent_name, job.job_id)
            except Exception as e:
                logger.error("❌ %s failed job %s: %s", agent_name, job.job_id, e)
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
                        "🚫 %s declining job %s — confidence too low (%.2f)",
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
            "🤖 %s bidding %.2f USDC on job %s  (tags matched: %s)",
            getattr(self, "agent_name", "Worker"),
            bid.amount_usdc, job.job_id, list(overlap),
        )
        return bid
