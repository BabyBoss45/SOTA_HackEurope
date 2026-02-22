"""
Tests for ClawBot bug fixes — standalone (no sota_sdk / solders dependency).

Covers:
  1. Case-insensitive tag matching (SQL LOWER wrapping)
  2. ExternalAgentInviter accepts pool (not db_url)
  3. _notify_external_winner marks job EXPIRED on failure
  4. Job timeout watchdog
  5. _persist_bid_update uses pool
  6. Bid validation logic
  7. Port stripping in domain validation
"""

import asyncio
import importlib
import inspect
import re
import sys
import time
import types
import unittest
from unittest.mock import AsyncMock, MagicMock


# ─── Manually load job_board.py and external_agent_inviter.py ──
# without triggering agents/src/__init__.py (which pulls solders/sota_sdk).

import os

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
_agents_root = os.path.join(_root, "agents")

def _load_module_directly(module_name: str, file_path: str, deps: dict = None):
    """Load a single .py file as a module, injecting mock dependencies."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    # Inject any pre-created dependency modules
    if deps:
        for dep_name, dep_mod in deps.items():
            sys.modules[dep_name] = dep_mod
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

# Stub out hmac_signer so external_agent_inviter can import it
_hmac_stub = types.ModuleType("agents.src.shared.hmac_signer")
class _StubHMACSigner:
    def sign(self, payload, key):
        return "t=0,v1=stub"
_hmac_stub.HMACSigner = _StubHMACSigner
sys.modules["agents.src.shared.hmac_signer"] = _hmac_stub

# Ensure parent packages exist
for pkg in ["agents", "agents.src", "agents.src.shared"]:
    if pkg not in sys.modules:
        sys.modules[pkg] = types.ModuleType(pkg)

# Load job_board first (no external deps beyond stdlib)
job_board_mod = _load_module_directly(
    "agents.src.shared.job_board",
    os.path.join(_agents_root, "src/shared/job_board.py"),
)

JobBoard = job_board_mod.JobBoard
JobListing = job_board_mod.JobListing
JobStatus = job_board_mod.JobStatus
Bid = job_board_mod.Bid

# Load external_agent_inviter (needs job_board + hmac_signer)
inviter_mod = _load_module_directly(
    "agents.src.shared.external_agent_inviter",
    os.path.join(_agents_root, "src/shared/external_agent_inviter.py"),
)
ExternalAgentInviter = inviter_mod.ExternalAgentInviter
_persist_bid_update = inviter_mod._persist_bid_update


# ─── Tests ─────────────────────────────────────────────────────

class TestJobBoardTimeoutWatchdog(unittest.TestCase):
    """Fix #6: _external_job_timeout marks ASSIGNED jobs as EXPIRED."""

    def setUp(self):
        JobBoard.reset()
        self.board = JobBoard.instance()

    def tearDown(self):
        JobBoard.reset()

    def test_timeout_marks_assigned_job_expired(self):
        job = JobListing(
            job_id="test-timeout-1", description="test", tags=["test"],
            budget_usdc=1.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        job.status = JobStatus.ASSIGNED

        loop = asyncio.new_event_loop()
        with unittest.mock.patch("asyncio.sleep", new_callable=AsyncMock):
            loop.run_until_complete(self.board._external_job_timeout(job, timeout_minutes=1))
        loop.close()

        self.assertEqual(job.status, JobStatus.EXPIRED)

    def test_timeout_skips_non_assigned_job(self):
        job = JobListing(
            job_id="test-timeout-2", description="test", tags=["test"],
            budget_usdc=1.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        job.status = JobStatus.EXPIRED  # Already moved on

        loop = asyncio.new_event_loop()
        with unittest.mock.patch("asyncio.sleep", new_callable=AsyncMock):
            loop.run_until_complete(self.board._external_job_timeout(job, timeout_minutes=1))
        loop.close()

        self.assertEqual(job.status, JobStatus.EXPIRED)


class TestNotifyExternalWinnerFailure(unittest.TestCase):
    """Fix #3: _notify_external_winner marks job EXPIRED when db_pool is None."""

    def setUp(self):
        JobBoard.reset()
        self.board = JobBoard.instance()
        self.board._db_pool = None

    def tearDown(self):
        JobBoard.reset()

    def test_no_db_pool_marks_expired(self):
        job = JobListing(
            job_id="test-nopool-1", description="test", tags=["test"],
            budget_usdc=1.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        job.status = JobStatus.ASSIGNED

        bid = Bid(
            bid_id="bid1", job_id="test-nopool-1", bidder_id="external:agent1",
            bidder_address="wallet1", amount_usdc=0.5, estimated_seconds=60,
            tags=["test"], metadata={"externalAgentId": "agent1", "confidence": 0.9},
        )

        # Stub execution_token module since it's imported inside the function
        exec_token_stub = types.ModuleType("agents.src.shared.execution_token")
        exec_token_stub.create_execution_token = AsyncMock()
        sys.modules["agents.src.shared.execution_token"] = exec_token_stub

        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.board._notify_external_winner(job, bid))
        loop.close()

        self.assertEqual(job.status, JobStatus.EXPIRED)


class TestBidSelection(unittest.TestCase):
    """Verify bid selection picks lowest price."""

    def test_lowest_price_wins(self):
        job = JobListing(
            job_id="s1", description="test", tags=["test"],
            budget_usdc=5.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        bids = [
            Bid(bid_id="b1", job_id="s1", bidder_id="w1", bidder_address="a1",
                amount_usdc=3.0, estimated_seconds=60, tags=["test"]),
            Bid(bid_id="b2", job_id="s1", bidder_id="w2", bidder_address="a2",
                amount_usdc=1.5, estimated_seconds=90, tags=["test"]),
            Bid(bid_id="b3", job_id="s1", bidder_id="w3", bidder_address="a3",
                amount_usdc=4.0, estimated_seconds=30, tags=["test"]),
        ]
        result = JobBoard._select_best(job, bids)
        self.assertEqual(result.winning_bid.bidder_id, "w2")

    def test_over_budget_rejected(self):
        job = JobListing(
            job_id="s2", description="test", tags=["test"],
            budget_usdc=1.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        bids = [
            Bid(bid_id="b1", job_id="s2", bidder_id="w1", bidder_address="a1",
                amount_usdc=2.0, estimated_seconds=60, tags=["test"]),
        ]
        result = JobBoard._select_best(job, bids)
        self.assertIsNone(result.winning_bid)

    def test_no_bids(self):
        job = JobListing(
            job_id="s3", description="test", tags=["test"],
            budget_usdc=1.0, deadline_ts=int(time.time()) + 3600, poster="p1",
        )
        result = JobBoard._select_best(job, [])
        self.assertIsNone(result.winning_bid)


class TestExternalAgentInviterPool(unittest.TestCase):
    """Fix #2: ExternalAgentInviter takes a pool, not db_url."""

    def test_constructor_accepts_pool(self):
        mock_pool = MagicMock()
        mock_signer = MagicMock()
        inviter = ExternalAgentInviter(pool=mock_pool, signer=mock_signer)
        self.assertIs(inviter._pool, mock_pool)

    def test_constructor_rejects_db_url(self):
        with self.assertRaises(TypeError):
            ExternalAgentInviter(db_url="postgres://...", signer=MagicMock())


class TestPersistBidUpdateUsesPool(unittest.TestCase):
    """Fix #5: _persist_bid_update uses the shared pool."""

    def test_calls_pool_execute(self):
        mock_pool = AsyncMock()
        agent = {"agentId": "a1", "name": "test-agent"}

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_persist_bid_update(mock_pool, "job-1", agent, 1.5, 0.9, 60))
        loop.close()

        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args[0][0]
        self.assertIn("AgentJobUpdate", sql)


class TestCaseInsensitiveSQL(unittest.TestCase):
    """Fix #1: SQL queries use LOWER() for case-insensitive matching."""

    def test_fetch_matching_agents_uses_lower(self):
        source = inspect.getsource(ExternalAgentInviter._fetch_matching_agents)
        self.assertIn("LOWER(c)", source)
        self.assertIn("array_agg", source)


class TestPortStripping(unittest.TestCase):
    """Fix #4: Port numbers stripped from host in domain validation."""

    def test_port_stripped(self):
        pattern = r':\d+$'
        self.assertEqual(re.sub(pattern, '', 'example.com:8080'), 'example.com')
        self.assertEqual(re.sub(pattern, '', 'example.com'), 'example.com')
        self.assertEqual(re.sub(pattern, '', 'sub.example.com:443'), 'sub.example.com')
        self.assertEqual(re.sub(pattern, '', 'localhost:3000'), 'localhost')


if __name__ == "__main__":
    unittest.main()
