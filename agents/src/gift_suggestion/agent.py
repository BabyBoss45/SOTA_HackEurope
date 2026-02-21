"""
Gift Suggestion Agent -- SOTA on Base

Ultra-simple gift recommendation agent that:
1. Analyzes recipients using past gift history
2. Searches for creative, personalized gift ideas
3. Learns price comfort zones and avoids repetition
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

from .tools import create_gift_suggestion_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


GIFT_SYSTEM_PROMPT = """
You are the Gift Suggestion Agent for SOTA, specializing in finding
thoughtful, personalized gift ideas.

## CRITICAL SAFETY RULE
You NEVER purchase or order anything. Your job is to SUGGEST gifts and provide
purchase links. The user decides what to buy and completes the purchase themselves.
Always include the purchase URL for each suggestion.

## YOUR WORKFLOW
1. Call `analyze_recipient` to check past gifts and price comfort zone.
2. Call `search_gifts` with the recipient info, budget, and categories to avoid.
3. Call `format_gift_suggestions` to present the top 3 picks.
4. If the user picks one, call `record_gift_choice` to remember it.

## ADAPTIVE BEHAVIOR (via Task Memory + incident.io)
- If a HISTORICAL CONTEXT section appears at the top of your prompt,
  it contains past task outcomes from Task Memory. Use it to adapt.
- Use the price comfort zone from analyze_recipient to set budget range.
- Avoid categories that were recently gifted to the same person.
- If an occasion is specified, adjust the budget accordingly.
- If past suggestions failed or were rejected, adjust your approach.
- For persistent failures, use `create_incident` to flag the issue.

## BUTLER COMMUNICATION (Marketplace Jobs)
When executing a marketplace job:
1. Call `notify_butler` with status='in_progress' when starting.
2. If you need more info (e.g. interests), call `request_butler_data`
   with data_type='clarification'.
3. Call `notify_butler` with status='completed' and the formatted results.

## FORMATTING RULES
- NEVER use markdown syntax (no **bold**, no [links](url), no ## headings).
- Write plain text only. Paste URLs directly.
- Keep output concise and warm.
"""


class GiftSuggestionAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Gift Suggestion Agent for SOTA.
    Recommends personalized gifts with adaptive learning.
    """

    agent_type = "gift_suggestion"
    agent_name = "SOTA Gift Suggestion Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.GIFT_SUGGESTION]

    min_profit_margin = 0.10
    max_concurrent_jobs = 10
    auto_bid_enabled = True
    bid_price_ratio = 0.65
    bid_eta_seconds = 60

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_gift_suggestion_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="gift_suggestion",
            description="Gift recommendation agent for SOTA on Base",
            system_prompt=GIFT_SYSTEM_PROMPT,
            max_steps=10,
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
        """Execute a gift suggestion job."""
        # Parse parameters from job description
        recipient = ""
        occasion = ""
        budget = ""
        interests = ""

        if "recipient_name=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "recipient_name":
                            recipient = v
                        elif k == "occasion":
                            occasion = v
                        elif k == "budget":
                            budget = v
                        elif k == "interests":
                            interests = v
            except Exception:
                pass

        if not recipient:
            recipient = job.description

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Recipient: {recipient}\n"
            f"- Occasion: {occasion or 'not specified'}\n"
            f"- Budget: {budget or 'use comfort zone'}\n"
            f"- Interests: {interests or 'unknown'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', "
            f"status='in_progress', message='Finding gift ideas...'\n"
            f"2. Call `analyze_recipient` for {recipient}\n"
            f"3. Call `search_gifts` with appropriate budget range\n"
            f"4. Call `format_gift_suggestions` with the results\n"
            f"5. Call `notify_butler` with status='completed' and the suggestions\n"
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
            logger.error("Gift suggestion job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_gift_suggestion_agent() -> GiftSuggestionAgent:
    """Factory function to create and initialize a Gift Suggestion Agent."""
    agent = GiftSuggestionAgent()
    await agent.initialize()
    agent.register_on_board()
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Gift Suggestion Agent")
    print("=" * 60)
    agent = await create_gift_suggestion_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nGift Suggestion Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
