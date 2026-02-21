"""
Marketplace Hub — FastAPI app + WebSocket server.

Central hub between Butler and external agents:
  - POST /jobs          — Butler posts a job here
  - GET  /jobs          — List all jobs
  - GET  /jobs/{id}     — Get a single job with bids
  - GET  /agents        — List connected agents
  - WS   /ws/agent      — Agents connect here on startup
  - GET  /health        — Health check

Runs on port 3002 by default.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    AgentInfo,
    BidMsg,
    JobCompletedMsg,
    JobFailedMsg,
    MessageType,
    PostJobRequest,
    PostJobResponse,
    RegisterMsg,
)
from .registry import AgentRegistry
from .bidding import BiddingEngine
from .router import JobRouter

logger = logging.getLogger(__name__)

# ─── Configuration (from env) ────────────────────────────────

HUB_HOST = os.getenv("HUB_HOST", "0.0.0.0")
HUB_PORT = int(os.getenv("HUB_PORT", "3002"))
_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
_hub_cors = os.getenv("HUB_CORS_ORIGINS", "*")
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else _hub_cors.split(",")
MAX_WS_MESSAGE_BYTES = int(os.getenv("HUB_MAX_WS_MSG_BYTES", str(64 * 1024)))  # 64 KB

# ─── Shared State ─────────────────────────────────────────────

registry = AgentRegistry()
engine = BiddingEngine()
router = JobRouter(registry=registry, engine=engine)


# ─── App Factory ──────────────────────────────────────────────

# NOTE: When mounted as sub-app via butler_api.py, this lifespan is NOT invoked.
# It only runs in standalone mode (python -m agents.marketplace.hub).
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Marketplace Hub starting on %s:%d", HUB_HOST, HUB_PORT)
    logger.info("WebSocket endpoint: /ws/agent")
    logger.info("REST endpoint:      /jobs")
    yield
    logger.info("Marketplace Hub shutting down")


app = FastAPI(title="SOTA Marketplace Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── REST Endpoints ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connected_agents": registry.count,
        "active_jobs": len(engine.list_jobs()),
    }


@app.post("/jobs", response_model=PostJobResponse)
async def post_job(req: PostJobRequest):
    """Butler posts a job here. Hub broadcasts to matching agents and opens bid window."""
    result = await router.route_job(req)
    return PostJobResponse(**result)


@app.get("/jobs")
async def list_jobs():
    """List all jobs in the hub."""
    jobs = engine.list_jobs()
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
    """Get a single job with its bids."""
    active = engine.get_job(job_id)
    if not active:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": active.job.id,
        "description": active.job.description,
        "tags": active.job.tags,
        "budget_usdc": active.job.budget_usdc,
        "status": active.status.value,
        "poster": active.job.poster,
        "winner": {
            "agent": active.winner.agent_name,
            "amount_usdc": active.winner.amount_usdc,
            "bid_id": active.winner.bid_id,
        } if active.winner else None,
        "bids": [
            {
                "bid_id": b.bid_id,
                "agent": b.agent_name,
                "amount_usdc": b.amount_usdc,
                "estimated_seconds": b.estimated_seconds,
                "submitted_at": b.submitted_at,
            }
            for b in active.bids
        ],
        "result": active.result,
    }


@app.get("/agents")
async def list_agents():
    """List all connected agents."""
    agents = registry.all_agents()
    return {
        "total": len(agents),
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "tags": a.tags,
                "wallet_address": a.wallet_address,
                "version": a.version,
                "capabilities": a.capabilities,
                "connected_at": a.connected_at,
                "last_heartbeat": a.last_heartbeat,
            }
            for a in agents
        ],
    }


# ─── WebSocket Endpoint ──────────────────────────────────────

@app.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    """
    Agents connect here on startup.

    Protocol:
      1. Agent connects and sends a ``register`` message.
      2. Hub adds agent to registry.
      3. Hub pushes ``job_available`` when matching jobs arrive.
      4. Agent sends ``bid``, ``job_completed``, ``job_failed``, or ``heartbeat``.
      5. On disconnect, agent is removed from registry.
    """
    await ws.accept()
    agent_id: str | None = None

    try:
        # ── Wait for registration message ─────────────────────
        raw = await ws.receive_text()
        if len(raw) > MAX_WS_MESSAGE_BYTES:
            await ws.close(code=1009, reason="Message too large")
            return

        data = json.loads(raw)

        if data.get("type") != MessageType.REGISTER:
            await ws.send_text(json.dumps({
                "error": "First message must be a 'register' message",
            }))
            await ws.close(code=1008)
            return

        if "agent" not in data or not isinstance(data["agent"], dict):
            await ws.send_text(json.dumps({
                "error": "'register' message must include an 'agent' object",
            }))
            await ws.close(code=1008)
            return

        try:
            info = AgentInfo(**data["agent"])
        except Exception as val_err:
            await ws.send_text(json.dumps({
                "error": f"Invalid agent info: {val_err}",
            }))
            await ws.close(code=1008)
            return

        agent = await registry.register(info, ws)
        agent_id = agent.agent_id

        # Acknowledge registration
        await ws.send_text(json.dumps({
            "type": "registered",
            "agent_id": agent_id,
            "message": f"Welcome, {info.name}!",
        }))

        # ── Message loop ──────────────────────────────────────
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_WS_MESSAGE_BYTES:
                logger.warning("Oversized message from %s (%d bytes), skipping", agent_id, len(raw))
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON from %s, skipping message", agent_id)
                continue

            msg_type = data.get("type")

            if msg_type == MessageType.BID:
                _handle_bid(data, agent_id, agent)

            elif msg_type == MessageType.JOB_COMPLETED:
                await _handle_job_completed(data, agent_id)

            elif msg_type == MessageType.JOB_FAILED:
                await _handle_job_failed(data, agent_id)

            elif msg_type == MessageType.HEARTBEAT:
                await registry.touch_heartbeat(agent_id)

            else:
                logger.warning(
                    "Unknown message type from %s: %s", agent_id, msg_type,
                )

    except WebSocketDisconnect:
        logger.info("Agent disconnected: %s", agent_id or "unknown")
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON from %s: %s", agent_id or "unknown", exc)
    except Exception as exc:
        logger.error("WebSocket error for %s: %s", agent_id or "unknown", exc)
    finally:
        if agent_id:
            await registry.unregister(agent_id)


# ─── Message Handlers ────────────────────────────────────────

def _handle_bid(data: Dict[str, Any], agent_id: str, agent: Any) -> None:
    """Process a bid message from an agent."""
    job_id = data.get("job_id")
    amount = data.get("amount_usdc")
    if not job_id or amount is None:
        logger.warning("Invalid bid from %s: missing job_id or amount_usdc", agent_id)
        return
    if not isinstance(amount, (int, float)) or amount <= 0:
        logger.warning("Invalid bid from %s: amount_usdc must be positive, got %s", agent_id, amount)
        return
    engine.submit_bid(
        job_id=job_id,
        agent_id=agent_id,
        agent_name=agent.name,
        wallet_address=agent.wallet_address,
        amount_usdc=float(amount),
        estimated_seconds=data.get("estimated_seconds", 300),
    )


async def _handle_job_completed(data: Dict[str, Any], agent_id: str) -> None:
    """Process a job_completed message from an agent."""
    job_id = data.get("job_id")
    if not job_id:
        logger.warning("Invalid job_completed from %s: missing job_id", agent_id)
        return
    await router.handle_completion(
        job_id=job_id,
        agent_id=agent_id,
        success=data.get("success", True),
        result=data.get("result", {}),
    )
    # Persist job stats
    if registry._db:
        try:
            earnings = float(data.get("earnings_usdc", 0))
            await registry._db.increment_worker_job_stats(agent_id, success=True, earnings_usdc=earnings)
        except Exception as e:
            logger.warning("Failed to increment job stats for %s: %s", agent_id, e)


async def _handle_job_failed(data: Dict[str, Any], agent_id: str) -> None:
    """Process a job_failed message from an agent."""
    job_id = data.get("job_id")
    if not job_id:
        logger.warning("Invalid job_failed from %s: missing job_id", agent_id)
        return
    await router.handle_failure(
        job_id=job_id,
        agent_id=agent_id,
        error=data.get("error", "Unknown error"),
    )
    # Persist job stats
    if registry._db:
        try:
            await registry._db.increment_worker_job_stats(agent_id, success=False)
        except Exception as e:
            logger.warning("Failed to increment job stats for %s: %s", agent_id, e)


# ─── Entry Point ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-25s  %(levelname)-7s  %(message)s",
    )
    uvicorn.run(app, host=HUB_HOST, port=HUB_PORT)
