"""Unit tests for sota_sdk.marketplace.bidding — BidStrategy, DefaultBidStrategy, CostAwareBidStrategy."""

import pytest

from sota_sdk.marketplace.bidding import (
    BidStrategy,
    CostAwareBidStrategy,
    DefaultBidStrategy,
)
from sota_sdk.models import Bid, Job

pytestmark = pytest.mark.unit


def _job(tags=None, budget=10.0):
    return Job(
        id="j1", description="d", tags=tags or ["test"],
        budget_usdc=budget, deadline_ts=999999, poster="0xA",
    )


class TestBidStrategyABC:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BidStrategy()

    async def test_custom_strategy(self):
        class AlwaysBid(BidStrategy):
            async def evaluate(self, job):
                return Bid(job_id=job.id, amount_usdc=1.0)

        s = AlwaysBid()
        bid = await s.evaluate(_job())
        assert bid.amount_usdc == 1.0


class TestDefaultBidStrategy:
    async def test_matching_tags_bids(self, make_job):
        s = DefaultBidStrategy(agent_tags=["test"])
        job = make_job(tags=["test"])
        bid = await s.evaluate(job)
        assert bid is not None
        assert bid.job_id == job.id

    async def test_non_matching_tags_skips(self, make_job):
        s = DefaultBidStrategy(agent_tags=["python"])
        job = make_job(tags=["javascript"])
        bid = await s.evaluate(job)
        assert bid is None

    async def test_low_budget_skips(self, make_job):
        s = DefaultBidStrategy(agent_tags=["test"], min_budget_usdc=5.0)
        job = make_job(tags=["test"], budget_usdc=1.0)
        bid = await s.evaluate(job)
        assert bid is None

    async def test_case_insensitive_tags(self, make_job):
        s = DefaultBidStrategy(agent_tags=["TEST"])
        job = make_job(tags=["test"])
        bid = await s.evaluate(job)
        assert bid is not None

    async def test_empty_agent_tags_bids_on_all(self, make_job):
        s = DefaultBidStrategy(agent_tags=[])
        job = make_job(tags=["anything"])
        bid = await s.evaluate(job)
        assert bid is not None

    async def test_bid_amount_at_ratio(self, make_job):
        s = DefaultBidStrategy(price_ratio=0.80, agent_tags=["test"])
        job = make_job(tags=["test"], budget_usdc=100.0)
        bid = await s.evaluate(job)
        assert bid.amount_usdc == 80.0

    @pytest.mark.parametrize("ratio", [0.50, 0.80, 0.95])
    async def test_parametrized_ratios(self, make_job, ratio):
        s = DefaultBidStrategy(price_ratio=ratio, agent_tags=["test"])
        job = make_job(tags=["test"], budget_usdc=100.0)
        bid = await s.evaluate(job)
        expected = round(100.0 * ratio, 2)
        assert bid.amount_usdc == expected

    async def test_bid_tags_contain_overlap_only(self, make_job):
        s = DefaultBidStrategy(agent_tags=["python", "nlp"])
        job = make_job(tags=["python", "javascript"])
        bid = await s.evaluate(job)
        assert bid is not None
        assert "python" in bid.tags
        assert "javascript" not in bid.tags

    async def test_set_agent_tags(self, make_job):
        s = DefaultBidStrategy()
        s.set_agent_tags(["NEW_TAG"])
        job = make_job(tags=["new_tag"])
        bid = await s.evaluate(job)
        assert bid is not None

    async def test_min_budget_floor(self, make_job):
        s = DefaultBidStrategy(price_ratio=0.10, min_budget_usdc=0.50, agent_tags=["test"])
        job = make_job(tags=["test"], budget_usdc=1.0)
        bid = await s.evaluate(job)
        # max(1.0 * 0.10, 0.50) = 0.50
        assert bid.amount_usdc == 0.50


class TestCostAwareBidStrategy:
    async def test_delegates_to_default(self, make_job):
        s = CostAwareBidStrategy(agent_tags=["test"])
        job = make_job(tags=["test"])
        bid = await s.evaluate(job)
        assert bid is not None

    async def test_set_agent_tags(self, make_job):
        s = CostAwareBidStrategy()
        s.set_agent_tags(["nlp"])
        job = make_job(tags=["nlp"])
        bid = await s.evaluate(job)
        assert bid is not None
