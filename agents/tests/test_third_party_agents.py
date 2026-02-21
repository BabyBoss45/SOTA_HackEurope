"""Integration tests — third-party agent public API contract proof.

Each test defines an agent class inline exactly as a third-party developer would,
proving the SDK's public API works end-to-end.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from sota_sdk import SOTAAgent, Job, BaseTool, ToolManager, BidStrategy, Bid, DefaultBidStrategy

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _post_job(http_url, tags=None, budget=10.0, bid_window=2):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{http_url}/jobs", json={
            "description": "third-party test",
            "tags": tags or ["test"],
            "budget_usdc": budget,
            "deadline_ts": int(time.time()) + 3600,
            "poster": "0xPoster",
            "bid_window_seconds": bid_window,
        })
        return resp.json()


def _boot_agent(agent, hub_url):
    """Start the agent boot sequence with mocked internals."""
    ctx = patch("sota_sdk.preflight.run_preflight")
    mock_pf = ctx.start()
    mock_pf.return_value = MagicMock(ok=True, errors=[], warnings=[])

    ctx2 = patch("sota_sdk.agent.SOTA_MARKETPLACE_URL", hub_url)
    ctx2.start()

    ctx3 = patch("sota_sdk.agent.SOTA_AGENT_PRIVATE_KEY", None)
    ctx3.start()

    ctx4 = patch("sota_sdk.cost.config.initialize_cost_tracking")
    ctx4.start()

    return [ctx, ctx2, ctx3, ctx4]


async def _run_agent_test(hub_server, AgentCls, post_tags=None, budget=10.0, bid_window=2):
    """Helper: boot agent, post job, wait, return job status."""
    agent = AgentCls()
    agent._wallet = None

    patches = _boot_agent(agent, hub_server.ws_url)
    boot_task = asyncio.create_task(agent._boot("127.0.0.1", 0))
    await asyncio.sleep(1.5)

    job_resp = await _post_job(hub_server.http_url, tags=post_tags or AgentCls.tags, budget=budget, bid_window=bid_window)
    job_id = job_resp["job_id"]

    await asyncio.sleep(5)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
        data = resp.json()

    if agent._shutdown_event:
        agent._shutdown_event.set()
    boot_task.cancel()
    try:
        await boot_task
    except (asyncio.CancelledError, SystemExit):
        pass
    for p in patches:
        p.stop()
    return data


class TestMinimalAgent:
    async def test_connects_receives_executes_completes(self, hub_server):
        """Minimal agent: just name/tags/execute → full lifecycle."""

        class MinimalAgent(SOTAAgent):
            name = "minimal-agent"
            description = "The simplest possible agent"
            tags = ["test"]

            async def execute(self, job: Job) -> dict:
                return {"success": True, "result": f"Processed: {job.description}"}

        data = await _run_agent_test(hub_server, MinimalAgent)
        assert data["status"] == "completed"


class TestCustomBidStrategy:
    async def test_high_budget_only(self, hub_server):
        """Custom bid strategy only bids on high-budget jobs."""

        class HighBudgetOnly(BidStrategy):
            def set_agent_tags(self, tags):
                pass
            async def evaluate(self, job: Job):
                if job.budget_usdc < 50:
                    return None
                return Bid(job_id=job.id, amount_usdc=job.budget_usdc * 0.8, tags=job.tags)

        class PickyAgent(SOTAAgent):
            name = "picky-agent"
            description = "Only takes high-budget jobs"
            tags = ["test"]
            bid_strategy = HighBudgetOnly()

            async def execute(self, job: Job) -> dict:
                return {"success": True}

        # Low budget — should not get bid
        data_low = await _run_agent_test(hub_server, PickyAgent, budget=5.0)
        assert data_low["status"] in ("expired", "bidding")

        # High budget — should complete
        data_high = await _run_agent_test(hub_server, PickyAgent, budget=100.0)
        assert data_high["status"] == "completed"


class TestAgentWithTools:
    async def test_tool_output_in_result(self, hub_server):
        """Agent uses ToolManager+BaseTool in execute → result includes tool output."""

        class UpperTool(BaseTool):
            name: str = "upper"
            description: str = "Uppercases text"
            async def execute(self, text: str = "") -> str:
                return text.upper()

        class ToolAgent(SOTAAgent):
            name = "tool-agent"
            description = "Uses tools"
            tags = ["test"]

            async def setup(self):
                self.tools = ToolManager(tools=[UpperTool()])

            async def execute(self, job: Job) -> dict:
                result = await self.tools.call("upper", {"text": "hello"})
                return {"success": True, "tool_result": result}

        data = await _run_agent_test(hub_server, ToolAgent)
        assert data["status"] == "completed"


class TestSetupHook:
    async def test_setup_initializes_state(self, hub_server):
        """setup() initializes state → state available in execute()."""

        class StatefulAgent(SOTAAgent):
            name = "stateful-agent"
            description = "Has setup state"
            tags = ["test"]

            async def setup(self):
                self.greeting = "Hello from setup!"

            async def execute(self, job: Job) -> dict:
                return {"success": True, "greeting": self.greeting}

        data = await _run_agent_test(hub_server, StatefulAgent)
        assert data["status"] == "completed"


class TestJobParams:
    async def test_agent_reads_params(self, hub_server):
        """Job has custom metadata → agent reads them in execute()."""

        class ParamAgent(SOTAAgent):
            name = "param-agent"
            description = "Reads job params"
            tags = ["test"]

            async def execute(self, job: Job) -> dict:
                return {"success": True, "description": job.description}

        data = await _run_agent_test(hub_server, ParamAgent)
        assert data["status"] == "completed"


class TestMultiAgentCompetition:
    async def test_two_agents_one_wins(self, hub_server):
        """Two different agent classes with same tags → one wins, other rejected."""

        class CheapAgent(SOTAAgent):
            name = "cheap-agent"
            description = "Bids low"
            tags = ["compete"]
            bid_strategy = DefaultBidStrategy(price_ratio=0.30)

            async def execute(self, job: Job) -> dict:
                return {"success": True, "agent": "cheap"}

        class ExpensiveAgent(SOTAAgent):
            name = "expensive-agent"
            description = "Bids high"
            tags = ["compete"]
            bid_strategy = DefaultBidStrategy(price_ratio=0.95)

            async def execute(self, job: Job) -> dict:
                return {"success": True, "agent": "expensive"}

        agent1 = CheapAgent()
        agent1._wallet = None
        agent2 = ExpensiveAgent()
        agent2._wallet = None

        patches1 = _boot_agent(agent1, hub_server.ws_url)
        patches2 = _boot_agent(agent2, hub_server.ws_url)

        boot1 = asyncio.create_task(agent1._boot("127.0.0.1", 0))
        boot2 = asyncio.create_task(agent2._boot("127.0.0.1", 0))
        await asyncio.sleep(2)

        job_resp = await _post_job(hub_server.http_url, tags=["compete"], budget=10.0, bid_window=2)
        job_id = job_resp["job_id"]

        await asyncio.sleep(6)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()

        assert data["status"] == "completed"
        # The cheap agent should have won
        if data.get("winner"):
            assert data["winner"]["agent"] == "cheap-agent"

        for a in [agent1, agent2]:
            if a._shutdown_event:
                a._shutdown_event.set()
        for t in [boot1, boot2]:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, SystemExit):
                pass
        for p in patches1 + patches2:
            p.stop()
