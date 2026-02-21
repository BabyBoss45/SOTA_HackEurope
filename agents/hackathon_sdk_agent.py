"""
SDK-based Hackathon Agent for SOTA.

Subclasses SOTAAgent from the SOTA SDK and reuses all existing hackathon
tools and LLM logic.  Drop-in replacement for the legacy
``src/hackathon/agent.py`` + ``src/hackathon/server.py`` stack.

Usage:
    cd agents && python hackathon_sdk_agent.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure the ``agents/`` package root is importable so we can reach
# ``src.hackathon.tools``, ``src.shared.*``, etc.
# ---------------------------------------------------------------------------
_AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _AGENTS_DIR not in sys.path:
    sys.path.insert(0, _AGENTS_DIR)

from sota_sdk import SOTAAgent, Job, DefaultBidStrategy
from src.shared.agent_runner import AgentRunner, LLMClient
from src.shared.tool_base import ToolManager
from src.hackathon.tools import create_hackathon_tools, SearchHackathonsTool
from src.hackathon.registration_tools import create_registration_tools
from src.shared.butler_comms import create_butler_comm_tools

# Import the system prompt from the legacy agent
from src.hackathon.agent import HACKATHON_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response models (same as legacy server.py)
# ---------------------------------------------------------------------------

class HackathonSearchRequest(BaseModel):
    location: str = "anywhere"
    date_from: str | None = None
    date_to: str | None = None
    topics: str | None = None
    mode: str = "both"
    keywords: str | None = None
    user_profile: dict | None = None


class HackathonRegisterRequest(BaseModel):
    hackathon_url: str
    user_profile: dict | None = None
    dry_run: bool = True


# ---------------------------------------------------------------------------
# SDKHackathonAgent
# ---------------------------------------------------------------------------

class SDKHackathonAgent(SOTAAgent):
    """
    Hackathon search & registration agent built on the SOTA SDK.

    Reuses every existing tool from the legacy hackathon agent but relies
    on the SDK for WebSocket marketplace connectivity, bidding, delivery
    proof, and the embedded FastAPI server.
    """

    name = "hackathon-agent"
    description = "Searches for upcoming hackathons and handles registration"
    tags = ["hackathon_registration"]
    version = "2.0.0"
    bid_strategy = DefaultBidStrategy(
        price_ratio=0.70,
        default_eta_seconds=120,
        min_budget_usdc=0.50,
    )

    # -- Lifecycle -----------------------------------------------------------

    async def setup(self) -> None:
        """Initialise the LLM agent runner with hackathon + registration + butler tools."""
        all_tools: list = []
        all_tools.extend(create_hackathon_tools())
        all_tools.extend(create_registration_tools())
        all_tools.extend(create_butler_comm_tools(agent_name="hackathon"))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        self._runner = AgentRunner(
            name="hackathon",
            description="Hackathon search & registration agent for SOTA on Base",
            system_prompt=HACKATHON_SYSTEM_PROMPT,
            max_steps=15,
            tools=ToolManager(all_tools),
            llm=LLMClient(model=model_name),
        )
        logger.info("AgentRunner initialised with %d tools", len(all_tools))

    # -- Job execution -------------------------------------------------------

    async def execute(self, job: Job) -> dict:
        """Process a marketplace job (search or registration)."""
        desc_lower = job.description.lower()
        is_registration = any(
            kw in desc_lower
            for kw in ["register", "sign up", "sign me up", "enroll", "rsvp"]
        )

        # Extract structured params (same parsing as legacy execute_job)
        location, date_from, keywords = self._parse_search_params(job)

        if is_registration:
            prompt = self._build_registration_prompt(job)
        else:
            prompt = self._build_search_prompt(job, location, date_from, keywords)

        # Enrich with historical pattern analysis if present
        pattern_analysis = job.params.get("_pattern_analysis")
        if pattern_analysis:
            try:
                from src.shared.task_memory import build_adaptation_prompt
                adaptation = build_adaptation_prompt(pattern_analysis)
                if adaptation:
                    prompt = adaptation + prompt
            except ImportError:
                pass

        try:
            result = await self._runner.run(prompt)

            # Fallback search if LLM returned no useful results
            if not is_registration and self._looks_like_no_results(result):
                logger.warning("LLM returned no results -- running direct search fallback")
                fallback = await self._direct_search_fallback(location, date_from, keywords)
                if fallback:
                    return {
                        "success": True,
                        "hackathons": fallback,
                        "job_id": job.id,
                        "source": "direct_fallback",
                    }

            return {
                "success": True,
                "result": result,
                "job_id": job.id,
            }

        except Exception as e:
            logger.error("Hackathon job %s failed: %s", job.id, e)
            # Last resort: try direct search even on error
            if not is_registration:
                try:
                    fallback = await self._direct_search_fallback(location, date_from, keywords)
                    if fallback:
                        return {
                            "success": True,
                            "hackathons": fallback,
                            "job_id": job.id,
                            "source": "error_fallback",
                        }
                except Exception:
                    pass
            return {
                "success": False,
                "error": str(e),
                "job_id": job.id,
            }

    # -- Custom routes (called by SDK's register_routes hook) ----------------

    def register_routes(self, app: FastAPI) -> None:
        """Add hackathon-specific HTTP endpoints to the SDK FastAPI app."""

        runner = self._runner  # capture for closures

        @app.post("/search")
        async def search_hackathons(req: HackathonSearchRequest):
            if not runner:
                raise HTTPException(status_code=503, detail="Agent not ready")

            # Store user context if provided
            if req.user_profile:
                try:
                    import httpx
                    butler_url = os.getenv("BUTLER_ENDPOINT", "http://localhost:3001")
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            f"{butler_url}/api/agent/set-user-context",
                            json={"user_id": "default", "profile": req.user_profile},
                        )
                except Exception:
                    pass

            topics = req.topics or req.keywords
            parts = ["Search for upcoming hackathons"]
            if req.location and req.location.lower() not in ("anywhere", ""):
                parts.append(f"near {req.location}")
            if req.date_from:
                parts.append(f"from {req.date_from}")
            if req.date_to:
                parts.append(f"to {req.date_to}")
            if topics:
                parts.append(f"related to {topics}")
            if req.mode and req.mode != "both":
                parts.append(f"({req.mode} only)")
            parts.append(". Return a formatted summary of upcoming events only.")

            prompt = " ".join(parts)

            try:
                result = await runner.run(prompt)
                return {"success": True, "result": result}
            except Exception as e:
                logger.error("Search failed: %s", e)
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/register")
        async def register_for_hackathon(req: HackathonRegisterRequest):
            if not runner:
                raise HTTPException(status_code=503, detail="Agent not ready")

            profile_str = json.dumps(req.user_profile) if req.user_profile else "{}"
            dry_label = "DRY RUN -- " if req.dry_run else ""
            prompt = (
                f"{dry_label}Register me for the hackathon at {req.hackathon_url}.\n"
                f"My profile: {profile_str}\n"
                f"dry_run={'true' if req.dry_run else 'false'}"
            )

            try:
                result = await runner.run(prompt)
                return {"success": True, "dry_run": req.dry_run, "result": result}
            except Exception as e:
                logger.error("Registration failed: %s", e)
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/v1/rpc")
        async def rpc(request: Request):
            """Agent-to-Agent JSON-RPC endpoint."""
            from src.shared.a2a import (
                A2AMessage,
                A2AMethod,
                A2AErrorCode,
                create_error_response,
                create_success_response,
            )

            try:
                body = await request.json()
                msg = A2AMessage(**body)
            except Exception:
                return create_error_response(
                    0, A2AErrorCode.INVALID_REQUEST, "Invalid A2A message"
                )

            logger.info("A2A request: method=%s id=%s", msg.method, msg.id)

            if msg.method in (A2AMethod.EXECUTE_TASK, "execute"):
                params = msg.params or {}
                description = params.get("description", "Find hackathons")
                sdk_job = Job(
                    id=str(params.get("job_id", 0)),
                    description=description,
                    tags=["hackathon_registration"],
                    budget_usdc=float(params.get("budget", 1.0)),
                    deadline_ts=int(params.get("deadline", 0)),
                    poster=params.get("poster", ""),
                    params=params,
                )
                result = await self.execute(sdk_job)
                return create_success_response(msg.id, result)

            elif msg.method in (A2AMethod.GET_STATUS, "status"):
                return create_success_response(msg.id, {
                    "name": self.name,
                    "version": self.version,
                    "tags": self.tags,
                    "active_jobs": len(self._active_jobs),
                    "connected": (
                        self._ws_client.connected if self._ws_client else False
                    ),
                })

            elif msg.method in (A2AMethod.PING, "health"):
                return create_success_response(msg.id, {"status": "healthy"})

            else:
                return create_error_response(
                    msg.id, A2AErrorCode.METHOD_NOT_FOUND,
                    f"Unknown method: {msg.method}",
                )

        @app.get("/jobs")
        async def get_active_jobs():
            return {
                "active_jobs": list(self._active_jobs.keys()),
                "count": len(self._active_jobs),
            }

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _parse_search_params(job: Job) -> tuple[str, str, str]:
        """Extract location, date_from, keywords from job description or params."""
        location = ""
        date_from = ""
        keywords = ""

        # Try structured params first
        if job.params:
            location = job.params.get("location", "")
            date_from = job.params.get("date_range", job.params.get("date_from", ""))
            keywords = job.params.get("keywords", job.params.get("theme_technology_focus", ""))

        # Fall back to parsing the description string
        if not location and "location=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if k == "location":
                            location = v
                        elif k == "date_range":
                            date_from = v
                        elif k == "theme_technology_focus":
                            keywords = v.strip("[]'\"")
                        elif k == "online_or_in_person":
                            if v == "in_person":
                                keywords = (keywords + " in-person").strip()
            except Exception:
                pass

        return location, date_from, keywords

    @staticmethod
    def _build_search_prompt(job: Job, location: str, date_from: str, keywords: str) -> str:
        prompt = (
            f"You are executing marketplace job #{job.id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED SEARCH PARAMETERS (use these directly):\n"
            f"- Location: {location or 'any'}\n"
            f"- Date range: {date_from or 'upcoming'}\n"
            f"- Keywords: {keywords or 'any'}\n\n"
            f"## YOUR TASK -- MANDATORY STEPS:\n"
            f"1. **IMMEDIATELY** call `search_hackathons` with "
            f"location=\"{location or 'worldwide'}\""
        )
        if date_from:
            prompt += f", date_from/date_to covering {date_from}"
        if keywords and keywords != "any":
            prompt += f", keywords=\"{keywords}\""
        prompt += (
            f".\n"
            f"   Do NOT skip this step. Do NOT wait for user profile data.\n"
            f"2. Call `notify_butler` with job_id='{job.id}', "
            f"status='in_progress', message='Searching for hackathons...'\n"
            f"3. If search returns results, call `format_hackathon_results`.\n"
            f"4. Call `notify_butler` with status='completed' and the results.\n\n"
            f"CRITICAL: You MUST call search_hackathons as your FIRST action. "
            f"The search parameters are already provided above -- do not ask "
            f"the Butler for clarification. Proceed immediately with the search."
        )
        return prompt

    @staticmethod
    def _build_registration_prompt(job: Job) -> str:
        return (
            f"You are executing marketplace job #{job.id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"Task: Register the user for a hackathon.\n\n"
            f"Workflow:\n"
            f"1. Request user profile from Butler (request_butler_data, "
            f"   data_type='user_profile', job_id='{job.id}')\n"
            f"2. Detect the registration form\n"
            f"3. Auto-fill with dry_run=true and notify Butler with results\n"
            f"4. Request confirmation from Butler (data_type='confirmation')\n"
            f"5. If confirmed, submit with dry_run=false\n"
            f"6. Notify Butler with final status (notify_butler status='completed')"
        )

    @staticmethod
    def _looks_like_no_results(text: str) -> bool:
        """Check if the LLM response indicates no hackathons were found."""
        if not text:
            return True
        lower = text.lower()
        no_result_phrases = [
            "couldn't find",
            "could not find",
            "no hackathons",
            "no results",
            "unable to find",
            "didn't find",
            "no matching",
            "try different",
            "step limit",
        ]
        return any(phrase in lower for phrase in no_result_phrases)

    @staticmethod
    async def _direct_search_fallback(
        location: str, date_range: str, keywords: str,
    ) -> list:
        """Bypass the LLM and call the search tool directly as a fallback."""
        results: list = []

        try:
            tool = SearchHackathonsTool()
            raw = await tool.execute(
                location=location or "worldwide",
                keywords=keywords if keywords and keywords != "any" else None,
            )
            data = json.loads(raw)
            if data.get("success") and data.get("hackathons"):
                results.extend(data["hackathons"])
        except Exception as e:
            logger.warning("Direct search tool failed: %s", e)

        # Also try event_finder scrapers
        if len(results) < 3:
            try:
                from event_finder import search_hackathons as scrape_search
                scraped = scrape_search(
                    query=f"hackathons in {location}" if location else "hackathons",
                    location=location,
                    num=5,
                )
                for s in scraped:
                    results.append({
                        "name": s.get("name", ""),
                        "location": s.get("location", ""),
                        "date_start": s.get("date", ""),
                        "date_end": s.get("date", ""),
                        "url": s.get("url", ""),
                        "description": s.get("description", ""),
                        "source": s.get("platform", "scraper"),
                    })
            except Exception as e:
                logger.warning("Event finder scraper failed: %s", e)

        return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SDKHackathonAgent.run(port=3005)
