"""
Mem0 Preferences Client — Persistent user memory for preferences and history.

Graceful degradation: if ``MEM0_API_KEY`` is not set, ``from_env()``
returns ``None`` and callers fall back to in-memory session stores.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Mem0Preferences:
    """Async-friendly wrapper around the Mem0 ``MemoryClient``."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from mem0 import MemoryClient  # type: ignore
            self._client = MemoryClient(api_key=self._api_key)
        return self._client

    @classmethod
    def from_env(cls) -> Optional["Mem0Preferences"]:
        key = os.getenv("MEM0_API_KEY", "").strip()
        if not key:
            logger.info("MEM0_API_KEY not set — Mem0 preferences disabled")
            return None
        return cls(api_key=key)

    async def remember(
        self,
        user_id: str,
        content: str,
        *,
        category: str = "general",
        metadata: dict | None = None,
    ) -> bool:
        """Store a memory for a user. Returns True on success."""
        try:
            client = self._get_client()
            meta = {"category": category}
            if metadata:
                meta.update(metadata)

            client.add(
                messages=[
                    {"role": "user", "content": content},
                ],
                user_id=user_id,
                metadata=meta,
            )
            logger.debug("Mem0 remember: user=%s category=%s", user_id, category)
            return True
        except Exception as e:
            logger.warning("Mem0 remember failed: %s", e)
            return False

    async def recall(
        self,
        user_id: str,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search user memories. Returns list of {memory, score, metadata}."""
        try:
            client = self._get_client()
            filters: dict[str, Any] = {"user_id": user_id}
            if category:
                filters["AND"] = [{"user_id": user_id}]

            results = client.search(query, user_id=user_id, limit=limit)

            memories = []
            for r in results:
                entry: dict[str, Any] = {"memory": r.get("memory", "")}
                if r.get("score") is not None:
                    entry["score"] = r["score"]
                if r.get("metadata"):
                    entry["metadata"] = r["metadata"]
                memories.append(entry)
            return memories

        except Exception as e:
            logger.warning("Mem0 recall failed: %s", e)
            return []

    async def get_all(self, user_id: str, *, limit: int = 20) -> list[str]:
        """Return all memories for a user (no search query)."""
        try:
            client = self._get_client()
            results = client.get_all(user_id=user_id)
            return [r.get("memory", "") for r in results[:limit] if r.get("memory")]
        except Exception as e:
            logger.warning("Mem0 get_all failed: %s", e)
            return []
