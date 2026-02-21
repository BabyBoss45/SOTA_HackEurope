"""
Job Router — Match job tags to registered agents and push via WebSocket.

Responsibilities:
  1. Receive a new job from the REST endpoint.
  2. Find matching agents in the registry (tag overlap).
  3. Push ``job_available`` to each matching agent over WebSocket.
  4. Kick off the bid window in the BiddingEngine.
  5. When the window closes, notify winner/losers.
  6. Handle completion forwarding back to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from starlette.websockets import WebSocketState

from .models import (
    BidAcceptedMsg,
    BidRejectedMsg,
    JobAvailableMsg,
    JobCancelledMsg,
    JobData,
    JobResultCallback,
    PostJobRequest,
)
from .registry import AgentRegistry, ConnectedAgent
from .bidding import BiddingEngine, BidResult

logger = logging.getLogger(__name__)

# Type for the optional callback when a job completes
CompletionCallback = Callable[[JobResultCallback], Coroutine[Any, Any, None]]


class JobRouter:
    """
    Orchestrates the full lifecycle of a job:
      POST /jobs -> match agents -> broadcast -> collect bids -> notify -> completion
    """

    def __init__(
        self,
        registry: AgentRegistry,
        engine: BiddingEngine,
        on_completion: Optional[CompletionCallback] = None,
    ) -> None:
        self._registry = registry
        self._engine = engine
        self._on_completion = on_completion

    # ── Route a New Job ───────────────────────────────────────

    async def route_job(self, req: PostJobRequest) -> Dict[str, Any]:
        """
        Entry point called by the REST handler.

        1. Build JobData from the request.
        2. Find matching agents.
        3. Push job_available to each.
        4. Open the bid window.
        5. Spawn a background task that waits for the window and notifies.

        Returns a summary dict for the REST response.
        """
        import uuid

        job = JobData(
            id=str(uuid.uuid4()),
            description=req.description,
            tags=[t.lower() for t in req.tags],
            budget_usdc=req.budget_usdc,
            deadline_ts=req.deadline_ts,
            poster=req.poster,
            metadata=req.metadata,
        )

        # Find matching agents
        matching = self._registry.find_by_tags(job.tags)
        logger.info(
            "Job %s: %d matching agent(s) for tags %s",
            job.id, len(matching), job.tags,
        )

        # Open bid window in engine
        self._engine.open_job(job, bid_window_seconds=req.bid_window_seconds)

        # Push job_available to each matching agent
        msg = JobAvailableMsg(job=job)
        await self._broadcast(matching, msg.model_dump())

        # Spawn background task to wait for bids and finalize
        task = asyncio.create_task(self._finalize_job(job.id, matching))
        task.add_done_callback(self._log_task_error)

        return {
            "job_id": job.id,
            "status": "bidding",
            "matched_agents": len(matching),
            "message": (
                f"Job broadcast to {len(matching)} agent(s). "
                f"Bid window: {req.bid_window_seconds}s."
            ),
        }

    # ── Finalization (runs after bid window) ──────────────────

    async def _finalize_job(
        self, job_id: str, candidates: List[ConnectedAgent]
    ) -> None:
        """Wait for the bid window, select winner, notify agents."""
        result: BidResult = await self._engine.wait_and_select(job_id)

        if result.winner:
            # Notify winner
            winner_agent = self._registry.get(result.winner.agent_id)
            if winner_agent:
                accept_msg = BidAcceptedMsg(
                    job_id=job_id, bid_id=result.winner.bid_id,
                )
                await self._send(winner_agent, accept_msg.model_dump())

            # Notify losers
            for bid in result.all_bids:
                if bid.bid_id == result.winner.bid_id:
                    continue
                loser_agent = self._registry.get(bid.agent_id)
                if loser_agent:
                    reject_msg = BidRejectedMsg(
                        job_id=job_id, reason="outbid",
                    )
                    await self._send(loser_agent, reject_msg.model_dump())

            logger.info(
                "Job %s assigned to %s (%.2f USDC)",
                job_id, result.winner.agent_name, result.winner.amount_usdc,
            )
        else:
            logger.warning("Job %s: no winner — %s", job_id, result.reason)

    @staticmethod
    def _log_task_error(task: asyncio.Task) -> None:
        """Log exceptions from fire-and-forget background tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Background job finalization failed: %s", exc, exc_info=exc)

    # ── Completion Handling ───────────────────────────────────

    async def handle_completion(
        self, job_id: str, agent_id: str, success: bool, result: Dict[str, Any]
    ) -> None:
        """Called when an agent sends job_completed."""
        agent = self._registry.get(agent_id)
        agent_name = agent.name if agent else agent_id

        if success:
            self._engine.mark_completed(job_id, result)
        else:
            self._engine.mark_failed(job_id, result.get("error", "unknown"))

        logger.info(
            "Job %s %s by %s",
            job_id, "completed" if success else "failed", agent_name,
        )

        # Forward to Butler via callback
        if self._on_completion:
            callback = JobResultCallback(
                job_id=job_id,
                success=success,
                result=result,
                agent_name=agent_name,
                error=result.get("error") if not success else None,
            )
            try:
                await self._on_completion(callback)
            except Exception as exc:
                logger.error("Completion callback failed for job %s: %s", job_id, exc)

    async def handle_failure(
        self, job_id: str, agent_id: str, error: str
    ) -> None:
        """Called when an agent sends job_failed."""
        await self.handle_completion(
            job_id, agent_id, success=False, result={"error": error}
        )

    # ── WebSocket Helpers ─────────────────────────────────────

    async def _broadcast(
        self, agents: List[ConnectedAgent], payload: Dict[str, Any]
    ) -> None:
        """Send a JSON message to multiple agents, skip disconnected ones."""
        data = json.dumps(payload)
        for agent in agents:
            await self._send(agent, payload, _raw=data)

    async def _send(
        self,
        agent: ConnectedAgent,
        payload: Dict[str, Any],
        _raw: Optional[str] = None,
    ) -> None:
        """Send a JSON message to a single agent."""
        try:
            if agent.ws.client_state == WebSocketState.CONNECTED:
                await agent.ws.send_text(_raw or json.dumps(payload))
        except Exception as exc:
            logger.warning(
                "Failed to send to agent %s: %s", agent.agent_id, exc,
            )
