"""Shared fixtures, factories, and helpers for the SOTA SDK test suite."""

import asyncio
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
import pytest_asyncio

from sota_sdk.models import Bid, Job
from sota_sdk.agent import SOTAAgent
from sota_sdk.marketplace.bidding import BidStrategy


# ── Markers ──────────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (no network)")
    config.addinivalue_line("markers", "integration: integration tests (need ports)")
    config.addinivalue_line("markers", "slow: slow tests (>10s)")


# ── Helpers ──────────────────────────────────────────────────────────────────

def free_port() -> int:
    """Bind to port 0 and return the OS-assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.05):
    """Async poll helper — raises TimeoutError if predicate never becomes truthy."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        await asyncio.sleep(interval)
    raise TimeoutError(f"Predicate did not become truthy within {timeout}s")


# ── Factories ────────────────────────────────────────────────────────────────

@pytest.fixture
def make_job():
    """Factory fixture: make_job(**overrides) → Job with sensible defaults."""
    def _make(**overrides) -> Job:
        defaults = {
            "id": str(uuid.uuid4()),
            "description": "Test job",
            "tags": ["test"],
            "budget_usdc": 10.0,
            "deadline_ts": int(time.time()) + 3600,
            "poster": "0xPoster",
            "metadata": {},
            "params": {},
        }
        defaults.update(overrides)
        return Job(**defaults)
    return _make


@pytest.fixture
def make_bid():
    """Factory fixture: make_bid(**overrides) → Bid with sensible defaults."""
    def _make(**overrides) -> Bid:
        defaults = {
            "job_id": str(uuid.uuid4()),
            "amount_usdc": 8.0,
            "estimated_seconds": 300,
            "bid_id": str(uuid.uuid4()),
            "tags": ["test"],
            "metadata": {},
        }
        defaults.update(overrides)
        return Bid(**defaults)
    return _make


@pytest.fixture
def make_agent_class():
    """Factory: make_agent_class(name, tags, execute_fn) → SOTAAgent subclass."""
    def _make(
        name: str = "test-agent",
        tags: Optional[list[str]] = None,
        execute_fn=None,
        description: str = "A test agent",
    ) -> type:
        if tags is None:
            tags = ["test"]

        async def default_execute(self, job):
            return {"success": True, "result": "done"}

        attrs = {
            "name": name,
            "description": description,
            "tags": tags,
        }
        if execute_fn is not None:
            attrs["execute"] = execute_fn
        else:
            attrs["execute"] = default_execute

        cls = type(f"Dynamic_{name.replace('-','_')}", (SOTAAgent,), attrs)
        return cls
    return _make


# ── Mock Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_wallet():
    """MagicMock mimicking AgentWallet."""
    wallet = MagicMock()
    wallet.address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
    wallet.sign_message.return_value = "0x" + "ab" * 65
    wallet.build_and_send.return_value = "0x" + "cc" * 32
    wallet.wait_for_receipt.return_value = {"status": 1}
    wallet.network = MagicMock()
    wallet.addresses = MagicMock()
    return wallet


@pytest.fixture
def mock_ws_client():
    """AsyncMock mimicking MarketplaceClient."""
    client = AsyncMock()
    client.send = AsyncMock()
    client.agent_id = ""
    type(client).connected = PropertyMock(return_value=False)
    client.on = MagicMock()
    return client


# ── Hub Fixtures (for integration tests) ─────────────────────────────────────

@dataclass
class HubContext:
    host: str
    port: int
    ws_url: str
    http_url: str
    registry: Any
    engine: Any
    router: Any


@pytest_asyncio.fixture
async def hub_server():
    """Start an isolated hub FastAPI app on a random port, yield HubContext."""
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    import json
    import logging

    from marketplace.registry import AgentRegistry
    from marketplace.bidding import BiddingEngine
    from marketplace.router import JobRouter
    from marketplace.models import (
        AgentInfo, MessageType, PostJobRequest, PostJobResponse,
    )

    logger = logging.getLogger("test_hub")

    reg = AgentRegistry()
    eng = BiddingEngine()
    rtr = JobRouter(registry=reg, engine=eng)

    app = FastAPI()

    MAX_MSG = 64 * 1024

    @app.get("/health")
    async def health():
        return {"status": "ok", "connected_agents": reg.count, "active_jobs": len(eng.list_jobs())}

    @app.post("/jobs", response_model=PostJobResponse)
    async def post_job(req: PostJobRequest):
        result = await rtr.route_job(req)
        return PostJobResponse(**result)

    @app.get("/jobs")
    async def list_jobs():
        jobs = eng.list_jobs()
        return {
            "total": len(jobs),
            "jobs": [
                {
                    "job_id": j.job.id,
                    "description": j.job.description,
                    "tags": j.job.tags,
                    "budget_usdc": j.job.budget_usdc,
                    "status": j.status.value,
                    "poster": j.job.poster,
                    "bid_count": len(j.bids),
                    "winner": j.winner.agent_name if j.winner else None,
                    "created_at": j.created_at,
                }
                for j in jobs
            ],
        }

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        from fastapi import HTTPException
        active = eng.get_job(job_id)
        if not active:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return {
            "job_id": active.job.id,
            "status": active.status.value,
            "bids": [
                {"bid_id": b.bid_id, "agent": b.agent_name, "amount_usdc": b.amount_usdc}
                for b in active.bids
            ],
            "winner": {
                "agent": active.winner.agent_name,
                "amount_usdc": active.winner.amount_usdc,
            } if active.winner else None,
            "result": active.result,
        }

    @app.get("/agents")
    async def list_agents():
        agents = reg.all_agents()
        return {
            "total": len(agents),
            "agents": [
                {"agent_id": a.agent_id, "name": a.name, "tags": a.tags}
                for a in agents
            ],
        }

    @app.websocket("/ws/agent")
    async def agent_ws(ws: WebSocket):
        await ws.accept()
        agent_id = None
        try:
            raw = await ws.receive_text()
            if len(raw) > MAX_MSG:
                await ws.close(code=1009, reason="Message too large")
                return
            data = json.loads(raw)
            if data.get("type") != MessageType.REGISTER:
                await ws.send_text(json.dumps({"error": "First message must be 'register'"}))
                await ws.close(code=1008)
                return
            if "agent" not in data or not isinstance(data["agent"], dict):
                await ws.send_text(json.dumps({"error": "Missing agent object"}))
                await ws.close(code=1008)
                return
            info = AgentInfo(**data["agent"])
            agent = reg.register(info, ws)
            agent_id = agent.agent_id
            await ws.send_text(json.dumps({
                "type": "registered",
                "agent_id": agent_id,
                "message": f"Welcome, {info.name}!",
            }))
            while True:
                raw = await ws.receive_text()
                if len(raw) > MAX_MSG:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type")
                if msg_type == MessageType.BID:
                    job_id = data.get("job_id")
                    amount = data.get("amount_usdc")
                    if job_id and amount and float(amount) > 0:
                        eng.submit_bid(
                            job_id=job_id,
                            agent_id=agent_id,
                            agent_name=agent.name,
                            wallet_address=agent.wallet_address,
                            amount_usdc=float(amount),
                            estimated_seconds=data.get("estimated_seconds", 300),
                        )
                elif msg_type == MessageType.JOB_COMPLETED:
                    await rtr.handle_completion(
                        job_id=data.get("job_id", ""),
                        agent_id=agent_id,
                        success=data.get("success", True),
                        result=data.get("result", {}),
                    )
                elif msg_type == MessageType.JOB_FAILED:
                    await rtr.handle_failure(
                        job_id=data.get("job_id", ""),
                        agent_id=agent_id,
                        error=data.get("error", "unknown"),
                    )
                elif msg_type == MessageType.HEARTBEAT:
                    reg.touch_heartbeat(agent_id)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if agent_id:
                reg.unregister(agent_id)

    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    # Wait until server is fully ready (HTTP responds, not just TCP accept)
    import httpx
    for _ in range(100):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/health")
                if resp.status_code == 200:
                    break
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            await asyncio.sleep(0.05)

    ctx = HubContext(
        host="127.0.0.1",
        port=port,
        ws_url=f"ws://127.0.0.1:{port}/ws/agent",
        http_url=f"http://127.0.0.1:{port}",
        registry=reg,
        engine=eng,
        router=rtr,
    )
    yield ctx

    server.should_exit = True
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
