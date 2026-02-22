"""
Restaurant Booker Agent -- SOTA on Base

Smart restaurant booking agent that:
1. Checks calendar for free evening slots
2. Searches nearby restaurants matching learned preferences
3. Books a table with minimal user input
4. Learns cuisine preferences and avoids cancelled places
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

from .tools import create_restaurant_booker_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


RESTAURANT_SYSTEM_PROMPT = """
You are the Restaurant Booker Agent for SOTA, specializing in finding
the best restaurant options for users.

## CRITICAL SAFETY RULE
You NEVER make reservations, provide credit card details, or place bookings
directly. You find the best restaurant and provide its details (name, URL,
phone number). A separate Caller Agent will phone the venue to secure the
booking -- no card is ever given over the phone.

## YOUR WORKFLOW
1. Call `learn_preferences` to see the user's cuisine history and avoided places.
2. Call `check_calendar` to find free evening slots on the requested date.
3. Call `search_restaurants` with the user's location, preferences, and the free time slot.
4. Present the top match(es) to the user with restaurant name, URL, and phone number.
5. Call `make_reservation` to record the user's booking intent for preference learning.
6. Call `notify_butler` with status='completed' and the restaurant details.
   Include the venue phone number so the Caller Agent can phone to confirm the booking.

## ADAPTIVE BEHAVIOR (via Task Memory + incident.io)
- If a HISTORICAL CONTEXT section appears at the top of your prompt,
  it contains past task outcomes. Use it to adapt your approach.
- If no cuisine is specified, use learned preferences to pick.
- Default party size to 2 unless history suggests otherwise.
- Never suggest a restaurant the user previously cancelled.
- Pick a time slot that's free on their calendar.
- If the user just says "Book dinner Friday" with no details, infer
  everything you can and only ask what you absolutely must.
- For persistent booking failures, use `create_incident` to flag.

## BUTLER COMMUNICATION (Marketplace Jobs)
When executing a marketplace job:
1. Call `notify_butler` with status='in_progress' when starting.
2. If you need essential info (e.g. location unknown), call `request_butler_data`
   with data_type='clarification'. Ask ONE question at most.
3. Call `notify_butler` with status='completed' and the restaurant details
   including phone number for the Caller Agent.

## FORMATTING RULES
- NEVER use markdown syntax.
- Write plain text only. Paste URLs directly.
- Keep output concise.
"""


class RestaurantBookerAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Restaurant Booker Agent for SOTA.
    Books restaurants with calendar awareness and preference learning.
    """

    agent_type = "restaurant_booker"
    agent_name = "SOTA Restaurant Booker Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.RESTAURANT_BOOKING_SMART]

    min_profit_margin = 0.10
    max_concurrent_jobs = 10
    auto_bid_enabled = True
    bid_price_ratio = 0.70
    bid_eta_seconds = 90

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_restaurant_booker_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

        return AgentRunner(
            name="restaurant_booker",
            description="Smart restaurant booking agent for SOTA on Base",
            system_prompt=RESTAURANT_SYSTEM_PROMPT,
            max_steps=12,
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
        """Execute a restaurant booking job."""
        date = ""
        time = ""
        cuisine = ""
        location = ""
        party_size = ""
        restaurant_name = ""

        if "date=" in job.description or "=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "date":
                            date = v
                        elif k == "time":
                            time = v
                        elif k == "cuisine":
                            cuisine = v
                        elif k == "location":
                            location = v
                        elif k == "party_size":
                            party_size = v
                        elif k == "restaurant_name":
                            restaurant_name = v
            except Exception:
                pass

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Date: {date or 'infer from description'}\n"
            f"- Time: {time or 'find a free slot'}\n"
            f"- Cuisine: {cuisine or 'use preferences'}\n"
            f"- Location: {location or 'ask if needed'}\n"
            f"- Party size: {party_size or 'use typical'}\n"
            f"- Restaurant: {restaurant_name or 'find best match'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', "
            f"status='in_progress', message='Finding the perfect restaurant...'\n"
            f"2. Call `learn_preferences` to check cuisine history\n"
            f"3. Call `check_calendar` for the requested date\n"
            f"4. Call `search_restaurants` with location and preferences\n"
            f"5. Call `make_reservation` to record the booking intent for preference learning\n"
            f"6. Call `notify_butler` with status='completed' and restaurant details "
            f"including the venue phone number so the Caller Agent can phone to confirm\n"
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
            logger.error("Restaurant booking job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_restaurant_booker_agent(db=None) -> RestaurantBookerAgent:
    """Factory function to create and initialize a Restaurant Booker Agent."""
    agent = RestaurantBookerAgent()
    await agent.initialize()
    await agent.register_on_board(db=db)
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Restaurant Booker Agent")
    print("=" * 60)
    agent = await create_restaurant_booker_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nRestaurant Booker Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
