"""
Tests for the Adaptive Task Memory system (agents/src/shared/task_memory.py).

All external services (PostgreSQL, Qdrant, OpenAI embeddings) are mocked.
No env vars or network access required.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import time
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Import Workaround ───────────────────────────────────────
# The agents.src.__init__ and agents.src.shared.__init__ eagerly
# import heavy deps (web3, openai, etc.) which may not be installed
# in the test environment.  We load task_memory.py directly by file
# path so none of the __init__.py chains are triggered.

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "src" / "shared"

def _load_module_from_file(name: str, filepath: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, filepath)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# First, provide a fake embedding module that task_memory imports via
# ``from .embedding import embed_text``.  The relative import resolves
# to *agents.src.shared.embedding*, so we register a stub under that
# dotted name before loading task_memory.
_embedding_stub = ModuleType("agents.src.shared.embedding")
async def _noop_embed(text, model=None):
    return [0.0] * 384
_embedding_stub.embed_text = _noop_embed  # type: ignore[attr-defined]
sys.modules["agents.src.shared.embedding"] = _embedding_stub

# We also need the parent packages registered as packages (with __path__)
# so that the relative import `from .embedding import embed_text` works.
for _pkg_name, _pkg_path in [
    ("agents", _HERE.parent),
    ("agents.src", _HERE.parent / "src"),
    ("agents.src.shared", _SHARED),
]:
    if _pkg_name not in sys.modules:
        _pkg_mod = ModuleType(_pkg_name)
        _pkg_mod.__path__ = [str(_pkg_path)]  # type: ignore[attr-defined]
        sys.modules[_pkg_name] = _pkg_mod

# Stub qdrant_client.models so that ``from qdrant_client.models import ...``
# inside analyze_similar() doesn't blow up when the package isn't installed.
if "qdrant_client" not in sys.modules:
    _qc = ModuleType("qdrant_client")
    _qc.__path__ = []  # type: ignore[attr-defined]
    sys.modules["qdrant_client"] = _qc

    _qm = ModuleType("qdrant_client.models")

    class _Filter:
        def __init__(self, **kw): self.__dict__.update(kw)
    class _FieldCondition:
        def __init__(self, **kw): self.__dict__.update(kw)
    class _MatchValue:
        def __init__(self, **kw): self.__dict__.update(kw)
    class _Distance:
        COSINE = "Cosine"
    class _VectorParams:
        def __init__(self, **kw): self.__dict__.update(kw)

    _qm.Filter = _Filter  # type: ignore[attr-defined]
    _qm.FieldCondition = _FieldCondition  # type: ignore[attr-defined]
    _qm.MatchValue = _MatchValue  # type: ignore[attr-defined]
    _qm.Distance = _Distance  # type: ignore[attr-defined]
    _qm.VectorParams = _VectorParams  # type: ignore[attr-defined]
    sys.modules["qdrant_client.models"] = _qm

# Now load task_memory.py itself.
_tm_mod = _load_module_from_file(
    "agents.src.shared.task_memory",
    _SHARED / "task_memory.py",
)

RECOVERABLE_TYPES = _tm_mod.RECOVERABLE_TYPES
SIMILARITY_THRESHOLD = _tm_mod.SIMILARITY_THRESHOLD
PatternAnalysis = _tm_mod.PatternAnalysis
TaskOutcome = _tm_mod.TaskOutcome
TaskPatternMemory = _tm_mod.TaskPatternMemory
_empty_pattern = _tm_mod._empty_pattern
_infer_task_type = _tm_mod._infer_task_type
_select_strategy = _tm_mod._select_strategy
build_adaptation_prompt = _tm_mod.build_adaptation_prompt
classify_failure = _tm_mod.classify_failure
extract_context = _tm_mod.extract_context

# Patching target: the stub module where embed_text actually lives.
EMBED_PATCH_TARGET = "agents.src.shared.embedding.embed_text"


# ─── Helpers ──────────────────────────────────────────────────

EMBED_DIM = 384


async def fake_embed_text(text: str, model: str | None = None) -> list[float]:
    """Deterministic 384-dim vector from hash of input."""
    h = hashlib.sha256(text.encode()).digest()
    return [b / 255.0 for b in h] * (EMBED_DIM // 32)


@dataclass
class FakeJob:
    """Minimal stand-in for ActiveJob."""
    job_id: int = 42
    bid_id: int = 0
    job_type: int = 0
    description: str = "Register for EU hackathons on devpost"
    budget: int = 1_000_000
    deadline: int = 9999999999
    status: str = "in_progress"
    metadata_uri: str = ""
    params: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)


def _make_scored_point(score: float, payload: dict) -> SimpleNamespace:
    """Mimics a qdrant_client ScoredPoint."""
    return SimpleNamespace(score=score, payload=payload)


def make_query_response(scored_points: list) -> SimpleNamespace:
    """Mimics a qdrant_client QueryResponse (returned by query_points)."""
    return SimpleNamespace(points=scored_points)


def _failure_payload(
    failure_type: str = "captcha",
    success: bool = False,
    agent_id: str = "hackathon",
    execution_time_ms: int = 5000,
) -> dict:
    return {
        "outcome_id": "out-1",
        "job_id": "99",
        "agent_id": agent_id,
        "task_type": "hackathon_registration",
        "success": success,
        "failure_type": failure_type if not success else "",
        "failure_detail": f"{failure_type} error" if not success else "",
        "recoverable": failure_type in RECOVERABLE_TYPES if not success else False,
        "execution_time_ms": execution_time_ms,
        "strategy_used": "standard",
        "created_at": time.time(),
    }


# ═════════════════════════════════════════════════════════════
#  Layer 1: Pure function unit tests
# ═════════════════════════════════════════════════════════════


class TestClassifyFailure:
    def test_captcha(self):
        assert classify_failure({"error": "CAPTCHA detected on page"}) == "captcha"

    def test_recaptcha(self):
        assert classify_failure({"error": "recaptcha challenge required"}) == "captcha"

    def test_timeout(self):
        assert classify_failure({"error": "Request timed out after 30s"}) == "timeout"

    def test_auth_required(self):
        assert classify_failure({"error": "403 Forbidden"}) == "auth_required"

    def test_unauthorized(self):
        assert classify_failure({"error": "Unauthorized access"}) == "auth_required"

    def test_network(self):
        assert classify_failure({"error": "Connection refused"}) == "network"

    def test_network_502(self):
        assert classify_failure({"error": "502 Bad Gateway"}) == "network"

    def test_rate_limit(self):
        assert classify_failure({"error": "429 Too Many Requests"}) == "rate_limit"

    def test_not_found(self):
        assert classify_failure({"error": "404 page not found"}) == "not_found"

    def test_unknown(self):
        assert classify_failure({"error": "Something weird happened"}) == "unknown"

    def test_empty_error(self):
        assert classify_failure({}) == "unknown"

    def test_case_insensitive(self):
        assert classify_failure({"error": "TIMEOUT ON SERVER"}) == "timeout"


class TestExtractContext:
    def test_region_from_description(self):
        job = FakeJob(description="Find hackathons in EU")
        ctx = extract_context(job)
        assert ctx["region"] == "EU"

    def test_site_from_description(self):
        job = FakeJob(description="Search devpost for events")
        ctx = extract_context(job)
        assert ctx["site"] == "devpost"

    def test_region_and_site(self):
        job = FakeJob(description="EU hackathons on devpost")
        ctx = extract_context(job)
        assert ctx["region"] == "EU"
        assert ctx["site"] == "devpost"

    def test_keys_from_params(self):
        job = FakeJob(params={"region": "US", "site": "github"})
        ctx = extract_context(job)
        assert ctx["region"] == "US"
        assert ctx["site"] == "github"

    def test_params_take_priority_over_description(self):
        job = FakeJob(
            description="EU hackathons on devpost",
            params={"region": "ASIA"},
        )
        ctx = extract_context(job)
        assert ctx["region"] == "ASIA"

    def test_empty(self):
        job = FakeJob(description="generic task", params={})
        ctx = extract_context(job)
        assert ctx == {}


class TestInferTaskType:
    def test_from_tags_attr(self):
        job = FakeJob(tags=["hackathon_registration", "eu"])
        assert _infer_task_type(job) == "hackathon_registration"

    def test_from_params_tags(self):
        job = FakeJob(params={"tags": ["call_verification"]})
        assert _infer_task_type(job) == "call_verification"

    def test_fallback_generic(self):
        job = FakeJob(tags=[], params={})
        assert _infer_task_type(job) == "generic"


class TestSelectStrategy:
    def test_standard(self):
        assert _select_strategy(0.8) == "standard"
        assert _select_strategy(0.6) == "standard"

    def test_cautious(self):
        assert _select_strategy(0.5) == "cautious"
        assert _select_strategy(0.3) == "cautious"

    def test_human_assisted(self):
        assert _select_strategy(0.2) == "human_assisted"
        assert _select_strategy(0.15) == "human_assisted"

    def test_decline(self):
        assert _select_strategy(0.1) == "decline"
        assert _select_strategy(0.0) == "decline"


class TestEmptyPattern:
    def test_defaults(self):
        p = _empty_pattern()
        assert p.confidence == 1.0
        assert p.success_rate == 1.0
        assert p.recommended_strategy == "standard"
        assert p.similar_outcomes == []
        assert p.common_failures == {}


class TestBuildAdaptationPrompt:
    def test_empty_pattern_returns_empty(self):
        assert build_adaptation_prompt(_empty_pattern()) == ""

    def test_populated_pattern(self):
        outcome = TaskOutcome(
            outcome_id="x", job_id="1", agent_id="hackathon",
            task_type="hackathon_registration", description="",
            tags=[], context={}, success=False,
            failure_type="captcha", failure_detail="CAPTCHA detected",
            recoverable=True, execution_time_ms=5000,
            strategy_used="standard", created_at=0,
        )
        pattern = PatternAnalysis(
            similar_outcomes=[outcome],
            similarity_scores=[0.9],
            confidence=0.0,
            success_rate=0.0,
            common_failures={"captcha": 1},
            avg_execution_time_ms=5000,
            recommended_strategy="decline",
            reasoning="test",
        )
        prompt = build_adaptation_prompt(pattern)
        assert "HISTORICAL CONTEXT" in prompt
        assert "Success rate: 0%" in prompt
        assert "captcha (1x)" in prompt
        assert "Confidence: 0.00" in prompt
        assert "ADAPT YOUR PLAN" in prompt


# ═════════════════════════════════════════════════════════════
#  Layer 2: persist_outcome() -- TaskOutcome construction
# ═════════════════════════════════════════════════════════════


class TestPersistOutcome:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(return_value={"id": 1})
        return db

    @pytest.fixture
    def memory_db_only(self, mock_db):
        """TaskPatternMemory with database only (no Qdrant)."""
        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = mock_db
        mem.qdrant = None
        mem.incident_io = None
        return mem

    async def test_success_outcome(self, memory_db_only, mock_db):
        job = FakeJob(tags=["hackathon_registration"])
        result = {"success": True, "hackathons": []}

        outcome = await memory_db_only.persist_outcome(
            job=job, agent_id="hackathon", result=result, elapsed_ms=1200,
        )

        assert outcome.success is True
        assert outcome.failure_type is None
        assert outcome.failure_detail is None
        assert outcome.recoverable is False
        assert outcome.agent_id == "hackathon"
        assert outcome.execution_time_ms == 1200
        mock_db.store_task_outcome.assert_awaited_once()

    async def test_captcha_failure(self, memory_db_only):
        job = FakeJob(description="Register for EU hackathons on devpost")
        result = {"success": False, "error": "CAPTCHA detected"}

        outcome = await memory_db_only.persist_outcome(
            job=job, agent_id="hackathon", result=result, elapsed_ms=5000,
        )

        assert outcome.success is False
        assert outcome.failure_type == "captcha"
        assert outcome.recoverable is True
        assert "CAPTCHA" in (outcome.failure_detail or "")
        assert outcome.context.get("region") == "EU"
        assert outcome.context.get("site") == "devpost"

    async def test_network_failure(self, memory_db_only):
        result = {"success": False, "error": "Connection refused to target host"}

        outcome = await memory_db_only.persist_outcome(
            job=FakeJob(), agent_id="caller", result=result, elapsed_ms=300,
        )

        assert outcome.failure_type == "network"
        assert outcome.recoverable is True

    async def test_unknown_failure(self, memory_db_only):
        result = {"success": False, "error": "Something bizarre"}

        outcome = await memory_db_only.persist_outcome(
            job=FakeJob(), agent_id="caller", result=result, elapsed_ms=100,
        )

        assert outcome.failure_type == "unknown"
        assert outcome.recoverable is False

    async def test_db_called_with_dict(self, memory_db_only, mock_db):
        job = FakeJob(tags=["call_verification"])
        await memory_db_only.persist_outcome(
            job=job, agent_id="caller",
            result={"success": True}, elapsed_ms=800,
        )

        call_args = mock_db.store_task_outcome.call_args[0][0]
        assert isinstance(call_args, dict)
        assert "outcome_id" in call_args
        assert "agent_id" in call_args
        assert call_args["agent_id"] == "caller"
        assert call_args["success"] is True

    async def test_no_qdrant_still_works(self, memory_db_only, mock_db):
        """Without Qdrant configured, persist should still write to database."""
        await memory_db_only.persist_outcome(
            job=FakeJob(), agent_id="hackathon",
            result={"success": False, "error": "timeout"}, elapsed_ms=100,
        )
        mock_db.store_task_outcome.assert_awaited_once()

    async def test_no_incident_io_no_crash(self, memory_db_only):
        """Without incident.io client, persist should not raise."""
        outcome = await memory_db_only.persist_outcome(
            job=FakeJob(), agent_id="hackathon",
            result={"success": False, "error": "captcha"}, elapsed_ms=100,
        )
        assert outcome.success is False

    async def test_strategy_passed_through(self, memory_db_only):
        outcome = await memory_db_only.persist_outcome(
            job=FakeJob(), agent_id="hackathon",
            result={"success": True}, elapsed_ms=500,
            strategy="cautious",
        )
        assert outcome.strategy_used == "cautious"

    async def test_task_type_inferred(self, memory_db_only):
        job = FakeJob(tags=["hotel_booking"])
        outcome = await memory_db_only.persist_outcome(
            job=job, agent_id="caller",
            result={"success": True}, elapsed_ms=200,
        )
        assert outcome.task_type == "hotel_booking"

    async def test_db_error_swallowed(self):
        """Database failure should not crash persist_outcome."""
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(side_effect=RuntimeError("Database down"))

        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = db
        mem.qdrant = None
        mem.incident_io = None

        outcome = await mem.persist_outcome(
            job=FakeJob(), agent_id="hackathon",
            result={"success": False, "error": "test"}, elapsed_ms=100,
        )
        assert outcome.success is False


# ═════════════════════════════════════════════════════════════
#  Layer 3: analyze_similar() with mocked Qdrant
# ═════════════════════════════════════════════════════════════


class TestAnalyzeSimilar:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(return_value={"id": 1})
        return db

    def _make_memory(self, mock_db, qdrant=None):
        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = mock_db
        mem.qdrant = qdrant
        mem.incident_io = None
        return mem

    async def test_no_qdrant_returns_empty(self, mock_db):
        mem = self._make_memory(mock_db, qdrant=None)
        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.confidence == 1.0
        assert pattern.recommended_strategy == "standard"
        assert pattern.similar_outcomes == []

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_qdrant_empty_results(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.confidence == 1.0
        assert pattern.similar_outcomes == []

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_below_threshold_filtered(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.5, _failure_payload("captcha")),
            _make_scored_point(0.3, _failure_payload("timeout")),
        ])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.similar_outcomes == []
        assert pattern.confidence == 1.0

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_all_failures(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.85, _failure_payload("captcha")),
            _make_scored_point(0.80, _failure_payload("captcha")),
            _make_scored_point(0.75, _failure_payload("timeout")),
        ])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("EU hackathons", [], "hackathon")

        assert pattern.success_rate == 0.0
        assert pattern.confidence == 0.0
        assert pattern.recommended_strategy == "decline"
        assert pattern.common_failures == {"captcha": 2, "timeout": 1}
        assert len(pattern.similar_outcomes) == 3
        assert "captcha (2x)" in pattern.reasoning

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_mixed_results(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.90, _failure_payload("captcha", success=False)),
            _make_scored_point(0.85, _failure_payload("", success=True)),
            _make_scored_point(0.80, _failure_payload("", success=True)),
        ])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("EU hackathons", [], "hackathon")

        assert len(pattern.similar_outcomes) == 3
        assert abs(pattern.success_rate - 2 / 3) < 0.01
        mean_sim = (0.90 + 0.85 + 0.80) / 3
        expected_conf = (2 / 3) * mean_sim
        assert abs(pattern.confidence - expected_conf) < 0.01
        # confidence ~0.567 < 0.6 threshold -> cautious
        assert pattern.recommended_strategy == "cautious"

    @patch(
        EMBED_PATCH_TARGET,
        new_callable=lambda: AsyncMock(side_effect=RuntimeError("OpenAI down")),
    )
    async def test_embedding_failure_graceful(self, _mock_embed, mock_db):
        mock_q = MagicMock()
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.confidence == 1.0
        assert pattern.recommended_strategy == "standard"

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_qdrant_search_error_graceful(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.side_effect = RuntimeError("Qdrant connection lost")
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.confidence == 1.0
        assert pattern.recommended_strategy == "standard"

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_confidence_and_strategy_thresholds(self, mock_db):
        """success_rate=0.33 * mean_sim=0.85 => confidence ~0.28 => cautious"""
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.85, _failure_payload("captcha", success=False)),
            _make_scored_point(0.85, _failure_payload("timeout", success=False)),
            _make_scored_point(0.85, _failure_payload("", success=True)),
        ])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert abs(pattern.confidence - (1 / 3) * 0.85) < 0.01
        assert pattern.recommended_strategy == "human_assisted"

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_avg_execution_time(self, mock_db):
        mock_q = MagicMock()
        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.90, _failure_payload(execution_time_ms=1000)),
            _make_scored_point(0.80, _failure_payload(execution_time_ms=3000)),
        ])
        mem = self._make_memory(mock_db, qdrant=mock_q)

        pattern = await mem.analyze_similar("test", [], "hackathon")
        assert pattern.avg_execution_time_ms == 2000.0


# ═════════════════════════════════════════════════════════════
#  Layer 4: End-to-end flow (mocked infra)
# ═════════════════════════════════════════════════════════════


class TestEndToEnd:
    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_persist_then_analyze(self):
        """Full round-trip: persist a failure, then analyze with mocked Qdrant
        that returns the persisted data."""
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(return_value={"id": 1})

        captured_points: list = []

        def capture_upsert(collection_name, points):
            captured_points.extend(points)

        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        mock_q.upsert.side_effect = capture_upsert

        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = db
        mem.qdrant = mock_q
        mem.incident_io = None

        job = FakeJob(
            description="Register for EU hackathons on devpost",
            tags=["hackathon_registration"],
        )
        outcome = await mem.persist_outcome(
            job=job, agent_id="hackathon",
            result={"success": False, "error": "CAPTCHA detected"},
            elapsed_ms=5000,
        )

        assert outcome.failure_type == "captcha"
        assert len(captured_points) == 1

        upserted = captured_points[0]
        assert "payload" in upserted
        assert upserted["payload"]["failure_type"] == "captcha"
        assert upserted["payload"]["success"] is False

        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.92, upserted["payload"]),
        ])

        pattern = await mem.analyze_similar(
            "Sign up for European hackathons on devpost",
            ["hackathon_registration"],
            "hackathon",
        )

        assert len(pattern.similar_outcomes) == 1
        assert pattern.success_rate == 0.0
        assert pattern.confidence == 0.0
        assert pattern.recommended_strategy == "decline"
        assert pattern.common_failures == {"captcha": 1}

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_mixed_persist_then_analyze(self):
        """Persist 2 failures + 1 success, then verify aggregation."""
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(return_value={"id": 1})
        captured: list = []

        def capture(collection_name, points):
            captured.extend(points)

        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        mock_q.upsert.side_effect = capture

        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = db
        mem.qdrant = mock_q
        mem.incident_io = None

        job = FakeJob(description="EU hackathons", tags=["hackathon_registration"])

        await mem.persist_outcome(
            job=job, agent_id="hackathon",
            result={"success": False, "error": "CAPTCHA"}, elapsed_ms=3000,
        )
        await mem.persist_outcome(
            job=job, agent_id="hackathon",
            result={"success": False, "error": "timeout"}, elapsed_ms=7000,
        )
        await mem.persist_outcome(
            job=job, agent_id="hackathon",
            result={"success": True}, elapsed_ms=2000,
        )

        assert len(captured) == 3

        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.88, captured[0]["payload"]),
            _make_scored_point(0.85, captured[1]["payload"]),
            _make_scored_point(0.82, captured[2]["payload"]),
        ])

        pattern = await mem.analyze_similar("EU hackathons", [], "hackathon")

        assert len(pattern.similar_outcomes) == 3
        assert abs(pattern.success_rate - 1 / 3) < 0.01
        assert pattern.common_failures.get("captcha") == 1
        assert pattern.common_failures.get("timeout") == 1
        mean_sim = (0.88 + 0.85 + 0.82) / 3
        expected_conf = (1 / 3) * mean_sim
        assert abs(pattern.confidence - expected_conf) < 0.01

    @patch(EMBED_PATCH_TARGET, new=fake_embed_text)
    async def test_adaptation_prompt_from_analysis(self):
        """Verify the full chain: persist -> analyze -> prompt generation."""
        db = AsyncMock()
        db.store_task_outcome = AsyncMock(return_value={"id": 1})
        captured: list = []

        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        mock_q.upsert.side_effect = lambda collection_name, points: captured.extend(points)

        mem = TaskPatternMemory.__new__(TaskPatternMemory)
        mem.db = db
        mem.qdrant = mock_q
        mem.incident_io = None

        job = FakeJob(description="EU hackathons", tags=["hackathon_registration"])
        await mem.persist_outcome(
            job=job, agent_id="hackathon",
            result={"success": False, "error": "CAPTCHA blocking registration"},
            elapsed_ms=4000,
        )

        mock_q.query_points.return_value = make_query_response([
            _make_scored_point(0.91, captured[0]["payload"]),
        ])

        pattern = await mem.analyze_similar("EU hackathons", [], "hackathon")
        prompt = build_adaptation_prompt(pattern)

        assert "HISTORICAL CONTEXT" in prompt
        assert "Success rate: 0%" in prompt
        assert "ADAPT YOUR PLAN" in prompt
        assert "captcha" in prompt.lower()
