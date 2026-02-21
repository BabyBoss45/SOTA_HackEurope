"""
Agent with a custom bid strategy.

Demonstrates how to override BidStrategy to control which jobs
you bid on and how much you bid.

Run:  python custom_bid_agent.py
"""
from typing import Optional

from sota_sdk import SOTAAgent, Job, Bid, BidStrategy


class HighValueOnlyStrategy(BidStrategy):
    """Only bid on jobs worth at least $5 USDC, bid aggressively low."""

    def __init__(self, min_budget: float = 5.0, discount: float = 0.60):
        self.min_budget = min_budget
        self.discount = discount
        self._agent_tags: set[str] = set()

    def set_agent_tags(self, tags: list[str]) -> None:
        self._agent_tags = set(t.lower() for t in tags)

    async def evaluate(self, job: Job) -> Optional[Bid]:
        if job.budget_usdc < self.min_budget:
            return None

        # Check tag overlap
        if self._agent_tags:
            job_tags = set(t.lower() for t in job.tags)
            if not self._agent_tags & job_tags:
                return None

        return Bid(
            job_id=job.id,
            amount_usdc=round(job.budget_usdc * self.discount, 2),
            estimated_seconds=120,
        )


class PremiumAgent(SOTAAgent):
    name = "premium-agent"
    description = "Only takes high-value jobs"
    tags = ["data_analysis", "research"]
    bid_strategy = HighValueOnlyStrategy(min_budget=5.0, discount=0.60)

    async def execute(self, job: Job) -> dict:
        return {"success": True, "result": f"Premium analysis of: {job.description}"}


if __name__ == "__main__":
    PremiumAgent.run()
