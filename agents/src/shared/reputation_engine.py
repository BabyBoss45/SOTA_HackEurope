"""
Reputation engine for external ClawBot agents.

Score formula:
    reputation_score =
        (success_rate * 0.6)
      + (speed_factor  * 0.2)
      + (low_dispute_factor * 0.2)

Where:
    success_rate       = successfulJobs / totalJobs
    speed_factor       = 1 - min(1, avgExecutionTimeMs / 120_000)   [normalised to 2 min]
    low_dispute_factor = 1 - min(1, disputes / totalJobs)

New agents start at 0.5 (neutral).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


def compute_reputation_score(
    total_jobs: int,
    successful_jobs: int,
    avg_execution_time_ms: float,
    disputes: int,
) -> float:
    """
    Compute the 0.0–1.0 reputation score from raw stats.

    Returns 0.5 for brand-new agents with no job history.
    """
    if total_jobs == 0:
        return 0.5

    success_rate = successful_jobs / total_jobs
    speed_factor = max(0.0, 1.0 - avg_execution_time_ms / 120_000)
    low_dispute_factor = max(0.0, 1.0 - disputes / max(total_jobs, 1))

    score = (
        success_rate * 0.6
        + speed_factor * 0.2
        + low_dispute_factor * 0.2
    )
    return round(min(1.0, max(0.0, score)), 4)


async def update_reputation(
    agent_id: str,
    success: bool,
    execution_time_ms: int,
    confidence_submitted: Optional[float],
    failure_type: Optional[str],
    db_pool: asyncpg.Pool,
) -> None:
    """
    Upsert ExternalAgentReputation for the given agent after a job completes.

    Uses a running average for execution time to avoid storing every sample.
    """
    try:
        existing = await db_pool.fetchrow(
            'SELECT * FROM "ExternalAgentReputation" WHERE "agentId" = $1',
            agent_id,
        )

        prev_total = existing['totalJobs'] if existing else 0
        prev_successful = existing['successfulJobs'] if existing else 0
        prev_failed = existing['failedJobs'] if existing else 0
        prev_avg_ms = float(existing['avgExecutionTimeMs']) if existing else 0.0
        prev_disputes = existing['disputes'] if existing else 0
        prev_avg_conf_err = float(existing['avgConfidenceError']) if existing else 0.0

        new_total = prev_total + 1
        new_successful = prev_successful + (1 if success else 0)
        new_failed = prev_failed + (0 if success else 1)

        # Running average for execution time
        new_avg_ms = (
            float(execution_time_ms)
            if prev_total == 0
            else (prev_avg_ms * prev_total + execution_time_ms) / new_total
        )

        # Confidence error delta
        new_avg_conf_err = prev_avg_conf_err
        if confidence_submitted is not None:
            actual = 1.0 if success else 0.0
            delta = abs(confidence_submitted - actual)
            new_avg_conf_err = (
                delta
                if prev_total == 0
                else (prev_avg_conf_err * prev_total + delta) / new_total
            )

        # Update failure type counters
        prev_types: dict = {}
        if existing and existing['failureTypes']:
            raw = existing['failureTypes']
            prev_types = json.loads(raw) if isinstance(raw, str) else dict(raw)
        new_types = dict(prev_types)
        if not success and failure_type:
            new_types[failure_type] = new_types.get(failure_type, 0) + 1

        new_score = compute_reputation_score(
            new_total, new_successful, new_avg_ms, prev_disputes
        )

        await db_pool.execute(
            """
            INSERT INTO "ExternalAgentReputation" (
                "agentId", "totalJobs", "successfulJobs", "failedJobs",
                "avgExecutionTimeMs", "avgConfidenceError",
                "failureTypes", "reputationScore", "updatedAt"
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, NOW())
            ON CONFLICT ("agentId") DO UPDATE SET
                "totalJobs"          = EXCLUDED."totalJobs",
                "successfulJobs"     = EXCLUDED."successfulJobs",
                "failedJobs"         = EXCLUDED."failedJobs",
                "avgExecutionTimeMs" = EXCLUDED."avgExecutionTimeMs",
                "avgConfidenceError" = EXCLUDED."avgConfidenceError",
                "failureTypes"       = EXCLUDED."failureTypes",
                "reputationScore"    = EXCLUDED."reputationScore",
                "updatedAt"          = EXCLUDED."updatedAt"
            """,
            agent_id,
            new_total, new_successful, new_failed,
            new_avg_ms, new_avg_conf_err,
            json.dumps(new_types), new_score,
        )

        logger.info(
            "Reputation updated for agent %s: score=%.4f (total=%d, success=%d)",
            agent_id, new_score, new_total, new_successful,
        )
    except Exception as exc:
        logger.error("Failed to update reputation for agent %s: %s", agent_id, exc)
