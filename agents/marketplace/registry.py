"""
Agent Registry — In-memory registry of connected WebSocket agents.

Tracks each agent's name, tags, wallet_address, and live WebSocket connection.
Thread-safe for asyncio (single event loop).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

from .models import AgentInfo

logger = logging.getLogger(__name__)


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


class AgentRegistry:
    """
    In-memory registry of connected agents.

    Agents are added when they send a ``register`` message over WebSocket
    and removed when the connection drops.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, ConnectedAgent] = {}   # agent_id -> ConnectedAgent
        self._counter: int = 0

    # ── Registration ──────────────────────────────────────────

    def register(self, info: AgentInfo, ws: WebSocket) -> ConnectedAgent:
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
        return agent

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the registry (on disconnect)."""
        removed = self._agents.pop(agent_id, None)
        if removed:
            logger.info("Agent unregistered: id=%s  name=%s", agent_id, removed.name)

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

    def touch_heartbeat(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.last_heartbeat = time.time()
