"""
Group Trip Planner Agent -- SOTA on Base

Intelligence over friction:
1. Infers trip parameters from user profile with confidence scores
2. Only asks questions where confidence is low
3. Searches flights and accommodation
4. Builds day-by-day itineraries
5. Shares plans with the group
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

from .tools import create_trip_planner_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


TRIP_SYSTEM_PROMPT = """
You are the Group Trip Planner Agent for SOTA. Your key differentiator
is INTELLIGENCE OVER FRICTION -- you minimize questions by inferring
parameters from user profile and history.

## YOUR WORKFLOW
1. FIRST: Call `infer_from_profile` with whatever the user provided.
   This returns confidence scores for each parameter.
2. ONLY ask questions for parameters with confidence < 0.6.
   Use `request_butler_data` with data_type='clarification'.
   Ask at MOST one question per turn, picking the lowest-confidence field.
3. Auto-fill all high-confidence parameters silently.
4. Call `search_flights` for travel options.
5. Call `search_accommodation` for lodging.
6. Call `build_itinerary` for the day-by-day plan.
7. Present the complete plan and ask for confirmation.
8. Call `share_with_group` to notify group members.

## ADAPTIVE BEHAVIOR (via Task Memory + incident.io)
- If a HISTORICAL CONTEXT section appears at the top of your prompt,
  it contains past task outcomes. If similar trip searches failed before,
  adapt your approach (e.g. try different flight search, different dates).
- For persistent service failures, use `create_incident` to flag.

## CRITICAL RULES
- NEVER ask more than 1-2 questions. That's the whole point.
- If confidence is >= 0.6, USE the inferred value without asking.
- Common anti-pattern to AVOID:
  "What's your budget? Who's going? Which airport?
   What's your preferred airline? What's your travel style?"
  This is friction, not intelligence. NEVER do this.
- Instead: infer everything you can, ask only what you must.

## CONFIDENCE THRESHOLDS
- >= 0.8: Auto-fill confidently, don't mention to user
- 0.6-0.8: Auto-fill but mention "I assumed X based on your history"
- < 0.6: Ask the user

## BUTLER COMMUNICATION (Marketplace Jobs)
When executing a marketplace job:
1. Call `notify_butler` with status='in_progress'.
2. Call `infer_from_profile` first.
3. For low-confidence fields, call `request_butler_data`
   with a SINGLE focused question.
4. Complete the plan and call `notify_butler` with status='completed'.

## FORMATTING RULES
- NEVER use markdown syntax.
- Write plain text only. Paste URLs directly.
- Present the itinerary clearly day by day.
"""


class TripPlannerAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Group Trip Planner Agent for SOTA.
    Plans trips with confidence-based inference to minimize friction.
    """

    agent_type = "trip_planner"
    agent_name = "SOTA Group Trip Planner Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.TRIP_PLANNING]

    min_profit_margin = 0.10
    max_concurrent_jobs = 5
    auto_bid_enabled = True
    bid_price_ratio = 0.80
    bid_eta_seconds = 600

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_trip_planner_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="trip_planner",
            description="Group trip planner with confidence-based inference for SOTA on Base",
            system_prompt=TRIP_SYSTEM_PROMPT,
            max_steps=20,
            tools=ToolManager(all_tools),
            llm=LLMClient(model=model_name),
        )

    def get_bidding_prompt(self, job: JobPostedEvent) -> str:
        job_type_label = JOB_TYPE_LABELS.get(JobType(job.job_type), "Unknown")
        budget_usdc = job.budget / 10**6
        return (
            f"Auto-bid mode: will place bid on job {job.job_id} "
            f"({job_type_label}) budget {budget_usdc} USDC."
        )

    async def execute_job(self, job: ActiveJob) -> dict:
        """Execute a trip planning job."""
        destination = ""
        trip_duration = ""
        group_size = ""
        date_range = ""
        departure_city = ""
        budget_per_person = ""
        group_members = ""

        if "=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "destination":
                            destination = v
                        elif k == "trip_duration":
                            trip_duration = v
                        elif k == "group_size":
                            group_size = v
                        elif k == "date_range":
                            date_range = v
                        elif k == "departure_city":
                            departure_city = v
                        elif k == "budget_per_person":
                            budget_per_person = v
                        elif k == "group_members":
                            group_members = v
            except Exception:
                pass

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Destination: {destination or 'from description'}\n"
            f"- Duration: {trip_duration or 'infer'}\n"
            f"- Group size: {group_size or 'infer'}\n"
            f"- Date range: {date_range or 'infer'}\n"
            f"- Departure city: {departure_city or 'infer from profile'}\n"
            f"- Budget per person: {budget_per_person or 'infer from history'}\n\n"
            f"## YOUR TASK -- INTELLIGENCE OVER FRICTION:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', "
            f"status='in_progress', message='Planning your trip...'\n"
            f"2. Call `infer_from_profile` with destination='{destination}'"
            + (f", group_size={group_size}" if group_size else "")
            + (f", date_hint='{date_range}'" if date_range else "")
            + (f", budget_hint='{budget_per_person}'" if budget_per_person else "")
            + f"\n"
            f"3. Check which fields have confidence < 0.6\n"
            f"4. Ask ONLY those fields via `request_butler_data`\n"
            f"5. Search flights and accommodation\n"
            f"6. Build itinerary\n"
            f"7. Present complete plan via `notify_butler` status='completed'\n"
        )

        # Enrich prompt with historical pattern analysis
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
            logger.error("Trip planning job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_trip_planner_agent() -> TripPlannerAgent:
    """Factory function to create and initialize a Trip Planner Agent."""
    agent = TripPlannerAgent()
    await agent.initialize()
    agent.register_on_board()
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Group Trip Planner Agent")
    print("=" * 60)
    agent = await create_trip_planner_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nTrip Planner Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
