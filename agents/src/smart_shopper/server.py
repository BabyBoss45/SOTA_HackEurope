"""
Smart Shopper Agent Server

FastAPI server exposing health, status, and direct shopping endpoints.
"""

import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn

from ..shared.a2a import (
    A2AMessage,
    A2AMethod,
    A2AErrorCode,
    create_error_response,
    create_success_response,
)

from .agent import SmartShopperAgent, create_smart_shopper_agent
from ..shared.base_agent import ActiveJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent: SmartShopperAgent = None


class ShoppingRequest(BaseModel):
    product_query: str
    max_budget: float = 0.0
    currency: str = "GBP"
    urgency: str = "medium"
    preferred_retailers: str = ""
    user_id: str = "default"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    logger.info("Starting SOTA Smart Shopper Agent...")
    agent = await create_smart_shopper_agent()

    # Connect to marketplace Hub
    from ..shared.hub_connector import HubConnector
    connector = HubConnector(agent)
    hub_task = asyncio.create_task(connector.run())

    yield

    connector.stop()
    hub_task.cancel()
    if agent:
        agent.stop()
    logger.info("Smart Shopper Agent stopped")


app = FastAPI(
    title="SOTA Smart Shopper Agent",
    description="Smart shopping agent with economic reasoning for SOTA on Base",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "smart_shopper"}


@app.get("/status")
async def get_status():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.get_status()


@app.post("/shop")
async def smart_shop(req: ShoppingRequest):
    """Direct shopping endpoint (bypasses JobBoard)."""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    prompt = (
        f"Find the best deal for: {req.product_query}"
        + (f" under {req.max_budget} {req.currency}" if req.max_budget else "")
        + (f". Urgency: {req.urgency}" if req.urgency != "medium" else "")
        + (f". Preferred retailers: {req.preferred_retailers}" if req.preferred_retailers else "")
        + "."
    )

    try:
        result = await agent.llm_agent.run(prompt)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Shopping search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/rpc")
async def rpc(request: Request):
    try:
        body = await request.json()
        msg = A2AMessage(**body)
    except Exception:
        return create_error_response("unknown", A2AErrorCode.INVALID_REQUEST, "Invalid A2A message")

    if msg.method == A2AMethod.EXECUTE:
        params = msg.params or {}
        job = ActiveJob(
            job_id=params.get("job_id", 0),
            bid_id=0,
            job_type=8,
            description=params.get("description", "Find best deal"),
            budget=params.get("budget", 2_000_000),
            deadline=params.get("deadline", 0),
        )
        result = await agent.execute_job(job)
        return create_success_response(msg.id, result)
    elif msg.method == A2AMethod.STATUS:
        return create_success_response(msg.id, agent.get_status())
    elif msg.method == A2AMethod.HEALTH:
        return create_success_response(msg.id, {"status": "healthy"})
    else:
        return create_error_response(msg.id, A2AErrorCode.METHOD_NOT_FOUND, f"Unknown method: {msg.method}")


def run_server():
    port = int(os.getenv("SHOPPER_AGENT_PORT", "3010"))
    logger.info("Smart Shopper Agent listening on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
