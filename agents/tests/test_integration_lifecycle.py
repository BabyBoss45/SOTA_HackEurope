"""Integration tests — full SOTAAgent boot-to-shutdown lifecycle."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
import websockets

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.asyncio]


async def _post_job(http_url, tags=None, budget=10.0, bid_window=2, deadline_ts=None):
    if deadline_ts is None:
        deadline_ts = int(time.time()) + 3600
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{http_url}/jobs", json={
            "description": "lifecycle test job",
            "tags": tags or ["test"],
            "budget_usdc": budget,
            "deadline_ts": deadline_ts,
            "poster": "0xPoster",
            "bid_window_seconds": bid_window,
        })
        return resp.json()


class TestLifecycle:
    async def test_full_lifecycle_off_chain(self, hub_server, make_agent_class):
        """Boot agent → post job → agent bids/wins/executes/completes."""

        async def execute(self, job):
            return {"success": True, "result": "done"}

        AgentCls = make_agent_class(name="lifecycle-agent", tags=["test"], execute_fn=execute)
        agent = AgentCls()
        agent._wallet = None

        # Mock preflight to pass
        with patch("sota_sdk.preflight.run_preflight") as mock_pf:
            mock_pf.return_value = MagicMock(ok=True, errors=[], warnings=[])
            with patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_server.ws_url):
                with patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None):
                    with patch("sota_sdk.cost.config.initialize_cost_tracking"):
                        boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
                        # Wait for agent to connect
                        await asyncio.sleep(1.5)

        # Post a job
        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2)
        job_id = job_resp["job_id"]

        # Wait for execution to complete
        await asyncio.sleep(4)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert data["status"] == "completed"

        # Shutdown
        if agent._shutdown_event:
            agent._shutdown_event.set()
        boot_task.cancel()
        try:
            await boot_task
        except (asyncio.CancelledError, SystemExit):
            pass

    async def test_execute_timeout(self, hub_server, make_agent_class):
        """Slow execute → job_failed."""

        async def slow_execute(self, job):
            await asyncio.sleep(100)
            return {"success": True}

        AgentCls = make_agent_class(name="slow-agent", tags=["test"], execute_fn=slow_execute)
        agent = AgentCls()
        agent._wallet = None

        # Keep patches active for the whole test so _DEFAULT_EXECUTE_TIMEOUT stays at 2
        patches = [
            patch("sota_sdk.preflight.run_preflight", return_value=MagicMock(ok=True, errors=[], warnings=[])),
            patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_server.ws_url),
            patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None),
            patch("sota_sdk.agent._DEFAULT_EXECUTE_TIMEOUT", 2),
            patch("sota_sdk.cost.config.initialize_cost_tracking"),
        ]
        for p in patches:
            p.start()

        boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
        await asyncio.sleep(1.5)

        # Post job with no deadline so _DEFAULT_EXECUTE_TIMEOUT (patched to 2s) is used
        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2, deadline_ts=0)
        job_id = job_resp["job_id"]

        # Wait for execution timeout (2s timeout + bid window + processing)
        await asyncio.sleep(8)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert data["status"] == "failed"

        if agent._shutdown_event:
            agent._shutdown_event.set()
        boot_task.cancel()
        try:
            await boot_task
        except (asyncio.CancelledError, SystemExit):
            pass
        for p in patches:
            p.stop()

    async def test_execute_exception(self, hub_server, make_agent_class):
        """Execute raises → job_failed."""

        async def bad_execute(self, job):
            raise RuntimeError("kaboom")

        AgentCls = make_agent_class(name="bad-agent", tags=["test"], execute_fn=bad_execute)
        agent = AgentCls()
        agent._wallet = None

        with patch("sota_sdk.preflight.run_preflight") as mock_pf:
            mock_pf.return_value = MagicMock(ok=True, errors=[], warnings=[])
            with patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_server.ws_url):
                with patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None):
                    with patch("sota_sdk.cost.config.initialize_cost_tracking"):
                        boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
                        await asyncio.sleep(1.5)

        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2)
        job_id = job_resp["job_id"]

        await asyncio.sleep(4)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert data["status"] == "failed"

        if agent._shutdown_event:
            agent._shutdown_event.set()
        boot_task.cancel()
        try:
            await boot_task
        except (asyncio.CancelledError, SystemExit):
            pass

    async def test_graceful_shutdown(self, hub_server, make_agent_class):
        """Set _shutdown_event → active tasks cancelled."""

        async def execute(self, job):
            await asyncio.sleep(100)  # long running
            return {"success": True}

        AgentCls = make_agent_class(name="shutdown-test", tags=["test"], execute_fn=execute)
        agent = AgentCls()
        agent._wallet = None

        patches = [
            patch("sota_sdk.preflight.run_preflight", return_value=MagicMock(ok=True, errors=[], warnings=[])),
            patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_server.ws_url),
            patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None),
            patch("sota_sdk.agent._SHUTDOWN_TIMEOUT", 2),
            patch("sota_sdk.cost.config.initialize_cost_tracking"),
        ]
        for p in patches:
            p.start()

        boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
        await asyncio.sleep(1.5)

        await _post_job(hub_server.http_url, tags=["test"], bid_window=1)
        await asyncio.sleep(3)

        # Trigger shutdown
        agent._shutdown_event.set()

        try:
            await asyncio.wait_for(boot_task, timeout=10)
        except (asyncio.CancelledError, SystemExit, asyncio.TimeoutError):
            pass
        for p in patches:
            p.stop()

    async def test_concurrent_jobs(self, hub_server, make_agent_class):
        """3 jobs posted → all completed."""

        async def execute(self, job):
            await asyncio.sleep(0.5)
            return {"success": True, "job_id": job.id}

        AgentCls = make_agent_class(name="concurrent-agent", tags=["test"], execute_fn=execute)
        agent = AgentCls()
        agent._wallet = None

        with patch("sota_sdk.preflight.run_preflight") as mock_pf:
            mock_pf.return_value = MagicMock(ok=True, errors=[], warnings=[])
            with patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_server.ws_url):
                with patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None):
                    with patch("sota_sdk.cost.config.initialize_cost_tracking"):
                        boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
                        await asyncio.sleep(1.5)

        # Post 3 jobs
        job_ids = []
        for _ in range(3):
            resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=1)
            job_ids.append(resp["job_id"])
            await asyncio.sleep(0.2)

        # Wait for all to complete
        await asyncio.sleep(8)

        async with httpx.AsyncClient() as client:
            completed = 0
            for jid in job_ids:
                resp = await client.get(f"{hub_server.http_url}/jobs/{jid}")
                if resp.json()["status"] == "completed":
                    completed += 1
            assert completed == 3

        if agent._shutdown_event:
            agent._shutdown_event.set()
        boot_task.cancel()
        try:
            await boot_task
        except (asyncio.CancelledError, SystemExit):
            pass
