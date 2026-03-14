"""
Database -- Async PostgreSQL interface for SOTA agents (asyncpg).

Drop-in replacement for the previous database class.  Every public
method has the same signature and return shape so callers (butler_comms,
butler_api, etc.) keep working unchanged.

Tables (mirroring Prisma schema -- PascalCase):
  "UserProfile", "MarketplaceJob", "AgentDataRequest",
  "AgentJobUpdate", "CallSummary"

Usage::

    from agents.src.shared.database import Database

    db = await Database.connect()
    profile = await db.get_user_profile("default")
    await db.upsert_user_profile("default", {"full_name": "Alice"})
    await db.close()
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg  # type: ignore

logger = logging.getLogger(__name__)

_JSON_COLUMNS = frozenset(("metadata", "data", "answerData", "preferences", "extra", "payload"))
_DATETIME_COLUMNS = frozenset(("createdAt", "updatedAt", "answeredAt", "lastHeartbeat", "connectedAt"))


def _now() -> datetime:
    # Prisma creates timestamp(3) WITHOUT time zone columns;
    # asyncpg rejects offset-aware datetimes for those columns.
    return datetime.utcnow()


def _prepare_jsonb(value: Any) -> Any:
    """Prepare a Python object for asyncpg JSONB insertion.

    asyncpg registers a built-in codec for ``jsonb`` that calls
    ``json.dumps()`` on the value before sending it to PostgreSQL.
    We must therefore pass the raw Python object (dict / list / scalar),
    **not** a pre-serialised JSON string, to avoid double-encoding.

    The round-trip through dumps/loads normalises non-JSON-native types
    (e.g. ``datetime``) into strings so asyncpg's encoder never chokes.
    """
    if value is None:
        return None
    # Round-trip to normalise datetime, Decimal, etc. into JSON-safe types
    return json.loads(json.dumps(value, default=str))


def _ensure_decoded_json(value: Any) -> Any:
    """Ensure a JSONB value is a Python object, not a raw JSON string.

    asyncpg's built-in codec normally returns dicts/lists directly.
    This handles the edge case where a value was stored as a double-encoded
    JSON string (legacy data) by attempting one extra ``json.loads``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _row_to_dict(row: asyncpg.Record | None) -> dict | None:
    """Convert an asyncpg Record to a plain dict with JSON fields decoded."""
    if row is None:
        return None
    d = dict(row)
    for key in _JSON_COLUMNS:
        if key in d:
            d[key] = _ensure_decoded_json(d[key])
    for key in _DATETIME_COLUMNS:
        if key in d and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


class Database:
    """Async PostgreSQL helper (singleton-capable, drop-in replacement)."""

    _instance: Optional["Database"] = None

    def __init__(self, pool: asyncpg.Pool | None = None):
        self._pool: asyncpg.Pool | None = pool

    async def initialize(self) -> None:
        """Initialize connection pool. No-op if already connected."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(_get_database_url())
        logger.info("Connected to PostgreSQL")

    @classmethod
    async def connect(cls) -> "Database":
        """Create (or return cached) Database instance with a connection pool."""
        if cls._instance is not None:
            return cls._instance
        pool = await asyncpg.create_pool(_get_database_url())
        cls._instance = cls(pool)
        logger.info("Connected to PostgreSQL")
        return cls._instance

    async def close(self) -> None:
        """Close the connection pool and reset the singleton."""
        if self._pool:
            await self._pool.close()
        logger.info("PostgreSQL connection pool closed")
        Database._instance = None

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # =====================================================================
    #  UserProfile
    # =====================================================================

    async def get_user_profile(self, user_id: str = "default") -> dict | None:
        """Return profile dict or None."""
        row = await self._pool.fetchrow(
            'SELECT * FROM "UserProfile" WHERE "userId" = $1',
            user_id,
        )
        return _row_to_dict(row)

    async def upsert_user_profile(self, user_id: str, data: dict) -> dict:
        """Create or update a user profile. Returns the stored row."""
        col_map = {
            "full_name": "fullName",
            "email": "email",
            "phone": "phone",
            "location": "location",
            "skills": "skills",
            "experience_level": "experienceLevel",
            "github_url": "githubUrl",
            "linkedin_url": "linkedinUrl",
            "portfolio_url": "portfolioUrl",
            "bio": "bio",
        }

        known: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        # Use .get() instead of .pop() to avoid mutating the caller's dict
        prefs = data.get("preferences", None)

        for k, v in data.items():
            if k == "preferences":
                continue
            if k in col_map:
                known[col_map[k]] = v
            elif k in col_map.values():
                known[k] = v
            else:
                extra[k] = v

        now = _now()

        # Build SET clause dynamically for the known columns
        set_parts: list[str] = ['"updatedAt" = $3']
        values: list[Any] = [user_id, now, now]  # $1=userId, $2=createdAt, $3=updatedAt
        idx = 4

        for col, val in known.items():
            set_parts.append(f'"{col}" = ${idx}')
            values.append(val)
            idx += 1

        if prefs is not None:
            set_parts.append(f'"preferences" = ${idx}')
            values.append(_prepare_jsonb(prefs))
            idx += 1

        if extra:
            set_parts.append(f'"extra" = ${idx}')
            values.append(_prepare_jsonb(extra))
            idx += 1

        # Build INSERT columns/values
        insert_cols = ['"userId"', '"createdAt"', '"updatedAt"']
        insert_vals = ["$1", "$2", "$3"]

        param_idx = 4
        for col in known:
            insert_cols.append(f'"{col}"')
            insert_vals.append(f"${param_idx}")
            param_idx += 1

        if prefs is not None:
            insert_cols.append('"preferences"')
            insert_vals.append(f"${param_idx}")
            param_idx += 1

        if extra:
            insert_cols.append('"extra"')
            insert_vals.append(f"${param_idx}")
            param_idx += 1

        sql = (
            f'INSERT INTO "UserProfile" ({", ".join(insert_cols)}) '
            f"VALUES ({', '.join(insert_vals)}) "
            f'ON CONFLICT ("userId") DO UPDATE SET {", ".join(set_parts)}'
        )

        await self._pool.execute(sql, *values)
        return await self.get_user_profile(user_id) or {}

    # =====================================================================
    #  MarketplaceJob
    # =====================================================================

    async def create_job(
        self,
        job_id: str,
        description: str,
        tags: list[str],
        budget_usdc: float = 0,
        poster: str = "",
        metadata: dict | None = None,
    ) -> dict:
        now = _now()
        row = await self._pool.fetchrow(
            """
            INSERT INTO "MarketplaceJob"
                ("jobId", "description", "tags", "budgetUsdc",
                 "status", "poster", "winner", "winnerPrice",
                 "metadata", "createdAt", "updatedAt")
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
            """,
            job_id,
            description,
            tags,
            budget_usdc,
            "open",
            poster,
            None,
            None,
            _prepare_jsonb(metadata or {}),
            now,
            now,
        )
        return _row_to_dict(row) or {}

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        winner: str | None = None,
        winner_price: float | None = None,
    ) -> dict | None:
        now = _now()

        set_parts = ['"status" = $2', '"updatedAt" = $3']
        values: list[Any] = [job_id, status, now]
        idx = 4

        if winner is not None:
            set_parts.append(f'"winner" = ${idx}')
            values.append(winner)
            idx += 1
        if winner_price is not None:
            set_parts.append(f'"winnerPrice" = ${idx}')
            values.append(winner_price)
            idx += 1

        sql = f'UPDATE "MarketplaceJob" SET {", ".join(set_parts)} WHERE "jobId" = $1 RETURNING *'
        row = await self._pool.fetchrow(sql, *values)
        return _row_to_dict(row)

    async def get_job(self, job_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            'SELECT * FROM "MarketplaceJob" WHERE "jobId" = $1',
            job_id,
        )
        return _row_to_dict(row)

    async def list_jobs(self, status: str | None = None, limit: int = 50) -> list[dict]:
        if status:
            rows = await self._pool.fetch(
                'SELECT * FROM "MarketplaceJob" WHERE "status" = $1 ORDER BY "createdAt" DESC LIMIT $2',
                status,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                'SELECT * FROM "MarketplaceJob" ORDER BY "createdAt" DESC LIMIT $1',
                limit,
            )
        return [_row_to_dict(r) for r in rows]

    # =====================================================================
    #  AgentDataRequest
    # =====================================================================

    async def create_data_request(
        self,
        request_id: str,
        job_id: str,
        agent: str,
        data_type: str,
        question: str,
        fields: list[str] | None = None,
        context: str = "",
    ) -> dict:
        now = _now()
        row = await self._pool.fetchrow(
            """
            INSERT INTO "AgentDataRequest"
                ("requestId", "jobId", "agent", "dataType", "question",
                 "fields", "context", "status", "answerData", "answerMsg",
                 "createdAt", "answeredAt")
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            request_id,
            job_id,
            agent,
            data_type,
            question,
            fields or [],
            context,
            "pending",
            None,
            None,
            now,
            None,
        )
        return _row_to_dict(row) or {}

    async def answer_data_request(
        self,
        request_id: str,
        answer_data: dict,
        message: str = "",
    ) -> dict | None:
        now = _now()
        row = await self._pool.fetchrow(
            """
            UPDATE "AgentDataRequest"
            SET "status" = $2,
                "answerData" = $3,
                "answerMsg" = $4,
                "answeredAt" = $5
            WHERE "requestId" = $1
            RETURNING *
            """,
            request_id,
            "answered",
            _prepare_jsonb(answer_data),
            message,
            now,
        )
        return _row_to_dict(row)

    async def get_pending_requests(self, job_id: str | None = None) -> list[dict]:
        if job_id:
            rows = await self._pool.fetch(
                'SELECT * FROM "AgentDataRequest" WHERE "status" = $1 AND "jobId" = $2 ORDER BY "createdAt"',
                "pending",
                job_id,
            )
        else:
            rows = await self._pool.fetch(
                'SELECT * FROM "AgentDataRequest" WHERE "status" = $1 ORDER BY "createdAt"',
                "pending",
            )
        return [_row_to_dict(r) for r in rows]

    async def get_data_request(self, request_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            'SELECT * FROM "AgentDataRequest" WHERE "requestId" = $1',
            request_id,
        )
        return _row_to_dict(row)

    # =====================================================================
    #  AgentJobUpdate
    # =====================================================================

    async def create_update(
        self,
        job_id: str,
        agent: str,
        status: str,
        message: str,
        data: dict | None = None,
    ) -> dict:
        now = _now()
        row = await self._pool.fetchrow(
            """
            INSERT INTO "AgentJobUpdate"
                ("jobId", "agent", "status", "message", "data", "createdAt")
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            job_id,
            agent,
            status,
            message,
            _prepare_jsonb(data or {}),
            now,
        )
        return _row_to_dict(row) or {}

    async def get_updates(self, job_id: str) -> list[dict]:
        rows = await self._pool.fetch(
            'SELECT * FROM "AgentJobUpdate" WHERE "jobId" = $1 ORDER BY "createdAt"',
            job_id,
        )
        return [_row_to_dict(r) for r in rows]

    # =====================================================================
    #  CallSummary
    # =====================================================================

    async def create_call_summary(
        self,
        conversation_id: str | None = None,
        call_sid: str | None = None,
        status: str | None = None,
        summary: str | None = None,
        to_number: str | None = None,
        job_id: str | None = None,
        storage_uri: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        now = _now()
        row = await self._pool.fetchrow(
            """
            INSERT INTO "CallSummary"
                ("conversationId", "callSid", "status", "summary",
                 "toNumber", "jobId", "storageUri", "payload", "createdAt")
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            conversation_id,
            call_sid,
            status,
            summary,
            to_number,
            job_id,
            storage_uri,
            _prepare_jsonb(payload),
            now,
        )
        return _row_to_dict(row) or {}

    # =====================================================================
    #  WorkerAgent
    # =====================================================================

    async def upsert_worker_agent(
        self,
        worker_id: str,
        name: str,
        *,
        tags: list[str] | None = None,
        version: str = "1.0.0",
        wallet_address: str | None = None,
        capabilities: list[str] | None = None,
        status: str = "online",
        max_concurrent: int = 5,
        bid_price_ratio: float = 0.80,
        bid_eta_seconds: int = 1800,
        min_profit_margin: float = 0.1,
        icon: str | None = None,
        metadata: dict | None = None,
        api_endpoint: str | None = None,
        source: str = "sdk",
        description: str | None = None,
    ) -> dict:
        """Insert or update a worker agent. Preserves stats on conflict."""
        now = _now()
        row = await self._pool.fetchrow(
            """
            INSERT INTO "WorkerAgent"
                ("workerId", "name", "description", "tags", "version",
                 "walletAddress", "capabilities", "status",
                 "lastHeartbeat", "connectedAt",
                 "maxConcurrent", "bidPriceRatio", "bidEtaSeconds",
                 "minProfitMargin", "icon", "metadata", "apiEndpoint",
                 "source", "createdAt", "updatedAt")
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            ON CONFLICT ("workerId") DO UPDATE SET
                "name"            = EXCLUDED."name",
                "description"     = COALESCE(EXCLUDED."description", "WorkerAgent"."description"),
                "tags"            = EXCLUDED."tags",
                "version"         = EXCLUDED."version",
                "walletAddress"   = COALESCE(EXCLUDED."walletAddress", "WorkerAgent"."walletAddress"),
                "capabilities"    = EXCLUDED."capabilities",
                "status"          = EXCLUDED."status",
                "lastHeartbeat"   = EXCLUDED."lastHeartbeat",
                "connectedAt"     = EXCLUDED."connectedAt",
                "maxConcurrent"   = EXCLUDED."maxConcurrent",
                "bidPriceRatio"   = EXCLUDED."bidPriceRatio",
                "bidEtaSeconds"   = EXCLUDED."bidEtaSeconds",
                "minProfitMargin" = EXCLUDED."minProfitMargin",
                "icon"            = COALESCE(EXCLUDED."icon", "WorkerAgent"."icon"),
                "metadata"        = COALESCE(EXCLUDED."metadata", "WorkerAgent"."metadata"),
                "apiEndpoint"     = COALESCE(EXCLUDED."apiEndpoint", "WorkerAgent"."apiEndpoint"),
                "source"          = EXCLUDED."source",
                "updatedAt"       = EXCLUDED."updatedAt"
            RETURNING *
            """,
            worker_id,                          # $1
            name,                               # $2
            description,                        # $3
            tags or [],                         # $4
            version,                            # $5
            wallet_address,                     # $6
            capabilities or [],                 # $7
            status,                             # $8
            now,                                # $9  lastHeartbeat
            now,                                # $10 connectedAt
            max_concurrent,                     # $11
            bid_price_ratio,                    # $12
            bid_eta_seconds,                    # $13
            min_profit_margin,                  # $14
            icon,                               # $15
            _prepare_jsonb(metadata),           # $16
            api_endpoint,                       # $17
            source,                             # $18
            now,                                # $19 createdAt
            now,                                # $20 updatedAt
        )
        return _row_to_dict(row) or {}

    async def update_worker_status(self, worker_id: str, status: str) -> dict | None:
        """Update a worker agent's status."""
        now = _now()
        row = await self._pool.fetchrow(
            """
            UPDATE "WorkerAgent"
            SET "status" = $2, "updatedAt" = $3
            WHERE "workerId" = $1
            RETURNING *
            """,
            worker_id, status, now,
        )
        return _row_to_dict(row)

    async def touch_worker_heartbeat(self, worker_id: str) -> None:
        """Update lastHeartbeat timestamp."""
        now = _now()
        await self._pool.execute(
            """
            UPDATE "WorkerAgent"
            SET "lastHeartbeat" = $2, "updatedAt" = $3
            WHERE "workerId" = $1
            """,
            worker_id, now, now,
        )

    async def increment_worker_job_stats(
        self, worker_id: str, success: bool, earnings_usdc: float = 0
    ) -> None:
        """Increment job counters for a worker agent."""
        now = _now()
        if success:
            await self._pool.execute(
                """
                UPDATE "WorkerAgent"
                SET "totalJobs" = "totalJobs" + 1,
                    "successfulJobs" = "successfulJobs" + 1,
                    "totalEarningsUsdc" = "totalEarningsUsdc" + $2,
                    "updatedAt" = $3
                WHERE "workerId" = $1
                """,
                worker_id, earnings_usdc, now,
            )
        else:
            await self._pool.execute(
                """
                UPDATE "WorkerAgent"
                SET "totalJobs" = "totalJobs" + 1,
                    "failedJobs" = "failedJobs" + 1,
                    "updatedAt" = $2
                WHERE "workerId" = $1
                """,
                worker_id, now,
            )

    async def get_worker_agent(self, worker_id: str) -> dict | None:
        """Get a single worker agent by workerId."""
        row = await self._pool.fetchrow(
            'SELECT * FROM "WorkerAgent" WHERE "workerId" = $1',
            worker_id,
        )
        return _row_to_dict(row)

    async def list_worker_agents(
        self, status: str | None = None, source: str | None = None, limit: int = 100
    ) -> list[dict]:
        """List worker agents with optional status/source filters."""
        conditions = []
        values: list[Any] = []
        idx = 1

        if status:
            conditions.append(f'"status" = ${idx}')
            values.append(status)
            idx += 1
        if source:
            conditions.append(f'"source" = ${idx}')
            values.append(source)
            idx += 1

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        values.append(limit)

        rows = await self._pool.fetch(
            f'SELECT * FROM "WorkerAgent"{where} ORDER BY "createdAt" ASC LIMIT ${idx}',
            *values,
        )
        return [_row_to_dict(r) for r in rows]
