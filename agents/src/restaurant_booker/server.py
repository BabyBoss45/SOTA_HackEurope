"""
Restaurant Booker Agent Server

FastAPI server exposing health, status, and direct booking endpoints.
"""

import os
import json
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

from .agent import RestaurantBookerAgent, create_restaurant_booker_agent
from ..shared.base_agent import ActiveJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent: RestaurantBookerAgent = None


class BookingRequest(BaseModel):
    date: str
    time: str = ""
    cuisine: str = ""
    location: str = ""
    party_size: int = 2
    restaurant_name: str = ""
    user_id: str = "default"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    logger.info("Starting SOTA Restaurant Booker Agent...")
    agent = await create_restaurant_booker_agent()
    yield
    if agent:
        agent.stop()
    logger.info("Restaurant Booker Agent stopped")


app = FastAPI(
    title="SOTA Restaurant Booker Agent",
    description="Smart restaurant booking agent for SOTA on Base",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "restaurant_booker"}


@app.get("/status")
async def get_status():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.get_status()


@app.post("/book")
async def book_restaurant(req: BookingRequest):
    """Direct restaurant booking endpoint (bypasses JobBoard)."""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    prompt = (
        f"Book dinner on {req.date}"
        + (f" at {req.time}" if req.time else "")
        + (f", {req.cuisine} cuisine" if req.cuisine else "")
        + (f" near {req.location}" if req.location else "")
        + (f" for {req.party_size} people" if req.party_size != 2 else "")
        + (f" at {req.restaurant_name}" if req.restaurant_name else "")
        + "."
    )

    try:
        result = await agent.llm_agent.run(prompt)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Booking failed: %s", e)
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
            job_type=12,
            description=params.get("description", "Book a restaurant"),
            budget=params.get("budget", 500_000),
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
    port = int(os.getenv("RESTAURANT_AGENT_PORT", "3008"))
    logger.info("Restaurant Booker Agent listening on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
