"""Unit tests for sota_sdk.models — Job, Bid, BidResult, JobResult."""

import pytest

from sota_sdk.models import Bid, BidResult, Job, JobResult

pytestmark = pytest.mark.unit


class TestJob:
    def test_required_fields(self):
        j = Job(id="1", description="d", tags=["t"], budget_usdc=5.0, deadline_ts=999, poster="0xA")
        assert j.id == "1"
        assert j.description == "d"
        assert j.tags == ["t"]
        assert j.budget_usdc == 5.0
        assert j.deadline_ts == 999
        assert j.poster == "0xA"

    def test_default_metadata_and_params(self):
        j = Job(id="1", description="d", tags=[], budget_usdc=0, deadline_ts=0, poster="")
        assert j.metadata == {}
        assert j.params == {}

    def test_custom_metadata(self):
        j = Job(id="1", description="d", tags=[], budget_usdc=0, deadline_ts=0, poster="", metadata={"k": "v"})
        assert j.metadata == {"k": "v"}

    def test_mutable_default_isolation(self):
        """Two Jobs must not share the same metadata dict."""
        j1 = Job(id="1", description="d", tags=[], budget_usdc=0, deadline_ts=0, poster="")
        j2 = Job(id="2", description="d", tags=[], budget_usdc=0, deadline_ts=0, poster="")
        j1.metadata["x"] = 1
        assert "x" not in j2.metadata

    def test_mutable_params_isolation(self):
        j1 = Job(id="1", description="", tags=[], budget_usdc=0, deadline_ts=0, poster="")
        j2 = Job(id="2", description="", tags=[], budget_usdc=0, deadline_ts=0, poster="")
        j1.params["y"] = 2
        assert "y" not in j2.params


class TestBid:
    def test_required_fields(self):
        b = Bid(job_id="j1", amount_usdc=8.0)
        assert b.job_id == "j1"
        assert b.amount_usdc == 8.0

    def test_defaults(self):
        b = Bid(job_id="j1", amount_usdc=5.0)
        assert b.estimated_seconds == 300
        assert b.bid_id == ""
        assert b.tags == []
        assert b.metadata == {}

    def test_custom_values(self):
        b = Bid(job_id="j1", amount_usdc=5.0, estimated_seconds=60, bid_id="b1", tags=["t"])
        assert b.estimated_seconds == 60
        assert b.bid_id == "b1"
        assert b.tags == ["t"]


class TestBidResult:
    def test_accepted(self):
        r = BidResult(job_id="j1", accepted=True, bid_id="b1")
        assert r.accepted is True
        assert r.bid_id == "b1"

    def test_rejected_with_reason(self):
        r = BidResult(job_id="j1", accepted=False, reason="outbid")
        assert r.accepted is False
        assert r.reason == "outbid"


class TestJobResult:
    def test_success(self):
        r = JobResult(success=True, data={"answer": 42})
        assert r.success is True
        assert r.data["answer"] == 42
        assert r.error is None
        assert r.proof_hash is None

    def test_proof_hash_assignment(self):
        r = JobResult(success=True)
        r.proof_hash = "0xdeadbeef"
        assert r.proof_hash == "0xdeadbeef"

    def test_defaults(self):
        r = JobResult(success=False)
        assert r.data == {}
        assert r.error is None
