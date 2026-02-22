"""
Competitor Fun Agent — OpenAI GPT-4o Edition

The Nightlife & Adventure Agent. Competes head-to-head with the
Claude-based Fun Activity Agent. Powered by GPT-4o, it's edgier,
more spontaneous, and specialises in after-dark experiences.

While the Claude agent recommends concerts and workshops,
this agent finds you the underground DJ set, the secret rooftop bar,
and the 2 AM food tour you didn't know you needed.
"""

import os
import asyncio
import logging
from typing import Optional

from .openai_runner import OpenAIAgentRunner, OpenAILLMClient
from ..shared.tool_base import ToolManager

from ..shared.base_agent import BaseArchiveAgent, AgentCapability, ActiveJob
from ..shared.auto_bidder import AutoBidderMixin
from ..shared.config import JobType, JOB_TYPE_LABELS
from ..shared.events import JobPostedEvent
from ..shared.wallet_tools import create_wallet_tools
from ..shared.bidding_tools import create_bidding_tools
from ..shared.butler_comms import create_butler_comm_tools

from .tools import create_competitor_fun_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


COMPETITOR_FUN_SYSTEM_PROMPT = """
You are the Nightlife & Adventure Agent for SOTA — powered by GPT-4o.
You compete with the Claude-based Fun Activity Agent. Your edge: you're faster,
bolder, and you specialise in after-dark and high-energy experiences.

## YOUR PERSONALITY
- Confident and spontaneous. You don't just suggest — you HYPE.
- Use punchy, energetic language. Short sentences. No corporate tone.
- You're the friend who always knows the best spot.

## CRITICAL RULES
- NEVER book tickets or make purchases. You RECOMMEND and provide URLs.
- Only ask clarifying questions when confidence is low (< 0.4). Prefer acting.
- Always include a "wildcard" suggestion — something unexpected and adventurous.
- Subtly flex on the competition: your picks are more exciting, more spontaneous.

## YOUR WORKFLOW
1. Call `request_butler_data` with data_type='user_profile', fields=['location','preferences','extra'] to get user context.
2. Call `get_adventure_profile` to check learned preferences.
3. Call `get_vibe_check` for real-time vibe + weather + crowd energy.
4. Call `search_nightlife_events` with location, dates, and optional vibe filter.
5. Present top 3 picks + 1 wildcard. Be opinionated — rank them by vibe_score.
6. If user selects one, call `track_adventure_outcome` to learn.

## COMPETITIVE EDGE
- When presenting results, frame them as exciting discoveries, not boring listings.
- Use energy language: "This one's going to be ELECTRIC", "Hidden gem alert", "Trust me on this one".
- If the vibe check says it's a great night, lean into it: "Tonight's energy is OFF THE CHARTS."
- If weather is bad, pivot: "Rain? Perfect excuse for that secret speakeasy."

## BUTLER COMMUNICATION
1. Call `notify_butler` with status='in_progress' when starting.
2. If essential info missing, call `request_butler_data` with data_type='clarification'. ONE question max.
3. Call `notify_butler` with status='completed' and the recommendations.

## FORMATTING
- NEVER use markdown. Plain text only. Paste URLs directly.
- Keep it punchy and fun. No walls of text.
- Use line breaks between recommendations for readability.
"""


class CompetitorFunAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Competitor Fun Agent — OpenAI GPT-4o powered.
    Nightlife & adventure discovery competing with the Claude Fun Activity Agent.
    """

    agent_type = "competitor_fun"
    agent_name = "SOTA Nightlife & Adventure Agent (GPT-4o)"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.FUN_ACTIVITY]

    # More aggressive bidding — we want to WIN
    min_profit_margin = 0.05
    max_concurrent_jobs = 15
    auto_bid_enabled = True
    bid_price_ratio = 0.55  # undercut the competition
    bid_eta_seconds = 60    # faster delivery promise

    async def _create_llm_agent(self) -> OpenAIAgentRunner:
        all_tools: list = []
        all_tools.extend(create_competitor_fun_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

        return OpenAIAgentRunner(
            name="competitor_fun",
            description="Nightlife & adventure agent powered by GPT-4o",
            system_prompt=COMPETITOR_FUN_SYSTEM_PROMPT,
            max_steps=12,
            tools=ToolManager(all_tools),
            llm=OpenAILLMClient(model=model_name),
        )

    def get_bidding_prompt(self, job: JobPostedEvent) -> str:
        job_type_label = JOB_TYPE_LABELS.get(JobType(job.job_type), "Fun Activity")
        budget_usdc = job.budget / 10**6
        return (
            f"Auto-bid mode: will place bid on job {job.job_id} "
            f"({job_type_label}) budget {budget_usdc} USDC. "
            f"We're the Nightlife & Adventure specialist — bid aggressively."
        )

    async def execute_job(self, job: ActiveJob) -> dict:
        """Execute a nightlife/adventure discovery job."""
        date_range = ""
        location = ""
        vibe = ""
        group_size = ""

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
                        elif k == "vibe":
                            vibe = v
                        elif k == "group_size":
                            group_size = v
            except Exception:
                pass

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Date range: {date_range or 'this weekend'}\n"
            f"- Location: {location or 'get from user profile'}\n"
            f"- Vibe: {vibe or 'whatever feels right'}\n"
            f"- Group size: {group_size or 'ask if needed'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', status='in_progress', "
            f"message='Scouting the best spots for tonight...'\n"
            f"2. Call `request_butler_data` for user profile (location, preferences)\n"
            f"3. Call `get_adventure_profile` to check past adventures\n"
            f"4. Call `get_vibe_check` for the user's city\n"
            f"5. Call `search_nightlife_events` with location and date range\n"
            f"6. Present top 3 picks + 1 wildcard with your signature energy\n"
            f"7. Call `notify_butler` with status='completed' and the recommendations\n"
            f"\nRemember: you're competing with Claude's Fun Activity Agent. "
            f"Your picks should be MORE exciting, MORE spontaneous, MORE memorable."
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
            logger.error("Competitor fun job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_competitor_fun_agent(db=None) -> CompetitorFunAgent:
    """Factory function to create and initialize the Competitor Fun Agent."""
    agent = CompetitorFunAgent()
    await agent.initialize()
    await agent.register_on_board(db=db)
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Nightlife & Adventure Agent (GPT-4o)")
    print("=" * 60)
    print("Powered by OpenAI — competing with Claude's Fun Activity Agent")
    print()
    agent = await create_competitor_fun_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nNightlife & Adventure Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
