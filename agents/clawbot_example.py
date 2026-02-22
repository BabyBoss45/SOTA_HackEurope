"""
ClawBot Example — SDK-based External Agent

Demonstrates how to build a ClawBot that integrates with the SOTA marketplace.
Uses the sota_sdk package (same SDK used by SDKHackathonAgent).

To register your ClawBot:
    1. Start this server:  python clawbot_example.py
    2. Expose it via ngrok or deploy to a public HTTPS URL
    3. POST to /api/agents/external/register with your endpoint

Protocol:
    GET  /health          — built in by sota_sdk.server.create_app()
    GET  /status          — built in by sota_sdk.server.create_app()
    POST /bid_request     — receives job, uses DefaultBidStrategy.evaluate()
    POST /execute         — receives execution token, runs task, calls back
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sota_sdk import SOTAAgent, Job, DefaultBidStrategy
from sota_sdk.chain.wallet import AgentWallet

logger = logging.getLogger(__name__)

# The SOTA marketplace platform URL — update for production
SOTA_API_URL = os.getenv('SOTA_API_URL', 'https://sota-web.vercel.app')


# ─── Pydantic models for incoming HTTP requests ───────────────

class BidRequestPayload(BaseModel):
    jobId: str
    description: str
    tags: list[str]
    budgetUsdc: float
    metadata: dict[str, Any] = {}


class ExecutePayload(BaseModel):
    jobId: str
    executionToken: str
    metadata: dict[str, Any] = {}


# ─── ClawBot Agent ────────────────────────────────────────────

class ClawRetailBot(SOTAAgent):
    """
    Example retail ClawBot that handles ecommerce checkout and price scraping.

    Subclasses SOTAAgent from sota_sdk — exactly like SDKHackathonAgent.
    """

    name = "claw-retail-bot"
    description = "Browser automation for ecommerce checkout and price comparison"
    tags = ["ecommerce_checkout", "price_scrape", "form_fill"]
    version = "1.0.0"

    # DefaultBidStrategy from sota_sdk: bids at 85% of budget, min 1.0 USDC
    bid_strategy = DefaultBidStrategy(
        price_ratio=0.85,
        default_eta_seconds=90,
        min_budget_usdc=1.0,
    )

    async def setup(self) -> None:
        """Called by SOTAAgent.run() before the server starts."""
        # Optionally initialise tools here (playwright, requests, etc.)
        logger.info("ClawRetailBot setup complete")

    async def execute(self, job: Job) -> dict:
        """
        Called by the SDK WebSocket hub path (if connected to /hub).
        For the HTTP external protocol, execution is driven by /execute below.
        """
        return {"success": True, "job_id": job.id, "note": "via WebSocket hub"}

    def register_routes(self, app: FastAPI) -> None:
        """
        Add /bid_request and /execute HTTP endpoints to the SDK's FastAPI app.
        /health and /status are already provided by sota_sdk.server.create_app().
        """
        bot = self  # capture self for closures

        @app.post("/bid_request")
        async def handle_bid_request(req: BidRequestPayload):
            """
            Receive a bid invitation from the SOTA platform and respond with
            a bid price computed by DefaultBidStrategy.evaluate().
            """
            job = Job(
                id=req.jobId,
                description=req.description,
                tags=req.tags,
                budget_usdc=req.budgetUsdc,
                deadline_ts=int(time.time()) + 3600,
                poster="",
                params=req.metadata,
            )

            # Use the SDK's DefaultBidStrategy to decide whether/how to bid
            bot.bid_strategy.set_agent_tags(bot.tags)
            bid = await bot.bid_strategy.evaluate(job)

            if bid is None:
                # SDK strategy returned None — agent declines this job
                raise HTTPException(status_code=400, detail="Declining job")

            return {
                "bidPrice": bid.amount_usdc,
                "confidence": 0.80,  # replace with real confidence estimate
                "estimatedTimeSec": bid.estimated_seconds,
                "riskFactors": [],   # e.g. ["captcha_possible"]
            }

        @app.post("/execute")
        async def handle_execute(req: ExecutePayload):
            """
            Receive the execution token after winning a bid.
            Execute the task asynchronously and call back with the result.
            """
            # Accept immediately and execute in background
            asyncio.create_task(
                bot._execute_and_callback(req.jobId, req.executionToken, req.metadata)
            )
            return {"accepted": True}

    async def _execute_and_callback(
        self,
        job_id: str,
        execution_token: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Run the actual task and POST the result back to the SOTA callback endpoint.
        """
        start_ms = int(time.time() * 1000)
        result: dict[str, Any]

        try:
            # ── YOUR TASK EXECUTION LOGIC HERE ────────────────
            # Example: use Playwright to checkout, scrape prices, fill forms, etc.
            # result = await self._run_playwright_task(metadata)
            result = {"success": True, "proof": {"note": "task completed"}}
        except Exception as exc:
            logger.error("ClawRetailBot execution failed for job %s: %s", job_id, exc)
            result = {"success": False, "failure_type": "other"}

        execution_time_ms = int(time.time() * 1000) - start_ms

        callback_payload = {
            "jobId": job_id,
            "executionToken": execution_token,
            "result": {
                "success": result.get("success", False),
                "failure_type": result.get("failure_type"),
                "execution_time_ms": execution_time_ms,
                "proof": result.get("proof"),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{SOTA_API_URL}/api/marketplace/external/execute",
                    json=callback_payload,
                )
                resp.raise_for_status()
                logger.info(
                    "Callback delivered for job %s: %s",
                    job_id, resp.json(),
                )
        except Exception as exc:
            logger.error("Callback failed for job %s: %s", job_id, exc)


# ─── Entry point ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Optional: load wallet for USDC payments (AgentWallet from sota_sdk)
    private_key = os.getenv("CLAWBOT_PRIVATE_KEY")
    if private_key:
        wallet = AgentWallet(private_key)
        logger.info("Wallet loaded: %s", wallet.address[:8] + "...")

    # SOTAAgent.run() creates the FastAPI app via create_app(), calls setup(),
    # calls register_routes(), then starts Uvicorn.
    ClawRetailBot.run(port=int(os.getenv("PORT", "8080")))
