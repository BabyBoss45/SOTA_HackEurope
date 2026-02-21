"""
Group Trip Planner Agent Server

FastAPI server exposing health, status, and direct planning endpoints.
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

from .agent import TripPlannerAgent, create_trip_planner_agent
from ..shared.base_agent import ActiveJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent: TripPlannerAgent = None


class TripRequest(BaseModel):
    destination: str
    trip_duration: int = 3
    group_size: int = 2
    date_range: str = ""
    departure_city: str = ""
    budget_per_person: float = 0.0
    interests: str = ""
    user_id: str = "default"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    logger.info("Starting SOTA Group Trip Planner Agent...")
    agent = await create_trip_planner_agent()

    # Connect to marketplace Hub
    from ..shared.hub_connector import HubConnector
    connector = HubConnector(agent)
    hub_task = asyncio.create_task(connector.run())

    yield

    connector.stop()
    hub_task.cancel()
    if agent:
        agent.stop()
    logger.info("Trip Planner Agent stopped")


app = FastAPI(
    title="SOTA Group Trip Planner Agent",
    description="Intelligence-over-friction trip planning for SOTA on Base",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "trip_planner"}


@app.get("/status")
async def get_status():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.get_status()


@app.post("/plan")
async def plan_trip(req: TripRequest):
    """Direct trip planning endpoint (bypasses JobBoard)."""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    prompt = (
        f"Plan a {req.trip_duration}-day trip to {req.destination}"
        + (f" for {req.group_size} people" if req.group_size > 1 else "")
        + (f" from {req.departure_city}" if req.departure_city else "")
        + (f" around {req.date_range}" if req.date_range else "")
        + (f", budget ~{req.budget_per_person} per person" if req.budget_per_person else "")
        + (f". Interests: {req.interests}" if req.interests else "")
        + "."
    )

    try:
        result = await agent.llm_agent.run(prompt)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Trip planning failed: %s", e)
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
            job_type=9,
            description=params.get("description", "Plan a group trip"),
            budget=params.get("budget", 3_000_000),
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
    port = int(os.getenv("TRIP_AGENT_PORT", "3011"))
    logger.info("Trip Planner Agent listening on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
