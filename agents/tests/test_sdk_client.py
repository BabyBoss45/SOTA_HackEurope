"""Unit tests for sota_sdk.marketplace.client — MarketplaceClient."""

import asyncio
import json
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sota_sdk.marketplace.client import MarketplaceClient

pytestmark = pytest.mark.unit


class TestURLValidation:
    def test_rejects_http(self):
        with pytest.raises(ValueError, match="ws://"):
            MarketplaceClient(url="http://example.com")

    def test_rejects_ftp(self):
        with pytest.raises(ValueError, match="ws://"):
            MarketplaceClient(url="ftp://example.com")

    def test_accepts_ws(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        assert c._url == "ws://localhost:3002/ws/agent"

    def test_accepts_wss(self):
        c = MarketplaceClient(url="wss://hub.example.com/ws/agent")
        assert c._url == "wss://hub.example.com/ws/agent"

    def test_warns_unencrypted(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            MarketplaceClient(url="ws://remote.host:3002/ws/agent")
        assert "unencrypted" in caplog.text.lower()


class TestHandlerRegistration:
    def test_on_registers_handler(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        handler = AsyncMock()
        c.on("job_available", handler)
        assert "job_available" in c._handlers

    def test_multiple_handlers(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        c.on("job_available", AsyncMock())
        c.on("bid_accepted", AsyncMock())
        assert len(c._handlers) == 2


class TestProperties:
    def test_connected_false_initially(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        assert c.connected is False

    def test_agent_id_empty_initially(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        assert c.agent_id == ""


class TestSendQueue:
    async def test_queues_when_disconnected(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        await c.send({"type": "bid", "job_id": "j1", "amount_usdc": 5.0})
        assert len(c._send_queue) == 1

    async def test_heartbeat_not_queued(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        await c.send({"type": "heartbeat"})
        assert len(c._send_queue) == 0

    async def test_queue_caps_at_256(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        for i in range(300):
            await c.send({"type": "bid", "job_id": f"j{i}", "amount_usdc": 1.0})
        assert len(c._send_queue) == 256

    async def test_send_calls_ws_when_connected(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        mock_ws = AsyncMock()
        mock_ws.open = True
        c._ws = mock_ws
        await c.send({"type": "bid", "job_id": "j1"})
        mock_ws.send.assert_called_once()


def _make_async_ws(messages: list[str]):
    """Create a mock websocket that yields messages via async for."""
    class FakeWS:
        def __init__(self, msgs):
            self._msgs = msgs
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._msgs:
                raise StopAsyncIteration
            return self._msgs.pop(0)
    return FakeWS(list(messages))


class TestListen:
    async def test_dispatches_to_handler(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        handler = AsyncMock()
        c.on("job_available", handler)

        msg = {"type": "job_available", "job": {"id": "j1"}}
        mock_ws = _make_async_ws([json.dumps(msg)])

        await c._listen(mock_ws)
        handler.assert_called_once_with(msg)

    async def test_sets_agent_id_on_registered(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        msg = {"type": "registered", "agent_id": "test-agent_1"}
        mock_ws = _make_async_ws([json.dumps(msg)])

        await c._listen(mock_ws)
        assert c.agent_id == "test-agent_1"

    async def test_ignores_non_json(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        mock_ws = _make_async_ws(["not json at all"])

        # Should not raise
        await c._listen(mock_ws)

    async def test_ignores_unknown_types(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        msg = {"type": "unknown_msg_type"}
        mock_ws = _make_async_ws([json.dumps(msg)])

        # Should not raise
        await c._listen(mock_ws)

    async def test_handler_exception_logged(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")

        async def bad_handler(msg):
            raise ValueError("boom")

        c.on("test_type", bad_handler)
        msg = {"type": "test_type"}
        mock_ws = _make_async_ws([json.dumps(msg)])

        # Should not propagate the exception
        await c._listen(mock_ws)


class TestFlushQueue:
    async def test_flushes_all_queued(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        c._send_queue.append({"type": "bid", "job_id": "j1"})
        c._send_queue.append({"type": "bid", "job_id": "j2"})

        mock_ws = AsyncMock()
        mock_ws.open = True
        c._ws = mock_ws

        await c._flush_queue()
        assert len(c._send_queue) == 0
        assert mock_ws.send.call_count == 2


class TestReconnect:
    def test_backoff_increases(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        d1 = c._next_delay()
        d2 = c._next_delay()
        d3 = c._next_delay()
        # Each delay base should approximately double (with jitter)
        assert d2 > d1 * 0.5  # allow for jitter
        assert d3 > d2 * 0.5

    def test_backoff_capped_at_max(self):
        from sota_sdk.config import WS_RECONNECT_MAX
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        # Force high delay
        c._reconnect_delay = WS_RECONNECT_MAX
        delay = c._next_delay()
        # delay = max + jitter(0,1), should be close to max
        assert delay <= WS_RECONNECT_MAX + 1.1


class TestDisconnect:
    async def test_disconnect_sets_running_false(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        c._running = True
        c._ws = None
        await c.disconnect()
        assert c._running is False

    async def test_disconnect_closes_ws(self):
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        c._running = True
        mock_ws = AsyncMock()
        c._ws = mock_ws
        await c.disconnect()
        mock_ws.close.assert_called_once()
