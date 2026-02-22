"""
Single-use execution token management for the ClawBot external agent protocol.

Tokens are created when an external agent wins a bid and delivered to the agent
along with the execute payload.  They expire after TOKEN_TTL_MINUTES and can
only be consumed once (atomic DB UPDATE prevents replay attacks).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import asyncpg

TOKEN_TTL_MINUTES: int = 15


async def create_execution_token(
    job_id: str,
    agent_id: str,
    confidence: Optional[float],
    db_pool: asyncpg.Pool,
) -> str:
    """
    Insert a new single-use execution token and return its UUID string.

    Args:
        job_id:     The JobBoard job_id (UUID string).
        agent_id:   ExternalAgent.agentId (UUID string).
        confidence: The bid confidence the agent submitted (stored for later delta calc).
        db_pool:    asyncpg connection pool.

    Returns:
        The generated token UUID string.
    """
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)

    await db_pool.execute(
        """
        INSERT INTO "ExecutionToken"
            (token, "jobId", "agentId", "expiresAt", "confidenceSubmitted")
        VALUES ($1, $2, $3, $4, $5)
        """,
        token, job_id, agent_id, expires_at, confidence,
    )
    return token


async def validate_and_consume_token(
    token: str,
    job_id: str,
    db_pool: asyncpg.Pool,
) -> Tuple[bool, str]:
    """
    Atomically mark a token as used and return whether it was valid.

    Uses a single UPDATE...WHERE clause to prevent race conditions when the
    same token is submitted twice concurrently.

    Returns:
        (True, "") on success.
        (False, reason) on failure, where reason is one of:
            "Token not found", "Token already used", "Token expired", "Invalid token"
    """
    now = datetime.now(timezone.utc)

    result = await db_pool.fetchrow(
        """
        UPDATE "ExecutionToken"
        SET used = TRUE, "usedAt" = $1
        WHERE token = $2
          AND "jobId" = $3
          AND used = FALSE
          AND "expiresAt" > $1
        RETURNING id
        """,
        now, token, job_id,
    )

    if result is not None:
        return True, ""

    # Determine why it failed
    existing = await db_pool.fetchrow(
        'SELECT used, "expiresAt" FROM "ExecutionToken" WHERE token = $1',
        token,
    )
    if existing is None:
        return False, "Token not found"
    if existing['used']:
        return False, "Token already used"
    if existing['expiresAt'] <= now:
        return False, "Token expired"
    return False, "Invalid token"


async def expire_stale_tokens(db_pool: asyncpg.Pool) -> list[str]:
    """
    Find all expired, unused tokens and mark them as used.

    Returns the list of job_ids whose tokens expired (so callers can trigger refunds).
    """
    now = datetime.now(timezone.utc)
    rows = await db_pool.fetch(
        """
        UPDATE "ExecutionToken"
        SET used = TRUE, "usedAt" = $1
        WHERE used = FALSE AND "expiresAt" <= $1
        RETURNING "jobId"
        """,
        now,
    )
    return [row['jobId'] for row in rows]
