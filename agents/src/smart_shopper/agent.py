"""
Smart Shopper Agent -- SOTA on Base

Beyond simple price comparison:
1. Scrapes retailers for real-time prices
2. Tracks price history and trends
3. Uses economic reasoning for buy/wait decisions
4. Sets alerts for target prices
5. Executes purchases when conditions are right
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

from .tools import create_smart_shopper_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


SHOPPER_SYSTEM_PROMPT = """
You are the Smart Shopper Agent for SOTA, specializing in finding the
best deals with economic reasoning.

## YOUR WORKFLOW
1. Call `search_retailers` to find current prices across stores.
2. Call `track_price_history` to see price trends.
3. Call `analyze_market` to get a buy/wait recommendation.
4. Based on the analysis:
   - If BUY NOW: present the best deal and offer to execute purchase.
   - If WAIT: set a price alert and explain the reasoning.
   - If stock is low and price is close to target: warn about stockout risk.

## ECONOMIC REASONING
- Factor in: price trend, stock levels, urgency, target price.
- If price is trending DOWN and stock is HIGH, recommend waiting.
- If price is trending UP or stock is LOW, recommend buying soon.
- Calculate expected savings vs risk: "Waiting could save ~X but
  there's a Y% chance it sells out."

## ADAPTIVE BEHAVIOR (via Task Memory + incident.io)
- If a HISTORICAL CONTEXT section appears at the top of your prompt,
  it contains past task outcomes. Adapt based on prior search failures.
- If stock level is "low" and price is within 5% of target, accelerate
  the decision -- recommend buying immediately.
- If price is trending down steadily, recommend setting an alert at a
  lower target and waiting.
- Always present the analysis transparently to the user.
- For persistent retailer failures, use `create_incident` to flag.

## BUTLER COMMUNICATION (Marketplace Jobs)
When executing a marketplace job:
1. Call `notify_butler` with status='in_progress' when starting.
2. If you need clarification (e.g. specific model), call
   `request_butler_data` with data_type='clarification'.
3. Before executing a purchase, call `request_butler_data` with
   data_type='confirmation'.
4. Call `notify_butler` with status='completed' and results.

## FORMATTING RULES
- NEVER use markdown syntax.
- Write plain text only. Paste URLs directly.
- Present prices clearly with currency.
"""


class SmartShopperAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Smart Shopper Agent for SOTA.
    Finds deals with economic reasoning and adaptive purchasing.
    """

    agent_type = "smart_shopper"
    agent_name = "SOTA Smart Shopper Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.SMART_SHOPPING]

    min_profit_margin = 0.10
    max_concurrent_jobs = 5
    auto_bid_enabled = True
    bid_price_ratio = 0.75
    bid_eta_seconds = 300

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_smart_shopper_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="smart_shopper",
            description="Smart shopping agent with economic reasoning for SOTA on Base",
            system_prompt=SHOPPER_SYSTEM_PROMPT,
            max_steps=15,
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
        """Execute a smart shopping job."""
        product_query = ""
        max_budget = ""
        currency = "GBP"
        urgency = "medium"
        preferred_retailers = ""

        if "=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "product_query":
                            product_query = v
                        elif k == "max_budget":
                            max_budget = v
                        elif k == "currency":
                            currency = v
                        elif k == "urgency":
                            urgency = v
                        elif k == "preferred_retailers":
                            preferred_retailers = v
            except Exception:
                pass

        if not product_query:
            product_query = job.description

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Product: {product_query}\n"
            f"- Max budget: {max_budget or 'not specified'} {currency}\n"
            f"- Urgency: {urgency}\n"
            f"- Preferred retailers: {preferred_retailers or 'any'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', "
            f"status='in_progress', message='Searching for the best deal...'\n"
            f"2. Call `search_retailers` for the product\n"
            f"3. Call `track_price_history` to check trends\n"
            f"4. Call `analyze_market` with the best price and conditions\n"
            f"5. Present the recommendation to the user\n"
            f"6. If buying: call `request_butler_data` for confirmation, "
            f"then `execute_purchase`\n"
            f"7. If waiting: call `set_price_alert`\n"
            f"8. Call `notify_butler` with status='completed' and results\n"
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
            logger.error("Smart shopper job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_smart_shopper_agent() -> SmartShopperAgent:
    """Factory function to create and initialize a Smart Shopper Agent."""
    agent = SmartShopperAgent()
    await agent.initialize()
    agent.register_on_board()
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Smart Shopper Agent")
    print("=" * 60)
    agent = await create_smart_shopper_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nSmart Shopper Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
