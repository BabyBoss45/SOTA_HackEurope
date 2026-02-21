"""
End-to-End Agent Test Harness — Butler Simulation + TaskPatternMemory

Bypasses the Butler's Claude chat loop and directly posts jobs to the
JobBoard marketplace.  Each worker agent is initialized, registered,
and tested with a realistic job.  TaskPatternMemory is wired in via
mocked Qdrant + DB so we can verify the full persist → analyze → adapt
loop alongside real agent execution.

Usage:
    # via pytest (recommended)
    cd <repo-root>
    python -m pytest agents/tests/test_e2e_agents.py -v -s --timeout=300

    # standalone
    python agents/tests/test_e2e_agents.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ─── Path & env bootstrap ────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_DIR = os.path.dirname(_HERE)           # agents/
_REPO_ROOT = os.path.dirname(_AGENTS_DIR)      # Euro_SOTA/

for p in (_REPO_ROOT, _AGENTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(_AGENTS_DIR) / ".env")
load_dotenv(Path(_REPO_ROOT) / ".env")

os.environ.setdefault("BUTLER_AUTO_CONFIRM", "true")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("e2e_test")

# ─── Imports from the agent codebase ─────────────────────────

from agents.src.shared.job_board import JobBoard, JobListing, BidResult, JobStatus
from agents.src.shared.butler_comms import ButlerDataExchange
from agents.src.shared.base_agent import ActiveJob
from agents.src.shared.task_memory import (
    TaskPatternMemory,
    TaskOutcome,
    PatternAnalysis,
    build_adaptation_prompt,
    classify_failure,
    extract_context,
)

# Agent factories
from agents.src.hackathon.agent import create_hackathon_agent, HackathonAgent
from agents.src.gift_suggestion.agent import create_gift_suggestion_agent
from agents.src.restaurant_booker.agent import create_restaurant_booker_agent
from agents.src.smart_shopper.agent import create_smart_shopper_agent
from agents.src.trip_planner.agent import create_trip_planner_agent
from agents.src.refund_claim.agent import create_refund_claim_agent
from agents.src.caller.agent import CallerAgent


# ═════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════

BID_WINDOW = 3   # seconds — agents evaluate instantly in-process
JOB_BUDGET = 1.0  # USDC — must exceed auto-bidder minimum of 0.50

MOCK_USER_PROFILE = {
    "full_name": "Test User",
    "email": "test@sota.dev",
    "phone": "+441234567890",
    "location": "London, UK",
    "skills": ["Python", "React", "AI/ML"],
    "preferences": {
        "cuisine": "Italian",
        "budget": "medium",
        "travel_style": "adventure",
    },
}


def _reset_board() -> JobBoard:
    """Reset the JobBoard singleton and return a fresh instance."""
    JobBoard.reset()
    return JobBoard.instance()


def _seed_user_context():
    """Pre-populate ButlerDataExchange with mock user data so agents
    that call request_butler_data get realistic responses."""
    exchange = ButlerDataExchange.instance()
    # The HTTP endpoint in butler_api.py checks _user_context dict.
    # For in-process tests we can also prime the exchange directly.
    # Since agents hit /api/agent/request-data which reads _user_context,
    # we just set the env var for auto-confirm and rely on job metadata.
    return exchange


def _make_listing(
    job_id: str,
    description: str,
    tags: list[str],
    metadata: dict,
    budget: float = JOB_BUDGET,
) -> JobListing:
    return JobListing(
        job_id=job_id,
        description=description,
        tags=tags,
        budget_usdc=budget,
        deadline_ts=int(time.time()) + 7200,
        poster="0xTEST_E2E",
        metadata=metadata,
        bid_window_seconds=BID_WINDOW,
    )


def _make_mock_memory() -> Tuple[TaskPatternMemory, AsyncMock, MagicMock, list]:
    """Create a TaskPatternMemory with mocked DB + Qdrant.

    Returns (memory, mock_db, mock_qdrant, captured_points).
    captured_points collects every Qdrant upsert call for later assertion.
    """
    mock_db = AsyncMock()
    mock_db.store_task_outcome = AsyncMock(return_value={"id": 1})

    captured: list = []

    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True

    def _capture_upsert(collection_name, points):
        captured.extend(points)

    mock_qdrant.upsert.side_effect = _capture_upsert
    mock_qdrant.search.return_value = []  # default: no history

    mem = TaskPatternMemory.__new__(TaskPatternMemory)
    mem.db = mock_db
    mem.qdrant = mock_qdrant
    mem.incident_io = None

    return mem, mock_db, mock_qdrant, captured


def _scored_point(score: float, payload: dict) -> SimpleNamespace:
    """Mimics a qdrant_client ScoredPoint."""
    return SimpleNamespace(score=score, payload=payload)


# ═════════════════════════════════════════════════════════════
#  Test scenarios — one dict per agent
# ═════════════════════════════════════════════════════════════

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "hackathon": {
        "description": (
            "hackathon_discovery: location=London, "
            "date_range=March-April 2026, "
            "theme_technology_focus=AI/blockchain, "
            "online_or_in_person=both"
        ),
        "tags": ["hackathon_registration"],
        "metadata": {
            "tool": "hackathon_registration",
            "parameters": {
                "location": "London",
                "date_range": "March-April 2026",
                "theme_technology_focus": ["AI", "blockchain"],
                "online_or_in_person": "both",
            },
        },
    },
    "gift_suggestion": {
        "description": (
            "gift_suggestion: recipient_name=Mom, "
            "occasion=Birthday, budget=50 GBP, "
            "interests=gardening/cooking"
        ),
        "tags": ["gift_suggestion"],
        "metadata": {
            "tool": "gift_suggestion",
            "parameters": {
                "recipient_name": "Mom",
                "occasion": "Birthday",
                "budget": "50 GBP",
                "interests": "gardening, cooking",
            },
        },
    },
    "restaurant_booker": {
        "description": (
            "restaurant_booking: date=2026-03-15, time=19:30, "
            "cuisine=Italian, location=Soho London, "
            "party_size=4, restaurant_name="
        ),
        "tags": ["restaurant_booking_smart"],
        "metadata": {
            "tool": "restaurant_booking_smart",
            "parameters": {
                "date": "2026-03-15",
                "time": "19:30",
                "cuisine": "Italian",
                "location": "Soho, London",
                "party_size": "4",
            },
        },
    },
    "smart_shopper": {
        "description": (
            "smart_shopping: product_query=Sony WH-1000XM5 headphones, "
            "max_budget=300, currency=GBP, urgency=medium"
        ),
        "tags": ["smart_shopping"],
        "metadata": {
            "tool": "smart_shopping",
            "parameters": {
                "product_query": "Sony WH-1000XM5 headphones",
                "max_budget": "300",
                "currency": "GBP",
                "urgency": "medium",
            },
        },
    },
    "trip_planner": {
        "description": (
            "trip_planning: destination=Barcelona, "
            "trip_duration=5 days, group_size=4, "
            "date_range=April 10-15 2026, "
            "departure_city=London, budget_per_person=500 GBP"
        ),
        "tags": ["trip_planning"],
        "metadata": {
            "tool": "trip_planning",
            "parameters": {
                "destination": "Barcelona",
                "trip_duration": "5 days",
                "group_size": "4",
                "date_range": "April 10-15 2026",
                "departure_city": "London",
                "budget_per_person": "500 GBP",
            },
        },
    },
    "refund_claim": {
        "description": (
            "refund_claim: service_type=train, "
            "booking_reference=GWR-12345, "
            "delay_details=45 minute delay on 14:30 London to Bristol, "
            "operator=GWR"
        ),
        "tags": ["refund_claim"],
        "metadata": {
            "tool": "refund_claim",
            "parameters": {
                "service_type": "train",
                "booking_reference": "GWR-12345",
                "delay_details": "45 minute delay on 14:30 London to Bristol",
                "operator": "GWR",
            },
        },
    },
    "caller": {
        "description": (
            "call_verification: phone_number=+441234567890, "
            "purpose=restaurant booking for 4 guests on March 15"
        ),
        "tags": ["call_verification"],
        "metadata": {
            "tool": "call_verification",
            "parameters": {
                "phone_number": "+441234567890",
                "purpose": "restaurant booking for 4 guests on March 15",
            },
        },
    },
}


# ═════════════════════════════════════════════════════════════
#  Agent factory helpers (with error handling)
# ═════════════════════════════════════════════════════════════

async def _init_agent(name: str):
    """Initialize and register a single agent by name. Returns the agent."""
    factories = {
        "hackathon": create_hackathon_agent,
        "gift_suggestion": create_gift_suggestion_agent,
        "restaurant_booker": create_restaurant_booker_agent,
        "smart_shopper": create_smart_shopper_agent,
        "trip_planner": create_trip_planner_agent,
        "refund_claim": create_refund_claim_agent,
    }
    if name == "caller":
        agent = CallerAgent()
        await agent.initialize()
        agent.register_on_board()
        return agent
    factory = factories[name]
    return await factory()


async def _run_scenario(
    agent_name: str,
    memory: Optional[TaskPatternMemory] = None,
) -> Tuple[BidResult, Any]:
    """Reset board, init agent, attach memory, post job, return results."""
    board = _reset_board()
    _seed_user_context()

    agent = await _init_agent(agent_name)
    if memory is not None:
        agent.task_memory = memory

    sc = SCENARIOS[agent_name]
    listing = _make_listing(
        job_id=f"test-{agent_name}-{uuid4().hex[:6]}",
        description=sc["description"],
        tags=sc["tags"],
        metadata=sc["metadata"],
    )

    result = await board.post_and_select(listing, execute_after_accept=True)
    return result, agent


# ═════════════════════════════════════════════════════════════
#  Part 1: Agent E2E Tests
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_hackathon_agent_e2e():
    result, _ = await _run_scenario("hackathon")
    assert result.winning_bid is not None, "HackathonAgent should have bid"
    assert result.winning_bid.bidder_id == "hackathon"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("HACKATHON result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_gift_suggestion_agent_e2e():
    result, _ = await _run_scenario("gift_suggestion")
    assert result.winning_bid is not None, "GiftSuggestionAgent should have bid"
    assert result.winning_bid.bidder_id == "gift_suggestion"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("GIFT result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_restaurant_booker_agent_e2e():
    result, _ = await _run_scenario("restaurant_booker")
    assert result.winning_bid is not None, "RestaurantBookerAgent should have bid"
    assert result.winning_bid.bidder_id == "restaurant_booker"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("RESTAURANT result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_smart_shopper_agent_e2e():
    result, _ = await _run_scenario("smart_shopper")
    assert result.winning_bid is not None, "SmartShopperAgent should have bid"
    assert result.winning_bid.bidder_id == "smart_shopper"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("SHOPPER result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_trip_planner_agent_e2e():
    result, _ = await _run_scenario("trip_planner")
    assert result.winning_bid is not None, "TripPlannerAgent should have bid"
    assert result.winning_bid.bidder_id == "trip_planner"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("TRIP result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_refund_claim_agent_e2e():
    result, _ = await _run_scenario("refund_claim")
    assert result.winning_bid is not None, "RefundClaimAgent should have bid"
    assert result.winning_bid.bidder_id == "refund_claim"
    assert result.execution_result is not None, "Job should have executed"
    logger.info("REFUND result keys: %s", list(result.execution_result.keys()) if isinstance(result.execution_result, dict) else type(result.execution_result))


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_caller_agent_e2e():
    """CallerAgent degrades gracefully without ElevenLabs/Twilio configured."""
    result, _ = await _run_scenario("caller")
    assert result.winning_bid is not None, "CallerAgent should have bid"
    assert result.winning_bid.bidder_id == "caller"
    assert result.execution_result is not None, "Job should have produced a result (even fallback)"
    if isinstance(result.execution_result, dict):
        # May succeed with a chat_summary fallback or may report missing config
        logger.info("CALLER result: success=%s", result.execution_result.get("success"))


# ═════════════════════════════════════════════════════════════
#  Part 2: TaskPatternMemory Integration Tests
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_memory_persist_on_agent_success():
    """Run an agent with mocked memory, verify TaskOutcome persisted correctly."""
    mem, mock_db, mock_qdrant, captured = _make_mock_memory()

    # Patch embed_text so Qdrant upsert works without sentence-transformers
    with patch("agents.src.shared.task_memory.TaskPatternMemory._persist_qdrant", new_callable=AsyncMock) as mock_pq:
        result, agent = await _run_scenario("gift_suggestion", memory=mem)

    assert result.winning_bid is not None, "Agent should have bid"
    assert result.execution_result is not None, "Job should have executed"

    # AutoBidderMixin._execute_job_for_board calls task_memory.persist_outcome
    assert mock_db.store_task_outcome.await_count >= 1, (
        "persist_outcome should have written to DB"
    )
    call_data = mock_db.store_task_outcome.call_args_list[0][0][0]
    assert call_data["agent_id"] == "gift_suggestion"
    assert "outcome_id" in call_data
    assert "task_type" in call_data
    assert isinstance(call_data["success"], bool)
    logger.info(
        "MEMORY PERSIST: agent=%s success=%s task_type=%s",
        call_data["agent_id"], call_data["success"], call_data["task_type"],
    )


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_memory_persist_failure_classification():
    """Verify failure classification when an agent returns an error dict."""
    mem, mock_db, _, _ = _make_mock_memory()

    fake_job = ActiveJob(
        job_id=999,
        bid_id=0,
        job_type=0,
        description="refund_claim: service_type=train, operator=GWR",
        budget=20000,
        deadline=int(time.time()) + 3600,
        params={"region": "UK"},
    )

    error_result = {"success": False, "error": "Connection refused to GWR API"}
    outcome = await mem.persist_outcome(
        job=fake_job, agent_id="refund_claim",
        result=error_result, elapsed_ms=300,
    )

    assert outcome.success is False
    assert outcome.failure_type == "network"
    assert outcome.recoverable is True
    assert outcome.agent_id == "refund_claim"
    assert outcome.context.get("region") == "UK"

    mock_db.store_task_outcome.assert_awaited_once()
    stored = mock_db.store_task_outcome.call_args[0][0]
    assert stored["failure_type"] == "network"
    assert stored["recoverable"] is True
    logger.info("FAILURE CLASSIFICATION: type=%s recoverable=%s", outcome.failure_type, outcome.recoverable)


@pytest.mark.asyncio
async def test_memory_analyze_after_multiple_outcomes():
    """Persist two outcomes, configure Qdrant mock to return them,
    then verify PatternAnalysis is computed correctly."""
    mem, mock_db, mock_qdrant, captured = _make_mock_memory()

    job = ActiveJob(
        job_id=100, bid_id=0, job_type=0,
        description="hackathon_discovery: location=London",
        budget=20000, deadline=int(time.time()) + 3600,
        params={"tags": ["hackathon_registration"]},
    )

    # Persist a success and a failure
    outcome_ok = await mem.persist_outcome(
        job=job, agent_id="hackathon",
        result={"success": True, "hackathons": [{"name": "ETH London"}]},
        elapsed_ms=1500,
    )
    outcome_fail = await mem.persist_outcome(
        job=job, agent_id="hackathon",
        result={"success": False, "error": "Request timed out after 30s"},
        elapsed_ms=30000,
    )

    assert outcome_ok.success is True
    assert outcome_fail.failure_type == "timeout"

    # Now configure Qdrant to return these as similar past outcomes
    mock_qdrant.search.return_value = [
        _scored_point(0.90, {
            "outcome_id": outcome_ok.outcome_id,
            "job_id": str(job.job_id),
            "agent_id": "hackathon",
            "task_type": "hackathon_registration",
            "success": True,
            "failure_type": "",
            "failure_detail": "",
            "recoverable": False,
            "execution_time_ms": 1500,
            "strategy_used": "standard",
            "created_at": time.time(),
        }),
        _scored_point(0.85, {
            "outcome_id": outcome_fail.outcome_id,
            "job_id": str(job.job_id),
            "agent_id": "hackathon",
            "task_type": "hackathon_registration",
            "success": False,
            "failure_type": "timeout",
            "failure_detail": "Request timed out after 30s",
            "recoverable": True,
            "execution_time_ms": 30000,
            "strategy_used": "standard",
            "created_at": time.time(),
        }),
    ]

    # Patch embed_text for the analyze_similar call
    async def _fake_embed(text, model=None):
        return [0.1] * 384

    with patch("agents.src.shared.embedding.embed_text", new=_fake_embed):
        pattern = await mem.analyze_similar(
            "Find hackathons in London",
            ["hackathon_registration"],
            "hackathon",
        )

    assert len(pattern.similar_outcomes) == 2
    assert abs(pattern.success_rate - 0.5) < 0.01
    mean_sim = (0.90 + 0.85) / 2
    expected_conf = 0.5 * mean_sim
    assert abs(pattern.confidence - expected_conf) < 0.01
    assert pattern.common_failures.get("timeout") == 1
    assert pattern.recommended_strategy in ("standard", "cautious", "human_assisted")
    logger.info(
        "ANALYZE: outcomes=%d success_rate=%.0f%% confidence=%.2f strategy=%s",
        len(pattern.similar_outcomes),
        pattern.success_rate * 100,
        pattern.confidence,
        pattern.recommended_strategy,
    )


@pytest.mark.asyncio
async def test_memory_adaptation_prompt_generation():
    """Verify build_adaptation_prompt produces a useful LLM preamble."""
    mem, _, mock_qdrant, _ = _make_mock_memory()

    # Set up a pattern with failures
    mock_qdrant.search.return_value = [
        _scored_point(0.88, {
            "outcome_id": "o1", "job_id": "1", "agent_id": "hackathon",
            "task_type": "hackathon_registration", "success": False,
            "failure_type": "captcha", "failure_detail": "CAPTCHA detected on devpost",
            "recoverable": True, "execution_time_ms": 5000,
            "strategy_used": "standard", "created_at": time.time(),
        }),
        _scored_point(0.82, {
            "outcome_id": "o2", "job_id": "2", "agent_id": "hackathon",
            "task_type": "hackathon_registration", "success": False,
            "failure_type": "captcha", "failure_detail": "CAPTCHA blocking registration",
            "recoverable": True, "execution_time_ms": 4500,
            "strategy_used": "standard", "created_at": time.time(),
        }),
    ]

    async def _fake_embed(text, model=None):
        return [0.1] * 384

    with patch("agents.src.shared.embedding.embed_text", new=_fake_embed):
        pattern = await mem.analyze_similar("EU hackathons devpost", [], "hackathon")

    prompt = build_adaptation_prompt(pattern)
    assert "HISTORICAL CONTEXT" in prompt
    assert "Success rate: 0%" in prompt
    assert "captcha" in prompt.lower()
    assert "ADAPT YOUR PLAN" in prompt
    assert pattern.recommended_strategy == "decline"  # 0% success → decline
    logger.info("ADAPTATION PROMPT (%d chars):\n%s", len(prompt), prompt[:300])


# ═════════════════════════════════════════════════════════════
#  Standalone runner with summary table
# ═════════════════════════════════════════════════════════════

AGENT_NAMES = [
    "hackathon",
    "gift_suggestion",
    "restaurant_booker",
    "smart_shopper",
    "trip_planner",
    "refund_claim",
    "caller",
]


async def _run_all():
    """Run all agent tests sequentially and print a summary table."""
    print("\n" + "=" * 72)
    print("  SOTA E2E Agent Test Harness — Butler Simulation + Memory")
    print("=" * 72)
    print(f"  Anthropic key: {'set' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING'}")
    print(f"  SerpAPI key:   {'set' if os.getenv('SERPAPI_API_KEY') else 'not set (optional)'}")
    print(f"  Bid window:    {BID_WINDOW}s")
    print("=" * 72 + "\n")

    results: list[dict] = []

    # ── Part 1: Agent execution ──────────────────────────────
    for name in AGENT_NAMES:
        print(f"\n{'─' * 60}")
        print(f"  Testing: {name}")
        print(f"{'─' * 60}")

        t0 = time.time()
        try:
            bid_result, agent = await _run_scenario(name)
            elapsed = time.time() - t0

            bid_ok = bid_result.winning_bid is not None
            exec_ok = bid_result.execution_result is not None
            success = False
            if isinstance(bid_result.execution_result, dict):
                success = bid_result.execution_result.get("success", False)

            results.append({
                "agent": name,
                "bid": "YES" if bid_ok else "NO",
                "executed": "YES" if exec_ok else "NO",
                "success": "PASS" if success else ("EXEC" if exec_ok else "FAIL"),
                "time": f"{elapsed:.1f}s",
                "error": "",
            })

            if isinstance(bid_result.execution_result, dict):
                err = bid_result.execution_result.get("error", "")
                if err:
                    results[-1]["error"] = str(err)[:60]

        except Exception as e:
            elapsed = time.time() - t0
            results.append({
                "agent": name,
                "bid": "ERR",
                "executed": "ERR",
                "success": "FAIL",
                "time": f"{elapsed:.1f}s",
                "error": str(e)[:60],
            })
            logger.exception("Agent %s failed", name)

    # ── Part 2: Memory integration ───────────────────────────
    print(f"\n{'─' * 60}")
    print("  Testing: TaskPatternMemory integration")
    print(f"{'─' * 60}")

    mem_tests = [
        ("memory_persist", test_memory_persist_on_agent_success),
        ("memory_failure_classify", test_memory_persist_failure_classification),
        ("memory_analyze", test_memory_analyze_after_multiple_outcomes),
        ("memory_adaptation", test_memory_adaptation_prompt_generation),
    ]
    for test_name, test_fn in mem_tests:
        t0 = time.time()
        try:
            await test_fn()
            elapsed = time.time() - t0
            results.append({
                "agent": test_name,
                "bid": "—",
                "executed": "—",
                "success": "PASS",
                "time": f"{elapsed:.1f}s",
                "error": "",
            })
        except Exception as e:
            elapsed = time.time() - t0
            results.append({
                "agent": test_name,
                "bid": "—",
                "executed": "—",
                "success": "FAIL",
                "time": f"{elapsed:.1f}s",
                "error": str(e)[:60],
            })
            logger.exception("Memory test %s failed", test_name)

    # ── Summary table ────────────────────────────────────────
    print("\n\n" + "=" * 72)
    print("  RESULTS SUMMARY")
    print("=" * 72)
    header = f"{'Agent':<25} {'Bid':>4} {'Exec':>5} {'Status':>6} {'Time':>7}  {'Error'}"
    print(header)
    print("─" * 72)

    pass_count = 0
    total = len(results)
    for r in results:
        line = f"{r['agent']:<25} {r['bid']:>4} {r['executed']:>5} {r['success']:>6} {r['time']:>7}"
        if r["error"]:
            line += f"  {r['error']}"
        print(line)
        if r["success"] == "PASS":
            pass_count += 1

    print("─" * 72)
    print(f"  {pass_count}/{total} passed")
    print("=" * 72 + "\n")

    return results


def main():
    results = asyncio.run(_run_all())
    failures = [r for r in results if r["success"] == "FAIL"]
    sys.exit(len(failures))


if __name__ == "__main__":
    main()
