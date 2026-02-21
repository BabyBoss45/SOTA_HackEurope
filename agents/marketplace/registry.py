"""
Agent Registry — In-memory registry of connected WebSocket agents.

Tracks each agent's name, tags, wallet_address, and live WebSocket connection.
Thread-safe for asyncio (single event loop).

Now also persists agent state to the WorkerAgent PostgreSQL table when a
Database instance is wired via ``set_db()``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any

from fastapi import WebSocket

from .models import AgentInfo

logger = logging.getLogger(__name__)

# Throttle DB heartbeat writes to at most once per 30 seconds per agent
_HEARTBEAT_DB_INTERVAL = 30.0


@dataclass
class ConnectedAgent:
    """A live agent connection in the registry."""
    agent_id: str                   # unique per connection (assigned by hub)
    name: str
    tags: List[str]
    wallet_address: str
    version: str
    capabilities: List[str]
    ws: WebSocket
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    _last_db_heartbeat: float = field(default_factory=time.time, repr=False)


class AgentRegistry:
    """
    In-memory registry of connected agents.

    Agents are added when they send a ``register`` message over WebSocket
    and removed when the connection drops.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, ConnectedAgent] = {}   # agent_id -> ConnectedAgent
        self._counter: int = 0
        self._db: Any = None  # Optional Database instance

    def set_db(self, db: Any) -> None:
        """Wire a Database instance for WorkerAgent persistence."""
        self._db = db

    # ── Registration ──────────────────────────────────────────

    async def register(self, info: AgentInfo, ws: WebSocket) -> ConnectedAgent:
        """Register a new agent connection and return its record."""
        self._counter += 1
        agent_id = f"{info.name}_{self._counter}"

        agent = ConnectedAgent(
            agent_id=agent_id,
            name=info.name,
            tags=[t.lower() for t in info.tags],
            wallet_address=info.wallet_address,
            version=info.version,
            capabilities=info.capabilities,
            ws=ws,
        )
        self._agents[agent_id] = agent
        logger.info(
            "Agent registered: id=%s  name=%s  tags=%s  wallet=%s",
            agent_id, info.name, agent.tags,
            (info.wallet_address[:10] + "...") if info.wallet_address else "(none)",
        )

        # Persist to WorkerAgent table
        if self._db:
            try:
                await self._db.upsert_worker_agent(
                    worker_id=agent_id,
                    name=info.name,
                    tags=agent.tags,
                    version=info.version,
                    wallet_address=info.wallet_address,
                    capabilities=info.capabilities,
                    status="online",
                    source="sdk",
                )
            except Exception as e:
                logger.warning("Failed to persist SDK agent registration: %s", e)

        return agent

    async def unregister(self, agent_id: str) -> None:
        """Remove an agent from the registry (on disconnect)."""
        removed = self._agents.pop(agent_id, None)
        if removed:
            logger.info("Agent unregistered: id=%s  name=%s", agent_id, removed.name)

            # Mark offline in DB
            if self._db:
                try:
                    await self._db.update_worker_status(agent_id, "offline")
                except Exception as e:
                    logger.warning("Failed to mark agent offline in DB: %s", e)

    # ── Queries ───────────────────────────────────────────────

    def get(self, agent_id: str) -> Optional[ConnectedAgent]:
        return self._agents.get(agent_id)

    def find_by_tags(self, job_tags: List[str]) -> List[ConnectedAgent]:
        """Return agents whose tags overlap with the given job tags."""
        job_tag_set: Set[str] = {t.lower() for t in job_tags}
        matching: List[ConnectedAgent] = []
        for agent in self._agents.values():
            agent_tag_set = set(agent.tags)
            if job_tag_set & agent_tag_set:
                matching.append(agent)
        return matching

    def all_agents(self) -> List[ConnectedAgent]:
        return list(self._agents.values())

    @property
    def count(self) -> int:
        return len(self._agents)

    # ── Heartbeat ─────────────────────────────────────────────

    async def touch_heartbeat(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            now = time.time()
            agent.last_heartbeat = now

            # Throttled DB write (every 30s)
            if self._db and (now - agent._last_db_heartbeat) >= _HEARTBEAT_DB_INTERVAL:
                agent._last_db_heartbeat = now
                try:
                    await self._db.touch_worker_heartbeat(agent_id)
                except Exception as e:
                    logger.warning("Failed to persist heartbeat for %s: %s", agent_id, e)
