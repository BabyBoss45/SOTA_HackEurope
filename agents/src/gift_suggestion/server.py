"""
Gift Suggestion Agent Server

FastAPI server exposing health, status, and direct suggestion endpoints.
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

from .agent import GiftSuggestionAgent, create_gift_suggestion_agent
from ..shared.base_agent import ActiveJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent: GiftSuggestionAgent = None


class GiftRequest(BaseModel):
    recipient_name: str
    occasion: str = ""
    budget: float = 0.0
    interests: str = ""
    user_id: str = "default"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    logger.info("Starting SOTA Gift Suggestion Agent...")
    agent = await create_gift_suggestion_agent()
    yield
    if agent:
        agent.stop()
    logger.info("Gift Suggestion Agent stopped")


app = FastAPI(
    title="SOTA Gift Suggestion Agent",
    description="Personalized gift recommendation agent for SOTA on Base",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "gift_suggestion"}


@app.get("/status")
async def get_status():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.get_status()


@app.post("/suggest")
async def suggest_gifts(req: GiftRequest):
    """Direct gift suggestion endpoint (bypasses JobBoard)."""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    prompt = (
        f"Suggest a gift for {req.recipient_name}."
        + (f" Occasion: {req.occasion}." if req.occasion else "")
        + (f" Budget: ~{req.budget} GBP." if req.budget else "")
        + (f" Interests: {req.interests}." if req.interests else "")
    )

    try:
        result = await agent.llm_agent.run(prompt)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Suggestion failed: %s", e)
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
            job_type=11,
            description=params.get("description", "Suggest a gift"),
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
    port = int(os.getenv("GIFT_AGENT_PORT", "3007"))
    logger.info("Gift Suggestion Agent listening on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
