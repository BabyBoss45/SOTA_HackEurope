"""
Fun Activity Agent — SOTA

Finds something fun with zero friction. Uses location, calendar, budget,
and past events to recommend concerts, workshops, exhibitions, comedy, and more.
Learns preferences over time. Minimal clarification — only asks when confidence low.
"""

import os
import asyncio
import logging
from typing import Optional

from ..shared.agent_runner import AgentRunner, LLMClient
from ..shared.tool_base import ToolManager

from ..shared.base_agent import BaseArchiveAgent, AgentCapability, ActiveJob
from ..shared.auto_bidder import AutoBidderMixin
from ..shared.config import JobType, JOB_TYPE_LABELS
from ..shared.events import JobPostedEvent
from ..shared.wallet_tools import create_wallet_tools
from ..shared.bidding_tools import create_bidding_tools
from ..shared.butler_comms import create_butler_comm_tools

from .tools import create_fun_activity_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


FUN_ACTIVITY_SYSTEM_PROMPT = """
You are the Fun Activity Agent for SOTA. Find something fun with minimal friction.

## CRITICAL RULES
- NEVER book tickets or make purchases. You RECOMMEND events and provide URLs.
- Only ask clarifying questions when confidence is low (< 0.5). Prefer acting with context.
- Use contextual, intelligent phrasing: "You've enjoyed live indie gigs before and you're free Saturday evening. There's a small Soho show within 20 minutes and under your usual £40 range."

## YOUR WORKFLOW
1. Call `request_butler_data` with data_type='user_profile', fields=['location','preferences','extra'] to get user context.
2. Call `get_event_preferences` to check learned preferences.
3. Call `get_weather` for weather-aware suggestions (push indoor if rain).
4. Call `search_local_events` with location, date range, and optional categories.
5. Present top 3 recommendations + 1 optional wildcard. Be contextual, not generic.
6. If user selects one, call `persist_event_outcome` to learn.

## ADAPTIVE BEHAVIOR
- If HISTORICAL CONTEXT appears, adapt to avoid past failures.
- Weather: rain/snow → prioritize indoor events.
- Budget: use learned budget_ceiling from preferences.
- Avoid event types user repeatedly ignored (from event_history).

## BUTLER COMMUNICATION
1. Call `notify_butler` with status='in_progress' when starting.
2. If essential info missing (e.g. no location), call `request_butler_data` with data_type='clarification'. Ask ONE short question max.
3. Call `notify_butler` with status='completed' and the recommendations.

## FORMATTING
- NEVER use markdown. Plain text only. Paste URLs directly.
- Keep output concise and fun.
"""


class FunActivityAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Fun Activity Agent for SOTA.
    Event discovery with preference learning and weather adaptation.
    """

    agent_type = "fun_activity"
    agent_name = "SOTA Fun Activity Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.FUN_ACTIVITY]

    min_profit_margin = 0.10
    max_concurrent_jobs = 10
    auto_bid_enabled = True
    bid_price_ratio = 0.65
    bid_eta_seconds = 90

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_fun_activity_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="fun_activity",
            description="Fun event discovery agent for SOTA",
            system_prompt=FUN_ACTIVITY_SYSTEM_PROMPT,
            max_steps=12,
            tools=ToolManager(all_tools),
            llm=LLMClient(model=model_name),
        )

    def get_bidding_prompt(self, job: JobPostedEvent) -> str:
        job_type_label = JOB_TYPE_LABELS.get(JobType(job.job_type), "Fun Activity")
        budget_usdc = job.budget / 10**6
        return (
            f"Auto-bid mode: will place bid on job {job.job_id} "
            f"({job_type_label}) budget {budget_usdc} USDC."
        )

    async def execute_job(self, job: ActiveJob) -> dict:
        """Execute a fun activity discovery job."""
        date_range = ""
        location = ""
        surprise_mode = ""
        last_minute = ""

        if "=" in job.description or ":" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "date_range":
                            date_range = v
                        elif k == "location":
                            location = v
                        elif k == "surprise_mode":
                            surprise_mode = v
                        elif k == "last_minute":
                            last_minute = v
            except Exception:
                pass

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Date range: {date_range or 'this weekend'}\n"
            f"- Location: {location or 'get from user profile'}\n"
            f"- Surprise mode: {surprise_mode or 'false'}\n"
            f"- Last minute: {last_minute or 'false'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', status='in_progress', message='Finding something fun...'\n"
            f"2. Call `request_butler_data` for user profile (location, preferences)\n"
            f"3. Call `get_event_preferences` to check learned preferences\n"
            f"4. Call `get_weather` for the user's location\n"
            f"5. Call `search_local_events` with location and date range\n"
            f"6. Present top 3 recommendations + 1 wildcard with contextual messaging\n"
            f"7. Call `notify_butler` with status='completed' and the recommendations\n"
        )

        pattern_analysis = getattr(job, "params", {}).get("pattern_analysis")
        if pattern_analysis:
            from ..shared.task_memory import build_adaptation_prompt
            adaptation = build_adaptation_prompt(pattern_analysis)
            if adaptation:
                prompt = adaptation + prompt

        try:
            if self.llm_agent:
                result = await self.llm_agent.run(prompt)
                return {"success": True, "result": result, "job_id": job.job_id}
            return {"success": False, "error": "LLM agent not initialized", "job_id": job.job_id}
        except Exception as e:
            logger.error("Fun activity job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_fun_activity_agent() -> FunActivityAgent:
    """Factory function to create and initialize a Fun Activity Agent."""
    agent = FunActivityAgent()
    await agent.initialize()
    agent.register_on_board()
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Fun Activity Agent")
    print("=" * 60)
    agent = await create_fun_activity_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nFun Activity Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
