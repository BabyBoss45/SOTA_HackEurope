"""
Bid strategies for the SOTA SDK.

DefaultBidStrategy  -- simple ratio-based bidding (adapted from auto_bidder.py)
CostAwareBidStrategy -- stub that will use Paid.ai data from Task 3
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from ..models import Job, Bid

logger = logging.getLogger(__name__)


class BidStrategy(ABC):
    """Interface that all bid strategies must implement."""

    @abstractmethod
    async def evaluate(self, job: Job) -> Optional[Bid]:
        """
        Evaluate a job and return a Bid if the agent should bid, else None.
        """
        ...

    def set_agent_tags(self, tags: list[str]) -> None:
        """Called by SOTAAgent during boot to inject the agent's declared tags.

        Override if your strategy uses tag matching for bid decisions.
        Default is a no-op.
        """


class DefaultBidStrategy(BidStrategy):
    """
    Ratio-based bidding (ported from AutoBidderMixin).

    Bids ``price_ratio * budget_usdc`` if the agent's tags overlap with
    the job's tags. Skips jobs below ``min_budget_usdc``.
    """

    def __init__(
        self,
        price_ratio: float = 0.80,
        default_eta_seconds: int = 300,
        min_budget_usdc: float = 0.50,
        agent_tags: Optional[list[str]] = None,
    ):
        self.price_ratio = price_ratio
        self.default_eta_seconds = default_eta_seconds
        self.min_budget_usdc = min_budget_usdc
        self._agent_tags: set[str] = set(t.lower() for t in (agent_tags or []))

    def set_agent_tags(self, tags: list[str]) -> None:
        """Called by SOTAAgent.run() to inject the agent's declared tags."""
        self._agent_tags = set(t.lower() for t in tags)

    async def evaluate(self, job: Job) -> Optional[Bid]:
        # Tag overlap check
        if self._agent_tags:
            job_tags = set(t.lower() for t in job.tags)
            if not self._agent_tags & job_tags:
                logger.debug("Skipping job %s -- no tag overlap", job.id)
                return None

        # Budget floor
        if job.budget_usdc < self.min_budget_usdc:
            logger.debug(
                "Skipping job %s -- budget %.2f below minimum %.2f",
                job.id, job.budget_usdc, self.min_budget_usdc,
            )
            return None

        proposed = max(job.budget_usdc * self.price_ratio, self.min_budget_usdc)
        return Bid(
            job_id=job.id,
            amount_usdc=round(proposed, 2),
            estimated_seconds=self.default_eta_seconds,
            tags=[t for t in job.tags if t.lower() in self._agent_tags] if self._agent_tags else job.tags,
        )


class CostAwareBidStrategy(BidStrategy):
    """
    Placeholder for Paid.ai cost-aware bidding (Task 3).

    Falls back to DefaultBidStrategy until Paid.ai integration is wired up.
    """

    def __init__(self, **kwargs):
        self._fallback = DefaultBidStrategy(**kwargs)

    def set_agent_tags(self, tags: list[str]) -> None:
        self._fallback.set_agent_tags(tags)

    async def evaluate(self, job: Job) -> Optional[Bid]:
        # TODO: Query Paid.ai for estimated execution cost, factor into bid
        return await self._fallback.evaluate(job)
