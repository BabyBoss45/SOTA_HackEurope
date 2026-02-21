"""
Task Memory — Structured outcome persistence + similarity-based pattern detection.

Dual storage:
  PostgreSQL = source of truth (structured data, analytics, UI)
  Qdrant     = experience retrieval layer (embeddings for similarity search)

Usage::

    memory = TaskPatternMemory(db=database)
    await memory.persist_outcome(job, agent_id="hackathon", result=result, elapsed_ms=1820)
    pattern = await memory.analyze_similar("Register for EU hackathons", ["hackathon_registration"], "hackathon")
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "task_outcomes"
SIMILARITY_THRESHOLD = 0.70
_EMBED_DIM: Optional[int] = None


def _get_embed_dim() -> int:
    """Detect embedding dimension from the active model (cached after first call)."""
    global _EMBED_DIM
    if _EMBED_DIM is not None:
        return _EMBED_DIM
    try:
        import asyncio
        from .embedding import embed_text
        vec = asyncio.get_event_loop().run_until_complete(embed_text("dim_probe"))
        _EMBED_DIM = len(vec)
    except Exception:
        _EMBED_DIM = 384  # safe fallback for all-MiniLM-L6-v2
    logger.info("Detected embedding dimension: %d", _EMBED_DIM)
    return _EMBED_DIM


# ─── Failure Classification ──────────────────────────────────

FAILURE_PATTERNS: Dict[str, List[str]] = {
    "captcha": ["captcha", "recaptcha", "challenge"],
    "timeout": ["timeout", "timed out", "deadline exceeded"],
    "auth_required": ["auth", "login", "403", "unauthorized", "permission"],
    "network": ["connection", "dns", "unreachable", "502", "503"],
    "rate_limit": ["rate limit", "429", "too many requests"],
    "not_found": ["not found", "404", "no results"],
}

RECOVERABLE_TYPES = {"captcha", "timeout", "network", "rate_limit"}


def classify_failure(result: dict) -> str:
    """Classify failure type from error string using keyword matching."""
    error = str(result.get("error", "")).lower()
    for ftype, keywords in FAILURE_PATTERNS.items():
        if any(kw in error for kw in keywords):
            return ftype
    return "unknown"


def extract_context(job: Any) -> dict:
    """Pull structured context from job metadata and description."""
    ctx: dict = {}
    params = getattr(job, "params", {}) or {}
    metadata = params if isinstance(params, dict) else {}

    for key in ("region", "site", "location", "platform", "url", "phone_number"):
        val = metadata.get(key)
        if val:
            ctx[key] = val

    desc = getattr(job, "description", "") or ""
    desc_lower = desc.lower()
    for region in ("eu", "europe", "us", "usa", "asia", "uk"):
        if region in desc_lower:
            ctx.setdefault("region", region.upper())
            break

    for site in ("devpost", "github", "linkedin", "indeed", "glassdoor"):
        if site in desc_lower:
            ctx.setdefault("site", site)
            break

    return ctx


def _infer_task_type(job: Any) -> str:
    """Derive task_type from the first tag or fall back to 'generic'."""
    tags = getattr(job, "tags", None)
    if not tags:
        params = getattr(job, "params", {}) or {}
        tags = params.get("tags", [])
    if tags and isinstance(tags, list) and len(tags) > 0:
        return str(tags[0])
    return "generic"


# ─── Data Structures ─────────────────────────────────────────

@dataclass
class TaskOutcome:
    outcome_id: str
    job_id: str
    agent_id: str
    task_type: str
    description: str
    tags: List[str]
    context: dict
    success: bool
    failure_type: Optional[str]
    failure_detail: Optional[str]
    recoverable: bool
    execution_time_ms: int
    strategy_used: str
    created_at: float


@dataclass
class PatternAnalysis:
    similar_outcomes: List[TaskOutcome]
    similarity_scores: List[float]
    confidence: float
    success_rate: float
    common_failures: Dict[str, int]
    avg_execution_time_ms: float
    recommended_strategy: str
    reasoning: str


def _empty_pattern() -> PatternAnalysis:
    """Safe default when no history exists or Qdrant is unavailable."""
    return PatternAnalysis(
        similar_outcomes=[],
        similarity_scores=[],
        confidence=1.0,
        success_rate=1.0,
        common_failures={},
        avg_execution_time_ms=0,
        recommended_strategy="standard",
        reasoning="No historical data available.",
    )


def _select_strategy(confidence: float) -> str:
    if confidence >= 0.6:
        return "standard"
    if confidence >= 0.3:
        return "cautious"
    if confidence >= 0.15:
        return "human_assisted"
    return "decline"


def build_adaptation_prompt(pattern: PatternAnalysis) -> str:
    """Build an LLM preamble from historical pattern analysis."""
    if not pattern.similar_outcomes:
        return ""
    failures_str = "; ".join(
        o.failure_detail for o in pattern.similar_outcomes
        if o.failure_detail
    )[:300]
    common = ", ".join(f"{k} ({v}x)" for k, v in pattern.common_failures.items())
    return (
        f"HISTORICAL CONTEXT ({len(pattern.similar_outcomes)} similar past tasks):\n"
        f"- Success rate: {pattern.success_rate:.0%}\n"
        f"- Common failures: {common}\n"
        f"- Confidence: {pattern.confidence:.2f}\n"
        f"- Recommended strategy: {pattern.recommended_strategy}\n"
        f"Failure details: {failures_str}\n"
        "ADAPT YOUR PLAN to avoid these known failure modes.\n\n"
    )


# ─── Task Pattern Memory ─────────────────────────────────────

class TaskPatternMemory:
    """
    Dual-write outcome store with similarity-based pattern retrieval.

    PostgreSQL = source of truth (structured records).
    Qdrant     = experience retrieval (embedding similarity search).
    """

    def __init__(
        self,
        db: Any,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        incident_io_client: Any = None,
    ):
        self.db = db
        self.incident_io = incident_io_client
        self.qdrant = self._init_qdrant(qdrant_url, qdrant_api_key)
        if self.qdrant:
            self._ensure_collection()

    # ── Qdrant lifecycle ──────────────────────────────────────

    @staticmethod
    def _init_qdrant(url: Optional[str], api_key: Optional[str]):
        try:
            from qdrant_client import QdrantClient  # type: ignore
            resolved_url = url or os.getenv("QDRANT_URL")
            if not resolved_url:
                logger.info("QDRANT_URL not set — task memory will use PostgreSQL only")
                return None
            return QdrantClient(
                url=resolved_url,
                api_key=api_key or os.getenv("QDRANT_API_KEY"),
            )
        except Exception as exc:
            logger.warning("Qdrant client init failed: %s", exc)
            return None

    def _ensure_collection(self) -> None:
        if not self.qdrant:
            return
        try:
            from qdrant_client.models import Distance, VectorParams  # type: ignore
            if not self.qdrant.collection_exists(QDRANT_COLLECTION):
                dim = _get_embed_dim()
                self.qdrant.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection '%s'", QDRANT_COLLECTION)
        except Exception as exc:
            logger.warning("Qdrant ensure collection failed: %s", exc)

    # ── Persist ───────────────────────────────────────────────

    async def persist_outcome(
        self,
        job: Any,
        agent_id: str,
        result: dict,
        elapsed_ms: int,
        strategy: str = "standard",
        pattern_hint: Optional[PatternAnalysis] = None,
    ) -> TaskOutcome:
        """
        Build a structured TaskOutcome and write it to PostgreSQL + Qdrant.

        ``pattern_hint`` is the pre-execution PatternAnalysis (if available).
        It's forwarded to ``_notify_incident_io`` so severity can escalate
        for recurring failure patterns.
        """
        success = bool(result.get("success"))
        failure_type = classify_failure(result) if not success else None
        failure_detail = str(result.get("error", ""))[:500] if not success else None
        tags = getattr(job, "tags", None) or []
        if not tags:
            params = getattr(job, "params", {}) or {}
            tags = params.get("tags", []) if isinstance(params, dict) else []

        outcome = TaskOutcome(
            outcome_id=str(uuid4()),
            job_id=str(getattr(job, "job_id", "")),
            agent_id=agent_id,
            task_type=_infer_task_type(job),
            description=getattr(job, "description", "") or "",
            tags=list(tags),
            context=extract_context(job),
            success=success,
            failure_type=failure_type,
            failure_detail=failure_detail,
            recoverable=failure_type in RECOVERABLE_TYPES if failure_type else False,
            execution_time_ms=elapsed_ms,
            strategy_used=strategy,
            created_at=time.time(),
        )

        # 1. PostgreSQL (always)
        await self._persist_db(outcome)

        # 2. Qdrant (if available)
        await self._persist_qdrant(outcome)

        # 3. incident.io alert/resolve (severity uses pattern_hint)
        await self._notify_incident_io(outcome, pattern=pattern_hint)

        return outcome

    async def _persist_db(self, outcome: TaskOutcome) -> None:
        if not self.db:
            return
        try:
            await self.db.store_task_outcome(asdict(outcome))
        except Exception as exc:
            logger.warning("Database task outcome write failed: %s", exc)

    async def _persist_qdrant(self, outcome: TaskOutcome) -> None:
        if not self.qdrant:
            return
        try:
            from .embedding import embed_text

            embed_input = (
                f"{outcome.description} | {outcome.task_type} | "
                f"{json.dumps(outcome.context)} | failure:{outcome.failure_type}"
            )
            vector = await embed_text(embed_input)

            payload = {
                "outcome_id": outcome.outcome_id,
                "job_id": outcome.job_id,
                "agent_id": outcome.agent_id,
                "task_type": outcome.task_type,
                "success": outcome.success,
                "failure_type": outcome.failure_type or "",
                "failure_detail": outcome.failure_detail or "",
                "recoverable": outcome.recoverable,
                "execution_time_ms": outcome.execution_time_ms,
                "strategy_used": outcome.strategy_used,
                "created_at": outcome.created_at,
            }

            self.qdrant.upsert(
                collection_name=QDRANT_COLLECTION,
                points=[{
                    "id": outcome.outcome_id,
                    "vector": vector,
                    "payload": payload,
                }],
            )
            logger.debug("Qdrant upsert OK for outcome %s", outcome.outcome_id)
        except Exception as exc:
            logger.warning("Qdrant task outcome upsert failed: %s", exc)

    def _compute_severity(
        self,
        outcome: TaskOutcome,
        pattern: Optional[PatternAnalysis] = None,
    ) -> str:
        """Derive alert severity from outcome + historical pattern.

        Recurring failures with low confidence escalate to critical.
        """
        if pattern and pattern.confidence < 0.3 and len(pattern.similar_outcomes) >= 2:
            return "critical"
        if outcome.failure_type in ("network", "timeout"):
            return "medium"
        if outcome.recoverable:
            return "high"
        return "high"

    async def _notify_incident_io(
        self,
        outcome: TaskOutcome,
        pattern: Optional[PatternAnalysis] = None,
    ) -> None:
        """Fire or resolve an incident.io alert based on TaskOutcome."""
        if not self.incident_io:
            return
        try:
            if not outcome.success:
                severity = self._compute_severity(outcome, pattern)
                await self.incident_io.create_alert(
                    title=f"Job #{outcome.job_id} failed: {outcome.agent_id} — {outcome.failure_type}",
                    description=f"{outcome.description}\n\nFailure: {outcome.failure_detail}",
                    metadata={
                        "job_id": outcome.job_id,
                        "agent_id": outcome.agent_id,
                        "task_type": outcome.task_type,
                        "failure_type": outcome.failure_type,
                        "execution_time_ms": outcome.execution_time_ms,
                        "context": outcome.context,
                        "recoverable": outcome.recoverable,
                        "strategy_used": outcome.strategy_used,
                    },
                    dedup_key=f"sota-job-{outcome.job_id}",
                    status="firing",
                    severity=severity,
                )
            else:
                await self.incident_io.resolve_alert(
                    dedup_key=f"sota-job-{outcome.job_id}",
                )
        except Exception as exc:
            logger.warning("incident.io notification failed: %s", exc)

    # ── Analyze ───────────────────────────────────────────────

    async def analyze_similar(
        self,
        description: str,
        tags: List[str],
        agent_id: str,
    ) -> PatternAnalysis:
        """
        Find similar past task outcomes and compute confidence + strategy.
        Returns a safe default if Qdrant is unavailable.
        """
        if not self.qdrant:
            return _empty_pattern()

        try:
            from .embedding import embed_text
            vector = await embed_text(description)
        except Exception as exc:
            logger.warning("Embedding failed in analyze_similar: %s", exc)
            return _empty_pattern()

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            query_filter = Filter(
                must=[FieldCondition(key="agent_id", match=MatchValue(value=agent_id))]
            )

            response = self.qdrant.query_points(
                collection_name=QDRANT_COLLECTION,
                query=vector,
                limit=5,
                query_filter=query_filter,
            )
            results = response.points
        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return _empty_pattern()

        if not results:
            return _empty_pattern()

        similar: List[TaskOutcome] = []
        scores: List[float] = []

        for hit in results:
            score = getattr(hit, "score", 0.0)
            if score < SIMILARITY_THRESHOLD:
                continue
            payload = getattr(hit, "payload", {}) or {}
            outcome = TaskOutcome(
                outcome_id=payload.get("outcome_id", ""),
                job_id=payload.get("job_id", ""),
                agent_id=payload.get("agent_id", ""),
                task_type=payload.get("task_type", ""),
                description="",
                tags=[],
                context={},
                success=payload.get("success", False),
                failure_type=payload.get("failure_type") or None,
                failure_detail=payload.get("failure_detail") or None,
                recoverable=payload.get("recoverable", False),
                execution_time_ms=payload.get("execution_time_ms", 0),
                strategy_used=payload.get("strategy_used", "standard"),
                created_at=payload.get("created_at", 0),
            )
            similar.append(outcome)
            scores.append(score)

        if not similar:
            return _empty_pattern()

        successes = sum(1 for o in similar if o.success)
        success_rate = successes / len(similar)
        mean_similarity = sum(scores) / len(scores)
        confidence = success_rate * mean_similarity

        failure_counts: Counter = Counter()
        for o in similar:
            if o.failure_type and not o.success:
                failure_counts[o.failure_type] += 1

        avg_time = sum(o.execution_time_ms for o in similar) / len(similar)
        strategy = _select_strategy(confidence)

        parts = [f"Found {len(similar)} similar past tasks (avg similarity {mean_similarity:.2f})."]
        parts.append(f"Success rate: {success_rate:.0%}.")
        if failure_counts:
            top = ", ".join(f"{k} ({v}x)" for k, v in failure_counts.most_common(3))
            parts.append(f"Common failures: {top}.")
        parts.append(f"Confidence: {confidence:.2f} — strategy: {strategy}.")

        return PatternAnalysis(
            similar_outcomes=similar,
            similarity_scores=scores,
            confidence=confidence,
            success_rate=success_rate,
            common_failures=dict(failure_counts),
            avg_execution_time_ms=avg_time,
            recommended_strategy=strategy,
            reasoning=" ".join(parts),
        )
