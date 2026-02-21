"""Unit tests for sota_sdk.agent — SOTAAgent class (no network)."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from sota_sdk.agent import SOTAAgent
from sota_sdk.models import Job, Bid
from sota_sdk.marketplace.bidding import DefaultBidStrategy

pytestmark = pytest.mark.unit


# ── Subclass & Initialization ────────────────────────────────────────────────

class TestSubclass:
    def test_inherits_class_attrs(self, make_agent_class):
        cls = make_agent_class(name="my-agent", tags=["nlp"])
        agent = cls()
        assert agent.name == "my-agent"
        assert agent.tags == ["nlp"]

    def test_mutable_tags_isolated(self, make_agent_class):
        cls = make_agent_class(name="a", tags=["test"])
        a1 = cls()
        a2 = cls()
        a1.tags.append("extra")
        assert "extra" not in a2.tags

    def test_default_bid_strategy_per_instance(self, make_agent_class):
        cls = make_agent_class(name="a", tags=["t"])
        a1 = cls()
        a2 = cls()
        assert a1.bid_strategy is not a2.bid_strategy
        assert isinstance(a1.bid_strategy, DefaultBidStrategy)


class TestExecute:
    async def test_base_raises_not_implemented(self):
        class Bare(SOTAAgent):
            name = "bare"
            tags = ["t"]
        agent = Bare()
        job = Job(id="1", description="d", tags=["t"], budget_usdc=10, deadline_ts=999, poster="0x")
        with pytest.raises(NotImplementedError, match="must be implemented"):
            await agent.execute(job)


class TestEvaluate:
    async def test_delegates_to_strategy(self, make_agent_class, make_job):
        cls = make_agent_class(name="a", tags=["test"])
        agent = cls()
        agent.bid_strategy.set_agent_tags(["test"])
        job = make_job(tags=["test"])
        bid = await agent.evaluate(job)
        assert bid is not None
        assert isinstance(bid, Bid)


# ── _hash_result ─────────────────────────────────────────────────────────────

class TestHashResult:
    def test_deterministic(self):
        h1 = SOTAAgent._hash_result({"a": 1, "b": 2})
        h2 = SOTAAgent._hash_result({"a": 1, "b": 2})
        assert h1 == h2

    def test_key_order_independent(self):
        h1 = SOTAAgent._hash_result({"b": 2, "a": 1})
        h2 = SOTAAgent._hash_result({"a": 1, "b": 2})
        assert h1 == h2

    def test_32_bytes(self):
        h = SOTAAgent._hash_result({"x": "y"})
        assert len(h) == 32


# ── _on_job_available ────────────────────────────────────────────────────────

class TestOnJobAvailable:
    async def test_ignores_empty_id(self, make_agent_class, mock_ws_client):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()
        agent._ws_client = mock_ws_client
        await agent._on_job_available({"job": {"id": ""}})
        mock_ws_client.send.assert_not_called()

    async def test_bids_on_matching(self, make_agent_class, mock_ws_client, make_job):
        cls = make_agent_class(name="a", tags=["test"])
        agent = cls()
        agent.bid_strategy.set_agent_tags(["test"])
        agent._ws_client = mock_ws_client

        job = make_job(tags=["test"])
        await agent._on_job_available({"job": {
            "id": job.id, "description": "d", "tags": ["test"],
            "budget_usdc": 10.0, "deadline_ts": int(time.time()) + 3600,
            "poster": "0xA",
        }})
        mock_ws_client.send.assert_called_once()
        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "bid"

    async def test_skips_when_evaluate_none(self, make_agent_class, mock_ws_client):
        cls = make_agent_class(name="a", tags=["python"])
        agent = cls()
        agent.bid_strategy.set_agent_tags(["python"])
        agent._ws_client = mock_ws_client

        await agent._on_job_available({"job": {
            "id": "j1", "description": "d", "tags": ["javascript"],
            "budget_usdc": 10.0, "deadline_ts": int(time.time()) + 3600,
            "poster": "0xA",
        }})
        mock_ws_client.send.assert_not_called()

    async def test_cache_eviction_at_1001(self, make_agent_class, mock_ws_client):
        cls = make_agent_class(name="a", tags=["test"])
        agent = cls()
        agent.bid_strategy.set_agent_tags(["test"])
        agent._ws_client = mock_ws_client

        for i in range(1002):
            await agent._on_job_available({"job": {
                "id": f"j{i}", "description": "d", "tags": ["test"],
                "budget_usdc": 10.0, "deadline_ts": int(time.time()) + 3600,
                "poster": "0xA",
            }})
        assert len(agent._job_cache) <= 1000


# ── _on_bid_accepted ────────────────────────────────────────────────────────

class TestOnBidAccepted:
    async def test_creates_task(self, make_agent_class, mock_ws_client, mock_wallet, make_job):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job()
        agent._job_cache[job.id] = job

        # Mock _execute_and_deliver to be a quick no-op
        agent._execute_and_deliver = AsyncMock()

        await agent._on_bid_accepted({"job_id": job.id, "bid_id": "b1"})
        assert job.id in agent._active_jobs or job.id in agent._reserved_jobs

    async def test_duplicate_guard_reserved(self, make_agent_class, mock_ws_client, make_job):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None
        agent._execute_and_deliver = AsyncMock()

        job = make_job()
        agent._job_cache[job.id] = job
        agent._reserved_jobs.add(job.id)

        await agent._on_bid_accepted({"job_id": job.id, "bid_id": "b1"})
        agent._execute_and_deliver.assert_not_called()

    async def test_concurrency_limit_sends_failed(self, make_agent_class, mock_ws_client, make_job, monkeypatch):
        monkeypatch.setattr("sota_sdk.agent._MAX_CONCURRENT_JOBS", 0)
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job()
        agent._job_cache[job.id] = job

        await agent._on_bid_accepted({"job_id": job.id, "bid_id": "b1"})
        # Should have sent job_failed
        mock_ws_client.send.assert_called()
        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_failed"

    async def test_missing_cache_resolves_fallback(self, make_agent_class, mock_ws_client):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None
        agent._execute_and_deliver = AsyncMock()

        # No job in cache — should still proceed with fallback Job
        await agent._on_bid_accepted({"job_id": "j1", "bid_id": "b1"})
        agent._execute_and_deliver.assert_called_once()


# ── _on_bid_rejected ────────────────────────────────────────────────────────

class TestOnBidRejected:
    async def test_clears_cache_and_reserved(self, make_agent_class, make_job):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()

        job = make_job()
        agent._job_cache[job.id] = job
        agent._reserved_jobs.add(job.id)

        await agent._on_bid_rejected({"job_id": job.id, "reason": "outbid"})
        assert job.id not in agent._job_cache
        assert job.id not in agent._reserved_jobs


# ── _on_job_cancelled ───────────────────────────────────────────────────────

class TestOnJobCancelled:
    async def test_cancels_active_task(self, make_agent_class, make_job):
        cls = make_agent_class(name="a", tags=["t"])
        agent = cls()

        job = make_job()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        agent._active_jobs[job.id] = mock_task
        agent._reserved_jobs.add(job.id)

        await agent._on_job_cancelled({"job_id": job.id})
        mock_task.cancel.assert_called_once()
        assert job.id not in agent._active_jobs
        assert job.id not in agent._reserved_jobs


# ── _execute_and_deliver ────────────────────────────────────────────────────

class TestExecuteAndDeliver:
    async def test_success_flow(self, make_agent_class, mock_ws_client, make_job):
        async def execute(self, job):
            return {"success": True, "data": "hello"}

        cls = make_agent_class(name="a", tags=["t"], execute_fn=execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job()
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            await agent._do_execute_and_deliver(job, "b1")

        mock_ws_client.send.assert_called()
        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_completed"
        assert sent["success"] is True

    async def test_timeout_sends_failed(self, make_agent_class, mock_ws_client, make_job):
        async def slow_execute(self, job):
            await asyncio.sleep(100)
            return {"success": True}

        cls = make_agent_class(name="a", tags=["t"], execute_fn=slow_execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job(deadline_ts=int(time.time()) + 1)  # 1 second deadline
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            with patch("sota_sdk.agent._DEFAULT_EXECUTE_TIMEOUT", 1):
                await agent._do_execute_and_deliver(job, "b1")

        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_failed"

    async def test_exception_sends_failed(self, make_agent_class, mock_ws_client, make_job):
        async def bad_execute(self, job):
            raise RuntimeError("exploded")

        cls = make_agent_class(name="a", tags=["t"], execute_fn=bad_execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job()
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            await agent._do_execute_and_deliver(job, "b1")

        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_failed"
        assert "exploded" in sent["error"]

    async def test_explicit_failure_sends_failed(self, make_agent_class, mock_ws_client, make_job):
        async def fail_execute(self, job):
            return {"success": False, "error": "nope"}

        cls = make_agent_class(name="a", tags=["t"], execute_fn=fail_execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job()
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            await agent._do_execute_and_deliver(job, "b1")

        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_failed"

    async def test_deadline_expired_sends_failed(self, make_agent_class, mock_ws_client, make_job):
        async def execute(self, job):
            return {"success": True}

        cls = make_agent_class(name="a", tags=["t"], execute_fn=execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None

        job = make_job(deadline_ts=int(time.time()) - 10)  # already expired
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            await agent._do_execute_and_deliver(job, "b1")

        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_failed"
        assert "deadline" in sent["error"].lower()

    async def test_no_wallet_skips_chain(self, make_agent_class, mock_ws_client, make_job):
        async def execute(self, job):
            return {"success": True, "data": "ok"}

        cls = make_agent_class(name="a", tags=["t"], execute_fn=execute)
        agent = cls()
        agent._ws_client = mock_ws_client
        agent._wallet = None  # no wallet

        job = make_job()
        with patch("sota_sdk.agent.SOTAAgent._get_paid_tracing_ctx") as mock_ctx:
            import contextlib
            mock_ctx.return_value = contextlib.AsyncExitStack()
            await agent._do_execute_and_deliver(job, "b1")

        sent = mock_ws_client.send.call_args[0][0]
        assert sent["type"] == "job_completed"
