"""
Hub Connector -- WebSocket client for the SOTA Marketplace Hub.

Allows agents running in separate containers/services to connect to the
central Hub, register themselves, receive job broadcasts, bid, and report
results -- all over a single persistent WebSocket.

Usage in an agent's server.py lifespan::

    from ..shared.hub_connector import HubConnector

    connector = HubConnector(
        agent=agent,                     # BaseArchiveAgent instance
        hub_url="ws://butler-api:3001/hub/ws/agent",
    )
    task = asyncio.create_task(connector.run())
    yield
    connector.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Env var for the Hub WebSocket URL
_DEFAULT_HUB_URL = "ws://localhost:3001/hub/ws/agent"

# Reconnect timing
_INITIAL_BACKOFF = 2      # seconds
_MAX_BACKOFF = 60          # seconds
_HEARTBEAT_INTERVAL = 30   # seconds


class HubConnector:
    """
    Persistent WebSocket client that connects an agent to the Marketplace Hub.

    Parameters
    ----------
    agent : BaseArchiveAgent
        The agent instance. Must have:
        - agent_type (str)
        - agent_name (str)
        - supported_job_types (list)
        - wallet (.address str)
        - execute_job(ActiveJob) -> dict  (async)
        - active_jobs (dict)
        - max_concurrent_jobs (int)
    hub_url : str | None
        WebSocket URL. Falls back to SOTA_HUB_URL env var.
    """

    def __init__(self, agent: Any, hub_url: str | None = None):
        self._agent = agent
        self._hub_url = hub_url or os.getenv("SOTA_HUB_URL", _DEFAULT_HUB_URL)
        self._ws = None
        self._running = False
        self._agent_id: str | None = None
        self._active_hub_jobs: dict[str, asyncio.Task] = {}
        self._job_cache: dict[str, dict] = {}  # job_id -> job data from job_available

    # -- Public API -----------------------------------------------------------

    async def run(self) -> None:
        """Connect to the Hub with auto-reconnect. Call as a background task."""
        self._running = True
        backoff = _INITIAL_BACKOFF

        while self._running:
            try:
                await self._connect_and_listen()
                backoff = _INITIAL_BACKOFF  # reset on clean disconnect
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Hub connection lost (%s), reconnecting in %ds...",
                    exc, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

        logger.info("HubConnector stopped")

    def stop(self) -> None:
        """Signal the connector to stop."""
        self._running = False
        for task in list(self._active_hub_jobs.values()):
            task.cancel()

    # -- Connection lifecycle -------------------------------------------------

    async def _connect_and_listen(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.error(
                "websockets package not installed. "
                "Add 'websockets>=12.0' to requirements.txt."
            )
            self._running = False
            return

        agent_name = getattr(self._agent, "agent_name",
                             getattr(self._agent, "agent_type", "unknown"))

        # Build tags from supported_job_types
        from .auto_bidder import job_types_to_tags
        tags = job_types_to_tags(
            getattr(self._agent, "supported_job_types", [])
        )

        wallet = getattr(self._agent, "wallet", None)
        wallet_address = wallet.address if wallet else "11111111111111111111111111111111"

        logger.info(
            "Connecting to Hub at %s as '%s' tags=%s",
            self._hub_url, agent_name, tags,
        )

        async with websockets.connect(
            self._hub_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            self._ws = ws

            # 1. Send register message
            register_msg = {
                "type": "register",
                "agent": {
                    "name": agent_name,
                    "tags": tags,
                    "version": "1.0.0",
                    "wallet_address": wallet_address,
                    "capabilities": tags,
                },
            }
            await ws.send(json.dumps(register_msg))

            # 2. Wait for registration ack
            ack_raw = await ws.recv()
            ack = json.loads(ack_raw)
            if ack.get("type") == "registered":
                self._agent_id = ack.get("agent_id", "")
                logger.info(
                    "Registered on Hub as '%s' (id=%s)",
                    agent_name, self._agent_id,
                )
            elif "error" in ack:
                logger.error("Hub registration failed: %s", ack["error"])
                return

            # 3. Start heartbeat + message loop
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                await self._message_loop(ws)
            finally:
                heartbeat_task.cancel()
                self._ws = None

    async def _heartbeat_loop(self, ws) -> None:
        """Send periodic heartbeats to keep the connection alive."""
        try:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                await ws.send(json.dumps({"type": "heartbeat"}))
        except (asyncio.CancelledError, Exception):
            pass

    async def _message_loop(self, ws) -> None:
        """Listen for messages from the Hub."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Malformed message from Hub, skipping")
                continue

            msg_type = msg.get("type")

            if msg_type == "job_available":
                asyncio.create_task(self._on_job_available(msg))
            elif msg_type == "bid_accepted":
                asyncio.create_task(self._on_bid_accepted(msg))
            elif msg_type == "bid_rejected":
                self._on_bid_rejected(msg)
            elif msg_type == "job_cancelled":
                self._on_job_cancelled(msg)
            else:
                logger.debug("Unhandled Hub message type: %s", msg_type)

    # -- Message handlers -----------------------------------------------------

    async def _on_job_available(self, msg: dict) -> None:
        """Evaluate a job broadcast from the Hub and optionally bid."""
        job_data = msg.get("job", {})
        job_id = job_data.get("id", "")
        if not job_id:
            return

        agent_name = getattr(self._agent, "agent_name",
                             getattr(self._agent, "agent_type", "unknown"))

        # Check capacity
        active = len(getattr(self._agent, "active_jobs", {}))
        active += len(self._active_hub_jobs)
        max_conc = getattr(self._agent, "max_concurrent_jobs", 5)
        if active >= max_conc:
            logger.debug("%s at capacity, skipping job %s", agent_name, job_id)
            return

        # Check tag overlap
        from .auto_bidder import job_types_to_tags
        my_tags = set(
            t.lower()
            for t in job_types_to_tags(
                getattr(self._agent, "supported_job_types", [])
            )
        )
        job_tags = set(t.lower() for t in job_data.get("tags", []))
        overlap = my_tags & job_tags
        if not overlap:
            return

        # Calculate bid price
        budget = job_data.get("budget_usdc", 0)
        ratio = getattr(self._agent, "bid_price_ratio", 0.80)
        proposed = max(budget * ratio, 0.50)
        eta = getattr(self._agent, "bid_eta_seconds", 1800)

        logger.info(
            "%s bidding %.2f USDC on hub job %s (tags: %s)",
            agent_name, proposed, job_id, list(overlap),
        )

        # Cache job data for when bid_accepted arrives (it only has job_id)
        self._job_cache[job_id] = job_data

        # Send bid
        bid_msg = {
            "type": "bid",
            "job_id": job_id,
            "amount_usdc": round(proposed, 2),
            "estimated_seconds": eta,
        }
        if self._ws:
            await self._ws.send(json.dumps(bid_msg))

    async def _on_bid_accepted(self, msg: dict) -> None:
        """Our bid was accepted -- execute the job."""
        job_id = msg.get("job_id", "")
        if not job_id or job_id in self._active_hub_jobs:
            return

        agent_name = getattr(self._agent, "agent_name",
                             getattr(self._agent, "agent_type", "unknown"))
        logger.info("%s bid accepted for hub job %s", agent_name, job_id)

        # Retrieve cached job data from job_available broadcast
        cached_job = self._job_cache.pop(job_id, {})

        task = asyncio.create_task(self._execute_hub_job(job_id, cached_job))
        self._active_hub_jobs[job_id] = task

        def _cleanup(_t):
            self._active_hub_jobs.pop(job_id, None)
        task.add_done_callback(_cleanup)

    async def _execute_hub_job(self, job_id: str, job_data: dict) -> None:
        """Execute a job from the Hub and report the result."""
        from .base_agent import ActiveJob

        description = job_data.get("description", "")
        budget = job_data.get("budget_usdc", 0)

        active_job = ActiveJob(
            job_id=int(job_id) if job_id.isdigit() else 0,
            bid_id=0,
            job_type=0,
            description=description,
            budget=int(budget * 1e6) if budget else 0,
            deadline=job_data.get("deadline_ts", 0),
            status="in_progress",
            params=job_data.get("metadata", {}),
        )

        execute_fn = getattr(self._agent, "execute_job", None)
        if not execute_fn:
            await self._send_job_failed(job_id, "Agent has no execute_job method")
            return

        try:
            result = await execute_fn(active_job)
            success = result.get("success", True) if isinstance(result, dict) else True
            result_data = result if isinstance(result, dict) else {"result": result}

            if success:
                await self._send_job_completed(job_id, result_data)
            else:
                await self._send_job_failed(
                    job_id, result_data.get("error", "execution returned failure")
                )
        except Exception as e:
            logger.exception("Hub job %s execution failed", job_id)
            await self._send_job_failed(job_id, f"execution failed: {type(e).__name__}")

    def _on_bid_rejected(self, msg: dict) -> None:
        job_id = msg.get("job_id", "")
        reason = msg.get("reason", "")
        self._job_cache.pop(job_id, None)
        logger.info("Bid rejected for hub job %s: %s", job_id, reason)

    def _on_job_cancelled(self, msg: dict) -> None:
        job_id = msg.get("job_id", "")
        self._job_cache.pop(job_id, None)
        logger.info("Hub job %s cancelled", job_id)
        task = self._active_hub_jobs.pop(job_id, None)
        if task and not task.done():
            task.cancel()

    # -- Outbound messages ----------------------------------------------------

    async def _send_job_completed(self, job_id: str, result: dict) -> None:
        if self._ws:
            await self._ws.send(json.dumps({
                "type": "job_completed",
                "job_id": job_id,
                "success": True,
                "result": result,
            }))
            logger.info("Hub job %s completed", job_id)

    async def _send_job_failed(self, job_id: str, error: str) -> None:
        if self._ws:
            await self._ws.send(json.dumps({
                "type": "job_failed",
                "job_id": job_id,
                "error": error,
            }))
            logger.error("Hub job %s failed: %s", job_id, error)
