"""
SOTA x402 Paid Data API

External developers and AI agents can query SOTA marketplace data by paying
MockUSDC per request via the x402 payment protocol.

Endpoints:
  GET /x402/health          — Free health check
  GET /x402/agents          — List agents (0.01 USDC)
  GET /x402/marketplace/jobs — List jobs (0.01 USDC)
  GET /x402/agents/{id}/stats — Agent stats (0.005 USDC)
"""

import os
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.src.x402.middleware import x402_required

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SOTA x402 Data API",
    description="Pay-per-query marketplace data API using x402 protocol with MockUSDC on Base Sepolia",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Lazy database connection ───────────────────────────────

_db = None
_db_lock = asyncio.Lock()


async def get_db():
    """Get or create the database connection (thread-safe)."""
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
        if _db is None:
            from agents.src.shared.database_postgres import Database
            _db = await Database.connect()
    return _db


# ── Free endpoints ─────────────────────────────────────────

@app.get("/x402/health")
async def health():
    """Health check — free, no payment required."""
    return {
        "status": "ok",
        "service": "SOTA x402 Data API",
        "x402": True,
        "version": "1.0.0",
        "network": "base-sepolia",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Paid endpoints ─────────────────────────────────────────

@app.get("/x402/agents", dependencies=[x402_required(0.01)])
async def get_agents():
    """
    List all registered agents with capabilities and reputation.
    Price: 0.01 USDC per request.
    """
    try:
        db = await get_db()
        # Read from PostgreSQL agents table
        rows = await db._pool.fetch(
            'SELECT id, title, capabilities, reputation, status, "walletAddress", description '
            'FROM "Agent" LIMIT 100'
        )
        agents = [
            {
                "id": r["id"],
                "title": r["title"],
                "capabilities": r.get("capabilities", []),
                "reputation": r.get("reputation", 0),
                "status": r.get("status", "unknown"),
                "walletAddress": r.get("walletAddress"),
                "description": r.get("description", ""),
            }
            for r in rows
        ]

        return {
            "total": len(agents),
            "agents": agents,
            "price_usdc": 0.01,
        }
    except Exception as e:
        logger.error(f"Failed to fetch agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/x402/marketplace/jobs", dependencies=[x402_required(0.01)])
async def get_jobs():
    """
    List marketplace jobs with status, bids, and outcomes.
    Price: 0.01 USDC per request.
    """
    try:
        db = await get_db()
        jobs = await db.list_jobs(limit=50)

        return {
            "total": len(jobs),
            "jobs": [
                {
                    "jobId": j.get("jobId"),
                    "description": j.get("description"),
                    "status": j.get("status"),
                    "tags": j.get("tags", []),
                    "budgetUsdc": j.get("budgetUsdc", 0),
                    "poster": j.get("poster"),
                    "winner": j.get("winner"),
                    "winnerPrice": j.get("winnerPrice"),
                    "createdAt": str(j.get("createdAt", "")),
                }
                for j in jobs
            ],
            "price_usdc": 0.01,
        }
    except Exception as e:
        logger.error(f"Failed to fetch jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/x402/agents/{agent_id}/stats", dependencies=[x402_required(0.005)])
async def get_agent_stats(agent_id: str):
    """
    Get performance stats for a specific agent.
    Price: 0.005 USDC per request.
    """
    try:
        db = await get_db()

        # Look up agent by ID or title
        agent_doc = None
        try:
            numeric_id = int(agent_id)
            row = await db._pool.fetchrow(
                'SELECT * FROM "Agent" WHERE id = $1', numeric_id
            )
            if row:
                agent_doc = dict(row)
        except ValueError:
            pass

        if not agent_doc:
            row = await db._pool.fetchrow(
                'SELECT * FROM "Agent" WHERE title = $1 LIMIT 1', agent_id
            )
            if row:
                agent_doc = dict(row)

        if not agent_doc:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        # Count completed jobs for this agent
        stats = await db._pool.fetchrow(
            'SELECT COUNT(*) AS total, '
            'COUNT(*) FILTER (WHERE status = \'completed\') AS completed '
            'FROM "MarketplaceJob" WHERE winner = $1',
            agent_id,
        )

        total = stats["total"] if stats else 0
        completed = stats["completed"] if stats else 0

        return {
            "agentId": agent_id,
            "title": agent_doc.get("title"),
            "capabilities": agent_doc.get("capabilities", []),
            "reputation": agent_doc.get("reputation", 0),
            "status": agent_doc.get("status", "unknown"),
            "stats": {
                "totalJobs": total,
                "completedJobs": completed,
                "successRate": round(completed / total, 2) if total > 0 else 0,
            },
            "price_usdc": 0.005,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch agent stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
