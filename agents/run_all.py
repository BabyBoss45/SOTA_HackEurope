"""
SOTA Agent Fleet — Single-process launcher for all 7 marketplace agents.

Boots every agent, connects each to the Marketplace Hub via WebSocket,
and exposes a single /health endpoint for Railway health checks.

Usage:
    python agents/run_all.py

Requires:
    SOTA_HUB_URL   — WebSocket URL of the Marketplace Hub
    ANTHROPIC_API_KEY — Claude API key for all agents
    See .env.example for the full list.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the parent of 'agents/' is on sys.path so `from agents.src.*` resolves
_agents_dir = Path(__file__).resolve().parent
if str(_agents_dir.parent) not in sys.path:
    sys.path.insert(0, str(_agents_dir.parent))

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Env ──────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent
load_dotenv(_here.parent / ".env")   # project root
load_dotenv(_here / ".env")          # agents/.env fallback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("sota.fleet")

# ── Agent registry ───────────────────────────────────────────
# Each entry: (display_name, create_function_import_path, needs_start)
# needs_start=True for agents whose lifespan calls agent.start() (e.g. caller)
AGENTS = [
    ("Caller",             "agents.src.caller.agent",             "create_caller_agent",             True),
    ("Gift Suggestion",    "agents.src.gift_suggestion.agent",    "create_gift_suggestion_agent",    False),
    ("Hackathon",          "agents.src.hackathon.agent",          "create_hackathon_agent",          False),
    ("Refund Claim",       "agents.src.refund_claim.agent",       "create_refund_claim_agent",       False),
    ("Restaurant Booker",  "agents.src.restaurant_booker.agent",  "create_restaurant_booker_agent",  False),
    ("Smart Shopper",      "agents.src.smart_shopper.agent",      "create_smart_shopper_agent",      False),
    ("Trip Planner",       "agents.src.trip_planner.agent",       "create_trip_planner_agent",       False),
]


# ── State ────────────────────────────────────────────────────
live_agents: list = []       # initialized agent instances
hub_tasks: list = []         # background hub connector tasks
connectors: list = []        # HubConnector instances (for shutdown)


PRODUCT_NAMES: dict[str, str] = {
    "hackathon": "Hackathon Registration Agent",
    "caller": "Call Verification Agent",
    "gift_suggestion": "Gift Suggestion Agent",
    "refund_claim": "Refund Claim Agent",
    "restaurant_booker": "Restaurant Booking Agent",
    "smart_shopper": "Smart Shopping Agent",
    "trip_planner": "Trip Planning Agent",
}


def _ensure_paid_products() -> None:
    """Ensure all 7 agent products exist in Paid.ai (idempotent)."""
    try:
        import paid
    except ImportError:
        logger.debug("paid-python not installed — skipping product registration")
        return

    api_key = os.getenv("SOTA_PAID_API_KEY") or os.getenv("PAID_API_KEY")
    if not api_key:
        logger.debug("No Paid.ai API key — skipping product registration")
        return

    try:
        client = paid.Paid(api_key=api_key)

        # Fetch existing products
        existing = client.products.list()
        existing_ids: set[str] = set()
        for prod in existing:
            ext_id = getattr(prod, "external_id", None)
            if ext_id:
                existing_ids.add(ext_id)

        # Migrate legacy "hackathon-agent" product to "hackathon"
        if "hackathon-agent" in existing_ids and "hackathon" not in existing_ids:
            try:
                client.products.update_product_by_external_id(
                    external_id="hackathon-agent",
                    external_id_update="hackathon",
                    name="Hackathon Registration Agent",
                )
                existing_ids.discard("hackathon-agent")
                existing_ids.add("hackathon")
                logger.info("  Migrated product 'hackathon-agent' → 'hackathon'")
            except Exception as e:
                logger.warning("  Failed to migrate hackathon-agent product: %s", e)

        # Ensure each agent type has a product
        for agent_type, display_name in PRODUCT_NAMES.items():
            if agent_type in existing_ids:
                logger.debug("  Product '%s' already exists", agent_type)
                continue
            try:
                client.products.create_product(
                    name=display_name,
                    external_id=agent_type,
                )
                logger.info("  Created Paid.ai product: %s (%s)", display_name, agent_type)
            except Exception as e:
                # 409 / duplicate is fine — race condition or already exists
                logger.debug("  Product create for '%s' skipped: %s", agent_type, e)

        logger.info("Paid.ai products ensured: %d agent types", len(PRODUCT_NAMES))
    except Exception as e:
        logger.warning("Paid.ai product registration failed: %s", e)


async def boot_agents():
    """Initialize all agents and connect each to the Hub."""
    from agents.src.shared.hub_connector import HubConnector

    # Initialize Paid.ai cost tracking (auto-instruments all LLM libraries)
    try:
        from sota_sdk.cost import initialize_cost_tracking
        initialize_cost_tracking()
        logger.info("Paid.ai cost tracking initialized")
    except Exception as e:
        logger.warning("Paid.ai init skipped: %s", e)

    # Ensure all 7 agent products exist in Paid.ai
    _ensure_paid_products()

    hub_url = os.getenv("SOTA_HUB_URL", "")
    if not hub_url:
        logger.error("SOTA_HUB_URL is not set — agents cannot connect to the Hub")
        return

    logger.info("Hub URL: %s", hub_url)
    logger.info("Booting %d agents...", len(AGENTS))

    for display_name, module_path, factory_name, needs_start in AGENTS:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            factory = getattr(mod, factory_name)
            agent = await factory()

            if needs_start:
                await agent.start()

            # Connect to Hub
            connector = HubConnector(agent, hub_url=hub_url)
            task = asyncio.create_task(connector.run())

            live_agents.append(agent)
            connectors.append(connector)
            hub_tasks.append(task)

            logger.info("  [OK] %s", display_name)

        except Exception:
            logger.exception("  [FAIL] %s — skipping", display_name)

    logger.info(
        "Fleet ready: %d/%d agents online",
        len(live_agents), len(AGENTS),
    )


async def shutdown_agents():
    """Graceful shutdown."""
    logger.info("Shutting down fleet...")
    for c in connectors:
        c.stop()
    for t in hub_tasks:
        t.cancel()
    if hub_tasks:
        await asyncio.gather(*hub_tasks, return_exceptions=True)
    for a in live_agents:
        try:
            a.stop()
        except Exception:
            pass
    logger.info("All agents stopped")


# ── FastAPI (health only) ────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await boot_agents()
    yield
    await shutdown_agents()


app = FastAPI(title="SOTA Agent Fleet", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/")
async def health():
    from agents.src.shared.hub_connector import HubConnector
    connected = sum(1 for c in connectors if c._ws is not None)
    return {
        "status": "ok",
        "agents_loaded": len(live_agents),
        "agents_total": len(AGENTS),
        "hub_connected": connected,
        "agents": [
            {
                "name": getattr(a, "agent_name", getattr(a, "agent_type", "unknown")),
                "type": getattr(a, "agent_type", "unknown"),
            }
            for a in live_agents
        ],
    }


@app.get("/agents")
async def list_agents():
    return {
        "total": len(live_agents),
        "agents": [
            {
                "name": getattr(a, "agent_name", getattr(a, "agent_type", "unknown")),
                "type": getattr(a, "agent_type", "unknown"),
                "status": "online" if getattr(a, "_running", True) else "idle",
                "active_jobs": len(getattr(a, "active_jobs", {})),
            }
            for a in live_agents
        ],
    }


# ── Entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "3001"))
    logger.info("Starting SOTA Agent Fleet on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
