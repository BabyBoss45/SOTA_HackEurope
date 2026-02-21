"""
SOTAAgent -- the main class third-party devs subclass.

    class MyAgent(SOTAAgent):
        name = "my-agent"
        description = "Does cool stuff"
        tags = ["cool_stuff"]

        def setup(self):
            self.llm = SomeLLMClient()

        async def execute(self, job: Job) -> dict:
            return {"answer": self.llm.ask(job.description)}

    if __name__ == "__main__":
        MyAgent.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

import uvicorn

from .config import SOTA_MARKETPLACE_URL, SOTA_AGENT_PRIVATE_KEY
from .models import Job, Bid, JobResult
from .marketplace.client import MarketplaceClient
from .marketplace.registration import build_register_message
from .marketplace.bidding import BidStrategy, DefaultBidStrategy
from .server import create_app

logger = logging.getLogger(__name__)

# Max seconds to wait for active jobs during shutdown
_SHUTDOWN_TIMEOUT = int(os.getenv("SOTA_SHUTDOWN_TIMEOUT", "30"))

# Default execute() timeout when no deadline is set (seconds)
_DEFAULT_EXECUTE_TIMEOUT = int(os.getenv("SOTA_EXECUTE_TIMEOUT", "600"))

# Maximum number of jobs an agent will execute concurrently
_MAX_CONCURRENT_JOBS = int(os.getenv("SOTA_MAX_CONCURRENT_JOBS", "5"))


class SOTAAgent:
    """
    Base class for all SOTA marketplace agents.

    Developers subclass this, set class-level attributes, override
    ``setup()`` and ``execute()``, then call ``MyAgent.run()``.
    """

    # -- Developer sets these on the subclass ----------------------------------
    name: str = "unnamed-agent"
    description: str = ""
    tags: list[str] = []
    version: str = "1.0.0"
    bid_strategy: BidStrategy | None = None  # None → DefaultBidStrategy created per-instance

    # -- Internal state (populated by run()) -----------------------------------

    def __init__(self):
        # Defensive copy of mutable class attrs so subclass lists are not shared
        self.tags = list(self.__class__.tags)
        if self.bid_strategy is None:
            self.bid_strategy = DefaultBidStrategy()
        else:
            import copy
            self.bid_strategy = copy.copy(self.__class__.bid_strategy)

        self._wallet = None                          # Optional[AgentWallet]
        self._ws_client: Optional[MarketplaceClient] = None
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._job_cache: Dict[str, Job] = {}         # jobs seen in job_available
        self._shutdown_event = None                  # created in _boot() when loop is running
        self._reserved_jobs: set = set()             # H1: guard against duplicate bid_accepted

    # -- Lifecycle hooks (developer overrides) ---------------------------------

    async def setup(self) -> None:
        """
        Called once before the agent starts listening for jobs.
        Override to initialise LLM clients, API keys, etc.
        """

    async def execute(self, job: Job) -> dict:
        """
        Execute a job. **Must be overridden.**

        Args:
            job: The Job to execute.

        Returns:
            A dict with at least ``{"success": True/False}``.
            Add any result data you want delivered.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.execute() must be implemented"
        )

    async def evaluate(self, job: Job) -> Optional[Bid]:
        """
        Custom bid evaluation. Override to replace the pluggable bid_strategy.

        Return a Bid to bid, or None to skip.
        By default delegates to ``self.bid_strategy.evaluate(job)``.
        """
        return await self.bid_strategy.evaluate(job)

    # -- Entry point -----------------------------------------------------------

    @classmethod
    def run(
        cls,
        port: int | None = None,
        host: str | None = None,
    ) -> None:
        """
        Single entry point -- boots everything:

        1. Instantiate agent
        2. Call setup()
        3. Start FastAPI server (health endpoint)
        4. Initialize wallet from SOTA_AGENT_PRIVATE_KEY
        5. Connect WebSocket to SOTA_MARKETPLACE_URL
        6. Send register message with {name, tags, version, wallet_address}
        7. Listen for job_available messages
        8. On job_available -> call evaluate() or bid_strategy.evaluate()
        9. Send bid to hub
        10. On bid_accepted -> call execute(job) in async task
        11. After execute() returns:
            a. Hash result -> delivery proof
            b. submit_delivery_proof(job_id, proof_hash) on-chain
            c. Send job_completed to hub
            d. (payment claim happens after delivery confirmation)
        """
        resolved_host = host or os.getenv("SOTA_AGENT_HOST", "127.0.0.1")
        resolved_port = port or int(os.getenv("SOTA_AGENT_PORT", "8000"))

        agent = cls()
        try:
            asyncio.run(agent._boot(resolved_host, resolved_port))
        except KeyboardInterrupt:
            pass  # Clean exit on Ctrl+C (especially on Windows)

    # -- Internal boot sequence ------------------------------------------------

    async def _boot(self, host: str, port: int) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        )

        # C1: Create Event inside running loop (not in __init__)
        self._shutdown_event = asyncio.Event()

        logger.info("Booting %s v%s ...", self.name, self.version)

        # 0 -- Paid.ai cost tracking (before setup so dev LLM clients get instrumented)
        from . import cost as _cost
        _cost.initialize_cost_tracking()

        # 1 -- setup() (H5: supports both sync and async overrides)
        if asyncio.iscoroutinefunction(self.setup):
            await self.setup()
        else:
            logger.warning("Sync setup() is deprecated, use 'async def setup()'")
            await asyncio.get_running_loop().run_in_executor(None, self.setup)
        logger.info("setup() complete")

        # 1.5 -- preflight validation (run in executor to avoid blocking event loop)
        from .preflight import run_preflight
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_preflight, self)
        for w in result.warnings:
            logger.warning("PREFLIGHT: %s", w)
        if not result.ok:
            for e in result.errors:
                logger.error("PREFLIGHT: %s", e)
            raise SystemExit(
                f"Preflight failed with {len(result.errors)} error(s). "
                "Fix the issues above and try again."
            )
        logger.info("Preflight checks passed")

        # 2 -- wallet (optional)
        if SOTA_AGENT_PRIVATE_KEY:
            from .chain.wallet import AgentWallet
            self._wallet = AgentWallet(SOTA_AGENT_PRIVATE_KEY)
            from .server import _mask_address
            logger.info("Wallet initialised: %s", _mask_address(self._wallet.address))
        else:
            logger.warning(
                "SOTA_AGENT_PRIVATE_KEY not set -- running off-chain only"
            )

        # 3 -- inject agent tags into bid strategy
        self.bid_strategy.set_agent_tags(self.tags)

        # 4 -- build FastAPI app
        app = create_app(self)

        # 5 -- register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: self._shutdown_event.set())
            except NotImplementedError:
                pass  # Windows -- handled via KeyboardInterrupt in run()

        # 6 -- start all tasks
        server_task = asyncio.create_task(self._run_server(app, host, port))
        ws_task = asyncio.create_task(self._run_ws())

        logger.info("%s is running (http://%s:%d)", self.name, host, port)

        # Wait for shutdown
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass

        logger.info("Shutting down ...")

        # Cleanup
        if self._ws_client:
            await self._ws_client.disconnect()
        server_task.cancel()
        ws_task.cancel()
        # H3: Await infrastructure tasks so exceptions are not lost
        await asyncio.gather(server_task, ws_task, return_exceptions=True)

        # H4: Cancel active jobs with safe snapshot (avoid dict mutation during iteration)
        tasks = list(self._active_jobs.values())
        for task in tasks:
            task.cancel()
        if tasks:
            logger.info(
                "Waiting for %d active jobs (%ds timeout) ...",
                len(tasks), _SHUTDOWN_TIMEOUT,
            )
            done, pending = await asyncio.wait(tasks, timeout=_SHUTDOWN_TIMEOUT)
            if pending:
                logger.warning(
                    "%d jobs did not finish within shutdown timeout", len(pending)
                )

        logger.info("%s stopped", self.name)

    # -- FastAPI server --------------------------------------------------------

    async def _run_server(self, app, host: str, port: int) -> None:
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        try:
            await server.serve()
        except asyncio.CancelledError:
            server.should_exit = True

    # -- WebSocket loop --------------------------------------------------------

    async def _run_ws(self) -> None:
        wallet_addr = self._wallet.address if self._wallet else ""

        register_msg = build_register_message(
            name=self.name,
            tags=self.tags,
            version=self.version,
            wallet_address=wallet_addr,
        )

        self._ws_client = MarketplaceClient(
            url=SOTA_MARKETPLACE_URL,
            register_payload=register_msg,
        )

        # Wire up handlers
        self._ws_client.on("job_available", self._on_job_available)
        self._ws_client.on("bid_accepted", self._on_bid_accepted)
        self._ws_client.on("bid_rejected", self._on_bid_rejected)
        self._ws_client.on("job_cancelled", self._on_job_cancelled)

        try:
            await self._ws_client.connect()
        except asyncio.CancelledError:
            pass

    # -- Message handlers ------------------------------------------------------

    async def _on_job_available(self, msg: dict) -> None:
        """Hub broadcasts a new job."""
        job_data = msg.get("job", {})

        job_id = job_data.get("id", "")
        if not job_id:
            logger.warning("Received job_available with no job ID, ignoring")
            return

        job = Job(
            id=job_id,
            description=job_data.get("description", ""),
            tags=job_data.get("tags", []),
            budget_usdc=float(job_data.get("budget_usdc", 0)),
            deadline_ts=int(job_data.get("deadline_ts", 0)),
            poster=job_data.get("poster", ""),
            metadata=job_data.get("metadata", {}),
            params=job_data.get("params", job_data.get("metadata", {}).get("parameters", {})),
        )

        logger.info(
            "Job available: %s (%.2f USDC) tags=%s",
            job.id, job.budget_usdc, job.tags,
        )

        # Evaluate
        bid = await self.evaluate(job)
        if bid is None:
            logger.info("Skipping job %s", job.id)
            return

        # C2: Only cache jobs the agent actually bids on
        self._job_cache[job.id] = job
        if len(self._job_cache) > 1000:
            self._job_cache.pop(next(iter(self._job_cache)))

        # Send bid to hub
        bid_msg = {
            "type": "bid",
            "job_id": bid.job_id,
            "amount_usdc": bid.amount_usdc,
            "estimated_seconds": bid.estimated_seconds,
        }
        await self._ws_client.send(bid_msg)
        logger.info(
            "Bid sent | job=%s amount=%.2f eta=%ds",
            bid.job_id, bid.amount_usdc, bid.estimated_seconds,
        )

    async def _on_bid_accepted(self, msg: dict) -> None:
        """Our bid was accepted -- execute the job."""
        job_id = msg.get("job_id", "")
        bid_id = msg.get("bid_id", "")

        if not job_id:
            logger.warning("Received bid_accepted with no job ID, ignoring")
            return

        # H1: Guard against TOCTOU race — reserve before any await
        if job_id in self._reserved_jobs:
            logger.warning("Duplicate bid_accepted for %s (reserved), ignoring", job_id)
            return
        self._reserved_jobs.add(job_id)

        # Guard against duplicate acceptance for the same job
        if job_id in self._active_jobs:
            logger.warning(
                "Duplicate bid_accepted for job %s, ignoring", job_id
            )
            return

        # Guard against unbounded parallelism
        if len(self._active_jobs) >= _MAX_CONCURRENT_JOBS:
            logger.warning(
                "Concurrency limit reached (%d/%d), declining job %s",
                len(self._active_jobs), _MAX_CONCURRENT_JOBS, job_id,
            )
            self._reserved_jobs.discard(job_id)
            self._job_cache.pop(job_id, None)
            await self._send_job_failed(job_id, "agent at concurrency limit")
            return

        logger.info("Bid accepted! job=%s bid=%s", job_id, bid_id)

        # Use cached job data first, then try on-chain, then bare fallback
        job = self._job_cache.pop(job_id, None)
        if job is None:
            job = await self._resolve_job(job_id, msg)

        # Execute in a background task
        task = asyncio.create_task(self._execute_and_deliver(job, bid_id))
        self._active_jobs[job_id] = task

        def _on_job_done(_t):
            self._active_jobs.pop(job_id, None)
            self._reserved_jobs.discard(job_id)

        task.add_done_callback(_on_job_done)

    async def _on_bid_rejected(self, msg: dict) -> None:
        job_id = msg.get("job_id", "")
        self._job_cache.pop(job_id, None)
        self._reserved_jobs.discard(job_id)
        logger.info(
            "Bid rejected | job=%s reason=%s",
            job_id, msg.get("reason", ""),
        )

    async def _on_job_cancelled(self, msg: dict) -> None:
        job_id = msg.get("job_id", "")
        logger.info("Job cancelled: %s", job_id)
        self._job_cache.pop(job_id, None)
        self._reserved_jobs.discard(job_id)
        task = self._active_jobs.pop(job_id, None)
        if task and not task.done():
            task.cancel()

    # -- Execution + delivery --------------------------------------------------

    async def _execute_and_deliver(self, job: Job, bid_id: str) -> None:
        """Run execute(), hash the result, submit proof on-chain, notify hub.

        The entire method body runs inside a ``paid_tracing`` context so that
        all LLM calls made during execute() are attributed to this job's
        customer (poster) and product (agent name).
        """
        logger.info("Executing job %s ...", job.id)

        # Acquire paid_tracing context manager (no-op stub if unavailable)
        tracing_ctx = self._get_paid_tracing_ctx(job)

        async with tracing_ctx:
            await self._do_execute_and_deliver(job, bid_id)

    def _get_paid_tracing_ctx(self, job: Job):
        """Return a paid_tracing async context manager, or a no-op fallback."""
        try:
            from paid.tracing import paid_tracing
            return paid_tracing(
                external_customer_id=job.poster or job.id,
                external_product_id=self.name,
            )
        except ImportError:
            import contextlib
            return contextlib.AsyncExitStack()  # no-op async context manager

    async def _do_execute_and_deliver(self, job: Job, bid_id: str) -> None:
        """Inner execution logic, called inside the paid_tracing context."""
        from . import cost as _cost

        # Compute a reasonable timeout from the job's deadline
        if job.deadline_ts > 0:
            remaining = job.deadline_ts - int(time.time())
            # M3: Reject jobs whose deadline has already passed
            if remaining <= 0:
                await self._send_job_failed(job.id, "Job deadline already passed")
                return
            timeout = max(remaining, 30)  # at least 30s
        else:
            timeout = _DEFAULT_EXECUTE_TIMEOUT

        try:
            result = await asyncio.wait_for(self.execute(job), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("execute() timed out for job %s after %ds", job.id, timeout)
            _cost.send_outcome(
                job_id=job.id, agent_name=self.name,
                revenue_usdc=job.budget_usdc, success=False,
            )
            await self._send_job_failed(job.id, f"execution timed out after {timeout}s")
            return
        except Exception as e:
            logger.exception("execute() failed for job %s", job.id)
            _cost.send_outcome(
                job_id=job.id, agent_name=self.name,
                revenue_usdc=job.budget_usdc, success=False,
            )
            await self._send_job_failed(job.id, f"execution failed: {type(e).__name__}: {e}")
            return

        success = result.get("success", True) if isinstance(result, dict) else True
        result_data = result if isinstance(result, dict) else {"result": result}

        if not success:
            _cost.send_outcome(
                job_id=job.id, agent_name=self.name,
                revenue_usdc=job.budget_usdc, success=False,
            )
            await self._send_job_failed(job.id, result_data.get("error", "unknown"))
            return

        # -- Outcome signal (inside paid_tracing context) ----------------------
        _cost.send_outcome(
            job_id=job.id, agent_name=self.name,
            revenue_usdc=job.budget_usdc, success=True,
        )

        # -- Delivery proof (on-chain, if wallet configured) -------------------
        proof_hash = self._hash_result(result_data)

        if self._wallet:
            try:
                from .chain.contracts import submit_delivery_proof

                if not job.id.isdigit():
                    logger.info(
                        "Skipping on-chain delivery proof for job %s (non-numeric ID)", job.id
                    )
                else:
                    loop = asyncio.get_running_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None, submit_delivery_proof,
                            self._wallet, int(job.id), proof_hash,
                        ),
                        timeout=180,
                    )
                    logger.info(
                        "On-chain delivery proof submitted for job %s", job.id
                    )
            except asyncio.TimeoutError:
                logger.error(
                    "On-chain delivery proof timed out for job %s", job.id
                )
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "On-chain delivery unavailable for job %s: %s", job.id, e
                )
            except Exception:
                logger.exception(
                    "Failed to submit delivery proof on-chain for job %s", job.id
                )

        # -- Notify hub --------------------------------------------------------
        if self._ws_client:
            await self._ws_client.send({
                "type": "job_completed",
                "job_id": job.id,
                "success": True,
                "result": result_data,
            })
            logger.info("Job %s completed and reported to hub", job.id)
        else:
            logger.warning(
                "Job %s completed but WS client is gone — cannot notify hub", job.id
            )

    async def _send_job_failed(self, job_id: str, error: str) -> None:
        if self._ws_client:
            await self._ws_client.send({
                "type": "job_failed",
                "job_id": job_id,
                "error": error,
            })
        logger.error("Job %s failed: %s", job_id, error)

    # -- Helpers ---------------------------------------------------------------

    async def _resolve_job(self, job_id: str, msg: dict) -> Job:
        """
        Try to fetch full job data from on-chain; fall back to
        whatever the hub sent in the bid_accepted message.
        """
        if self._wallet and job_id.isdigit():
            try:
                from .chain.contracts import get_job

                loop = asyncio.get_running_loop()
                on_chain = await loop.run_in_executor(
                    None, get_job, self._wallet, int(job_id),
                )
                return Job(
                    id=str(on_chain["id"]),
                    description=on_chain.get("metadata_uri", ""),
                    tags=[],
                    budget_usdc=on_chain.get("budget_usdc", 0),
                    deadline_ts=on_chain.get("deadline", 0),
                    poster=on_chain.get("poster", ""),
                )
            except (FileNotFoundError, ValueError) as e:
                logger.debug(
                    "On-chain fetch unavailable for job %s: %s", job_id, e
                )
            except Exception as e:
                logger.warning(
                    "Unexpected error fetching job %s on-chain: %s", job_id, e
                )

        # Fallback: minimal Job from hub message
        return Job(
            id=job_id,
            description=msg.get("description", ""),
            tags=msg.get("tags", []),
            budget_usdc=float(msg.get("budget_usdc", 0)),
            deadline_ts=int(msg.get("deadline_ts", 0)),
            poster=msg.get("poster", ""),
            metadata=msg.get("metadata", {}),
        )

    @staticmethod
    def _hash_result(result: dict) -> bytes:
        """SHA-256 hash of the JSON-serialised result (32 bytes)."""
        import hashlib

        raw = json.dumps(
            result, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(raw).digest()
