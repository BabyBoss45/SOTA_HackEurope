"""
FastAPI server embedded in every SOTAAgent.

Provides:
- GET /health    -- liveness probe
- GET /status    -- agent status (name, version, active jobs, etc.)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from .agent import SOTAAgent

logger = logging.getLogger(__name__)


def _mask_address(addr: str | None) -> str | None:
    """Show only the first 6 and last 4 characters of a wallet address."""
    if not addr or len(addr) < 12:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def create_app(agent: "SOTAAgent") -> FastAPI:
    """Build a FastAPI app wired to the given agent instance."""
    app = FastAPI(title=f"SOTA Agent: {agent.name}", version=agent.version)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/status")
    async def status():
        return {
            "name": agent.name,
            "description": agent.description,
            "version": agent.version,
            "tags": agent.tags,
            "wallet_address": _mask_address(
                agent._wallet.address if agent._wallet else None
            ),
            "active_jobs": len(agent._active_jobs),
            "connected": (
                agent._ws_client.connected if agent._ws_client else False
            ),
        }

    # Let subclasses add custom routes
    if hasattr(agent, 'register_routes'):
        agent.register_routes(app)

    return app
