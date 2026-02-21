"""Unit tests for marketplace hub — AgentRegistry, BiddingEngine, models."""

import time
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from marketplace.bidding import BiddingEngine, Bid, ActiveJob
from marketplace.models import (
    AgentInfo, BidMsg, JobData, JobStatus, PostJobRequest,
)
from marketplace.registry import AgentRegistry, ConnectedAgent

pytestmark = pytest.mark.unit


# ── AgentRegistry ────────────────────────────────────────────────────────────

class TestAgentRegistry:
    def test_register_assigns_unique_id(self):
        reg = AgentRegistry()
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["t"], wallet_address="SoLAgent1111111111111111111111111")
        a1 = reg.register(info, ws)
        a2 = reg.register(info, ws)
        assert a1.agent_id != a2.agent_id

    def test_unregister_removes(self):
        reg = AgentRegistry()
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["t"], wallet_address="SoLAgent1111111111111111111111111")
        a = reg.register(info, ws)
        reg.unregister(a.agent_id)
        assert reg.get(a.agent_id) is None
        assert reg.count == 0

    def test_find_by_tags_case_insensitive(self):
        reg = AgentRegistry()
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["NLP", "Python"], wallet_address="SoLAgent1111111111111111111111111")
        reg.register(info, ws)
        matches = reg.find_by_tags(["nlp"])
        assert len(matches) == 1

    def test_find_by_tags_no_match(self):
        reg = AgentRegistry()
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["nlp"], wallet_address="SoLAgent1111111111111111111111111")
        reg.register(info, ws)
        matches = reg.find_by_tags(["javascript"])
        assert len(matches) == 0

    def test_count_property(self):
        reg = AgentRegistry()
        assert reg.count == 0
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["t"], wallet_address="SoLAgent1111111111111111111111111")
        reg.register(info, ws)
        assert reg.count == 1

    def test_touch_heartbeat_updates(self):
        reg = AgentRegistry()
        ws = MagicMock()
        info = AgentInfo(name="a1", tags=["t"], wallet_address="SoLAgent1111111111111111111111111")
        a = reg.register(info, ws)
        old_hb = a.last_heartbeat
        time.sleep(0.01)
        reg.touch_heartbeat(a.agent_id)
        assert a.last_heartbeat > old_hb

    def test_all_agents(self):
        reg = AgentRegistry()
        ws = MagicMock()
        reg.register(AgentInfo(name="a1", tags=["t"], wallet_address=""), ws)
        reg.register(AgentInfo(name="a2", tags=["t"], wallet_address=""), ws)
        assert len(reg.all_agents()) == 2


# ── BiddingEngine ────────────────────────────────────────────────────────────

def _job_data(job_id="j1", budget=10.0, tags=None):
    return JobData(
        id=job_id, description="d", tags=tags or ["t"],
        budget_usdc=budget, deadline_ts=int(time.time()) + 3600, poster="SoLPoster1111111111111111111111111",
    )


class TestBiddingEngine:
    def test_open_job_status_bidding(self):
        eng = BiddingEngine()
        active = eng.open_job(_job_data())
        assert active.status == JobStatus.BIDDING

    def test_submit_bid_accepted(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        bid = eng.submit_bid("j1", "a1", "Agent1", "SoLAgent1111111111111111111111111", 5.0, 300)
        assert bid is not None
        assert bid.amount_usdc == 5.0

    def test_submit_bid_wrong_state(self):
        eng = BiddingEngine()
        # Job not opened
        bid = eng.submit_bid("j_nonexistent", "a1", "Agent1", "SoLAgent1111111111111111111111111", 5.0, 300)
        assert bid is None

    def test_submit_bid_duplicate_agent(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        eng.submit_bid("j1", "a1", "Agent1", "SoLAgent1111111111111111111111111", 5.0, 300)
        dup = eng.submit_bid("j1", "a1", "Agent1", "SoLAgent1111111111111111111111111", 4.0, 300)
        assert dup is None

    def test_select_winner_lowest_price(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1", budget=10.0))
        eng.submit_bid("j1", "a1", "Expensive", "SoLAgent1111111111111111111111111", 9.0, 300)
        eng.submit_bid("j1", "a2", "Cheap", "SoLAgent2222222222222222222222222", 5.0, 300)
        result = eng.select_winner("j1")
        assert result.winner is not None
        assert result.winner.agent_name == "Cheap"

    def test_select_winner_tiebreak_by_time(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1", budget=10.0))
        # Submit two bids at the same price; first one should win
        b1 = eng.submit_bid("j1", "a1", "First", "SoLAgent1111111111111111111111111", 5.0, 300)
        b2 = eng.submit_bid("j1", "a2", "Second", "SoLAgent2222222222222222222222222", 5.0, 300)
        # Ensure b1 has earlier timestamp
        b1.submitted_at = time.time() - 10
        b2.submitted_at = time.time()
        result = eng.select_winner("j1")
        assert result.winner.agent_name == "First"

    def test_over_budget_filtered(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1", budget=5.0))
        eng.submit_bid("j1", "a1", "Overpriced", "SoLAgent1111111111111111111111111", 10.0, 300)
        eng.submit_bid("j1", "a2", "Cheap", "SoLAgent2222222222222222222222222", 4.0, 300)
        result = eng.select_winner("j1")
        assert result.winner.agent_name == "Cheap"

    def test_all_over_budget_expired(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1", budget=1.0))
        eng.submit_bid("j1", "a1", "Over", "SoLAgent1111111111111111111111111", 5.0, 300)
        result = eng.select_winner("j1")
        assert result.winner is None
        active = eng.get_job("j1")
        assert active.status == JobStatus.EXPIRED

    def test_no_bids_expired(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        result = eng.select_winner("j1")
        assert result.winner is None
        active = eng.get_job("j1")
        assert active.status == JobStatus.EXPIRED

    def test_mark_completed(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        eng.mark_completed("j1", {"data": "ok"})
        active = eng.get_job("j1")
        assert active.status == JobStatus.COMPLETED
        assert active.result == {"data": "ok"}

    def test_mark_failed(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        eng.mark_failed("j1", "error msg")
        active = eng.get_job("j1")
        assert active.status == JobStatus.FAILED

    def test_list_jobs(self):
        eng = BiddingEngine()
        eng.open_job(_job_data("j1"))
        eng.open_job(_job_data("j2"))
        assert len(eng.list_jobs()) == 2


# ── Pydantic Models ──────────────────────────────────────────────────────────

class TestHubModels:
    def test_post_job_request_positive_budget(self):
        with pytest.raises(ValidationError):
            PostJobRequest(
                description="d", tags=["t"], budget_usdc=-1,
                deadline_ts=999, poster="SoLPoster1111111111111111111111111",
            )

    def test_post_job_request_bid_window_range(self):
        with pytest.raises(ValidationError):
            PostJobRequest(
                description="d", tags=["t"], budget_usdc=10,
                deadline_ts=999, poster="SoLPoster1111111111111111111111111", bid_window_seconds=0,
            )
        with pytest.raises(ValidationError):
            PostJobRequest(
                description="d", tags=["t"], budget_usdc=10,
                deadline_ts=999, poster="SoLPoster1111111111111111111111111", bid_window_seconds=301,
            )

    def test_post_job_request_non_empty_tags(self):
        with pytest.raises(ValidationError):
            PostJobRequest(
                description="d", tags=[], budget_usdc=10,
                deadline_ts=999, poster="SoLPoster1111111111111111111111111",
            )

    def test_bid_msg_positive_amount(self):
        with pytest.raises(ValidationError):
            BidMsg(job_id="j1", amount_usdc=0)
        with pytest.raises(ValidationError):
            BidMsg(job_id="j1", amount_usdc=-5)

    def test_valid_post_job_request(self):
        req = PostJobRequest(
            description="test", tags=["nlp"], budget_usdc=10,
            deadline_ts=999, poster="SoLPoster1111111111111111111111111",
        )
        assert req.budget_usdc == 10
        assert req.bid_window_seconds == 15  # default
