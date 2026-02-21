"""
WebSocket client to the SOTA marketplace hub.

Handles:
- Connecting / auto-reconnecting
- Sending ``register`` on connect
- Heartbeat loop
- Dispatching incoming messages (job_available, bid_accepted, bid_rejected, job_cancelled)
- Queuing outgoing messages during disconnects so nothing is silently lost
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from typing import Any, Callable, Coroutine, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from ..config import (
    SOTA_MARKETPLACE_URL,
    WS_HEARTBEAT_INTERVAL,
    WS_RECONNECT_MIN,
    WS_RECONNECT_MAX,
)


def _ws_is_open(ws) -> bool:
    """Check if a websockets connection is open (compatible with v14+ and v15+)."""
    if hasattr(ws, "open"):
        return ws.open
    # websockets v15+: ClientConnection has no .open; check close_code instead
    return ws.close_code is None

logger = logging.getLogger(__name__)

# Type alias for async message handlers
Handler = Callable[[dict], Coroutine[Any, Any, None]]

# Max number of messages to buffer while disconnected
_MAX_SEND_QUEUE = 256


class MarketplaceClient:
    """
    Async WebSocket client that stays connected to the marketplace hub.

    Usage (internal -- called by SOTAAgent.run())::

        client = MarketplaceClient(url, register_payload)
        client.on("job_available", handle_job)
        client.on("bid_accepted", handle_accepted)
        await client.connect()   # blocks, auto-reconnects
    """

    def __init__(
        self,
        url: str = SOTA_MARKETPLACE_URL,
        register_payload: Optional[dict] = None,
    ):
        if not url.startswith(("ws://", "wss://")):
            raise ValueError(
                f"SOTA_MARKETPLACE_URL must start with ws:// or wss://, got: {url}"
            )
        if url.startswith("ws://"):
            logger.warning(
                "WebSocket connection is unencrypted (ws://). "
                "Use wss:// in production."
            )

        self._url = url
        self._register_payload = register_payload
        self._handlers: Dict[str, Handler] = {}
        self._ws = None  # Optional[websockets.asyncio.client.ClientConnection]
        self._running = False
        self._reconnect_delay = WS_RECONNECT_MIN
        self._send_queue: deque[dict] = deque(maxlen=_MAX_SEND_QUEUE)
        self.agent_id: str = ""  # populated after hub sends "registered"

    # -- Public API ------------------------------------------------------------

    def on(self, message_type: str, handler: Handler) -> None:
        """Register a handler for a given message type."""
        self._handlers[message_type] = handler

    async def connect(self) -> None:
        """Connect and listen forever, auto-reconnecting on failure."""
        self._running = True
        while self._running:
            try:
                await self._connect_once()
            except Exception as e:
                if not self._running:
                    break
                delay = self._next_delay()
                logger.warning(
                    "WS disconnected (%s), reconnecting in %.1fs", e, delay
                )
                await asyncio.sleep(delay)

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def send(self, payload: dict) -> None:
        """
        Send a JSON message to the hub.

        If the socket is disconnected the message is queued (up to
        ``_MAX_SEND_QUEUE`` items) and flushed when the connection
        comes back. Heartbeats are not queued.
        """
        if self._ws is not None and _ws_is_open(self._ws):
            try:
                await self._ws.send(json.dumps(payload))
                return
            except (ConnectionClosed, Exception):
                pass  # Fall through to queue
        # Don't queue heartbeats -- they're ephemeral
        if payload.get("type") == "heartbeat":
            return
        self._send_queue.append(payload)
        logger.debug(
            "WS not connected, queued %s (queue=%d)",
            payload.get("type"), len(self._send_queue),
        )

    @property
    def connected(self) -> bool:
        return self._ws is not None and _ws_is_open(self._ws)

    # -- Internals -------------------------------------------------------------

    async def _connect_once(self) -> None:
        """Single connection attempt: connect, register, listen."""
        logger.info("Connecting to marketplace hub at %s ...", self._url)
        async with websockets.connect(
            self._url,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            self._ws = ws
            self._reconnect_delay = WS_RECONNECT_MIN
            logger.info("Connected to marketplace hub")

            # Auto-register
            if self._register_payload:
                await ws.send(json.dumps(self._register_payload))
                logger.info("Sent register message to hub")

            # Flush any messages that were queued while disconnected
            await self._flush_queue()

            # Spin up heartbeat
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            try:
                await self._listen(ws)
            finally:
                heartbeat_task.cancel()
                self._ws = None

    async def _flush_queue(self) -> None:
        """Send all queued messages that accumulated during disconnect."""
        flushed = 0
        while self._send_queue and self._ws and _ws_is_open(self._ws):
            msg = self._send_queue[0]  # peek, don't remove yet
            try:
                await self._ws.send(json.dumps(msg))
                self._send_queue.popleft()  # remove only on success
                flushed += 1
            except Exception:
                logger.warning("Flush interrupted, %d msgs remain in queue", len(self._send_queue))
                break
        if flushed:
            logger.debug("Flushed %d queued messages", flushed)

    async def _listen(self, ws) -> None:
        """Read messages until the connection drops."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Non-JSON message from hub: %.200s", raw)
                continue

            msg_type = msg.get("type", "")

            # Handle hub's registration acknowledgement
            if msg_type == "registered":
                self.agent_id = msg.get("agent_id", "")
                logger.info(
                    "Registered with hub, agent_id=%s", self.agent_id
                )
                continue

            handler = self._handlers.get(msg_type)
            if handler:
                try:
                    await handler(msg)
                except Exception:
                    logger.exception("Handler for '%s' raised", msg_type)
            else:
                logger.debug("Unhandled message type: %s", msg_type)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        try:
            while self._running:
                if not self._ws or not _ws_is_open(self._ws):
                    logger.warning("Heartbeat: connection lost, stopping heartbeat loop")
                    break
                try:
                    await self.send({"type": "heartbeat"})
                except Exception as e:
                    logger.warning("Heartbeat send failed: %s", e)
                    break
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            pass

    def _next_delay(self) -> float:
        """Exponential backoff with jitter."""
        delay = self._reconnect_delay + random.uniform(0, 1)
        self._reconnect_delay = min(self._reconnect_delay * 2, WS_RECONNECT_MAX)
        return delay
