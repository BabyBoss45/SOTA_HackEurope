"""
SOTA Butler API — FastAPI Bridge

Exposes HTTP endpoints for the ElevenLabs voice agent and web frontend.
Internally delegates to the Anthropic Claude-backed Butler Agent and in-memory marketplace.

Endpoints:
  POST /api/v1/chat      — Chat with Claude-backed Butler Agent
  POST /api/v1/query     — Alias for /api/v1/chat (backward compat)
  POST /api/v1/create    — Create + fund a job on-chain
  POST /api/v1/status    — Check job status + delivery confirmation
  POST /api/v1/release   — Release payment (delivery-gated)
  GET  /api/v1/marketplace/jobs     — List marketplace jobs
  GET  /api/v1/marketplace/bids/{id} — Get bids for a job
  GET  /api/v1/marketplace/workers  — List registered workers
"""

import os
import sys
import time
import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.marketplace.hub import app as marketplace_hub_app, registry as hub_registry

import hashlib

from agents.src.shared.chain_config import get_private_key, get_cluster, PROGRAM_ID, USDC_MINT
from agents.src.shared.chain_contracts import (
    get_contracts,
    Contracts,
    create_job,
    assign_provider,
    fund_job,
    mark_completed,
    release_payment,
    refund_escrow,
    confirm_delivery,
    is_delivery_confirmed,
    get_job,
    get_escrow_deposit,
)
from agents.src.shared.butler_comms import ButlerDataExchange
try:
    from agents.src.shared.database import Database
except ImportError:
    Database = None  # type: ignore

# Anthropic Claude Butler Agent + JobBoard marketplace
from agents.src.butler.agent import ButlerAgent, create_butler_agent
from agents.src.shared.job_board import JobBoard, JobStatus

# Worker agents — created in-process for JobBoard bidding
from agents.src.hackathon.agent import HackathonAgent, create_hackathon_agent
from agents.src.caller.agent import CallerAgent, create_caller_agent
from agents.src.gift_suggestion.agent import create_gift_suggestion_agent
from agents.src.restaurant_booker.agent import create_restaurant_booker_agent
from agents.src.refund_claim.agent import create_refund_claim_agent
from agents.src.smart_shopper.agent import create_smart_shopper_agent
from agents.src.trip_planner.agent import create_trip_planner_agent
from agents.src.fun_activity.agent import create_fun_activity_agent
from agents.src.competitor_fun.agent import create_competitor_fun_agent

# Load .env from project root (single source of truth)
_here = Path(__file__).resolve().parent
load_dotenv(_here.parent / ".env")
load_dotenv(_here / ".env")  # fallback: agents/.env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")

# ─── Globals ──────────────────────────────────────────────────

contracts: Optional[Contracts] = None
butler_agent: Optional[ButlerAgent] = None
job_board: Optional[JobBoard] = None
hackathon_agent: Optional[HackathonAgent] = None
caller_agent: Optional[CallerAgent] = None
db: Optional[Any] = None  # Database connection
task_memory: Optional[Any] = None  # TaskPatternMemory instance
_db_pool: Optional[Any] = None  # asyncpg pool for ClawBot token/reputation ops


# ─── Request / Response Models ────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: Optional[int] = None


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    model: str = ""


class CreateJobRequest(BaseModel):
    description: str
    budget_usdc: float
    deadline_seconds: int = 86400
    provider_address: Optional[str] = None
    metadata_uri: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: int
    tx_hash: str
    budget_usdc: float
    usdc_locked: float
    provider: str
    message: str


class MarketplacePostRequest(BaseModel):
    """Accept the raw job JSON from ElevenLabs and post to marketplace."""
    model_config = {"extra": "allow"}

    task: str
    location: Optional[str] = None
    date_range: Optional[str] = None
    online_or_in_person: Optional[str] = None
    theme_technology_focus: Optional[Any] = None
    # Booking fields
    city: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    guests: Optional[int] = None
    cuisine: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    room_type: Optional[str] = None
    budget: Optional[str] = None
    budget_usd: float = 1.0
    deadline_hours: int = 24
    wallet_address: Optional[str] = None


class JobStatusRequest(BaseModel):
    job_id: int


class JobStatusResponse(BaseModel):
    job_id: int
    status: str
    poster: str
    provider: str
    budget_usdc: float
    delivery_confirmed: bool
    escrow_funded: bool
    escrow_released: bool
    message: str


class ReleaseRequest(BaseModel):
    job_id: int


# ─── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global contracts, butler_agent, job_board, hackathon_agent, caller_agent, db, task_memory, _db_pool
    cluster = get_cluster()
    print(f"Starting SOTA Butler API...")
    print(f"Cluster: {cluster.rpc_url} ({cluster.cluster_name})")

    # ── Connect to PostgreSQL ────────────────────────────────
    if Database is not None:
        try:
            db = await Database.connect()
            print("Connected to PostgreSQL")
            # Wire DB to hub registry for SDK agent persistence
            hub_registry.set_db(db)
        except Exception as e:
            print(f"Database unavailable — running without persistence: {e}")
    else:
        print("Database module not available — running without persistence")

    # ── asyncpg pool for ClawBot operations ──────────────────
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        try:
            import asyncpg
            _db_pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
            print("asyncpg pool created for ClawBot operations")
        except Exception as e:
            print(f"asyncpg pool creation failed (non-critical): {e}")

    # ── incident.io client (graceful no-op if unconfigured) ──
    _incident_io = None
    try:
        from agents.src.shared.incident_io import IncidentIOClient
        _incident_io = IncidentIOClient.from_env()
        if _incident_io:
            print("incident.io client configured")
            try:
                from agents.src.shared.incident_tools import set_incident_io_client
                set_incident_io_client(_incident_io)
            except Exception:
                pass
        else:
            print("incident.io not configured (INCIDENT_IO_API_KEY not set)")
    except Exception as e:
        print(f"incident.io init skipped: {e}")

    # ── Task Pattern Memory ────────────────────────────────
    try:
        from agents.src.shared.task_memory import TaskPatternMemory
        task_memory = TaskPatternMemory(db=db, incident_io_client=_incident_io)
        qdrant_ok = "yes" if task_memory.qdrant else "no"
        print(f"TaskPatternMemory initialized (qdrant={qdrant_ok}, incident_io={'yes' if _incident_io else 'no'})")
        if task_memory.qdrant:
            try:
                cols = task_memory.qdrant.get_collections().collections
                for c in cols:
                    info = task_memory.qdrant.get_collection(c.name)
                    print(f"  Qdrant collection '{c.name}': {info.points_count} points")
            except Exception:
                pass
    except Exception as e:
        print(f"TaskPatternMemory init failed (non-critical): {e}")

    pk = get_private_key("butler")
    if not pk:
        print("PRIVATE_KEY not set. Read-only mode.")
    else:
        # ── Contracts ─────────────────────────────────────────────
        try:
            contracts = get_contracts(pk)
            print(f"Connected to Solana ({cluster.cluster_name})")
            print(f"  Program ID: {contracts.program_id}")
            print(f"  USDC Mint:  {USDC_MINT}")
            print(f"  Signer:     {contracts.keypair.pubkey() if contracts.keypair else 'read-only'}")
        except Exception as e:
            print(f"Failed to connect: {e}")

    # ── Anthropic Claude Butler Agent ────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            butler_agent = create_butler_agent(
                private_key=pk or "0x" + "0" * 64,
                anthropic_api_key=anthropic_key,
            )
            print(f"Butler Agent initialized (model={butler_agent.model})")
        except Exception as e:
            print(f"Butler Agent init failed: {e}")
    else:
        print("ANTHROPIC_API_KEY not set — Butler Agent disabled")

    # ── JobBoard Marketplace ─────────────────────────────────
    job_board = JobBoard.instance()
    print(f"JobBoard marketplace ready (in-memory)")

    # ── ClawBot External Agent Inviter ────────────────────────
    if database_url and _db_pool:
        try:
            from agents.src.shared.hmac_signer import HMACSigner
            from agents.src.shared.external_agent_inviter import ExternalAgentInviter
            _signer = HMACSigner()
            _inviter = ExternalAgentInviter(pool=_db_pool, signer=_signer)
            job_board.set_external_inviter(_inviter)
            job_board.set_db_pool(_db_pool)
            print("ClawBot ExternalAgentInviter attached to JobBoard")
        except Exception as e:
            print(f"ExternalAgentInviter init failed (non-critical): {e}")

    # ── Stale execution token cleanup loop ────────────────────
    if _db_pool and contracts:
        asyncio.create_task(_expire_stale_tokens_loop())

    # ── Register Worker Agents ────────────────────────────────
    try:
        hackathon_agent = await create_hackathon_agent(db=db)
        if task_memory:
            hackathon_agent.task_memory = task_memory
        print(f"HackathonAgent registered on JobBoard")
    except Exception as e:
        print(f"HackathonAgent init failed (non-critical): {e}")

    try:
        caller_agent = await create_caller_agent(db=db)
        if task_memory:
            caller_agent.task_memory = task_memory
        print(f"CallerAgent registered on JobBoard")
    except Exception as e:
        print(f"CallerAgent init failed (non-critical): {e}")

    try:
        gift_agent = await create_gift_suggestion_agent(db=db)
        print(f"GiftSuggestionAgent registered on JobBoard")
    except Exception as e:
        print(f"GiftSuggestionAgent init failed (non-critical): {e}")

    try:
        restaurant_agent = await create_restaurant_booker_agent(db=db)
        print(f"RestaurantBookerAgent registered on JobBoard")
    except Exception as e:
        print(f"RestaurantBookerAgent init failed (non-critical): {e}")

    try:
        refund_agent = await create_refund_claim_agent(db=db)
        print(f"RefundClaimAgent registered on JobBoard")
    except Exception as e:
        print(f"RefundClaimAgent init failed (non-critical): {e}")

    try:
        shopper_agent = await create_smart_shopper_agent(db=db)
        print(f"SmartShopperAgent registered on JobBoard")
    except Exception as e:
        print(f"SmartShopperAgent init failed (non-critical): {e}")

    try:
        trip_agent = await create_trip_planner_agent(db=db)
        print(f"TripPlannerAgent registered on JobBoard")
    except Exception as e:
        print(f"TripPlannerAgent init failed (non-critical): {e}")

    try:
        fun_activity_agent = await create_fun_activity_agent(db=db)
        if task_memory:
            fun_activity_agent.task_memory = task_memory
        print(f"FunActivityAgent registered on JobBoard")
    except Exception as e:
        print(f"FunActivityAgent init failed (non-critical): {e}")

    try:
        competitor_fun_agent = await create_competitor_fun_agent(db=db)
        if task_memory:
            competitor_fun_agent.task_memory = task_memory
        print(f"CompetitorFunAgent (GPT-4o) registered on JobBoard")
    except Exception as e:
        print(f"CompetitorFunAgent init failed (non-critical): {e}")

    # Log registered workers
    workers = job_board.workers
    print(f"{len(workers)} worker(s) registered: {list(workers.keys())}")

    yield


app = FastAPI(title="SOTA Butler API", lifespan=lifespan)
app.mount("/hub", marketplace_hub_app)
logger.info("Marketplace Hub mounted at /hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "SOTA Butler API running", "version": "3.0"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "butler-api"}


# ─── Butler Agent Chat (Anthropic Claude) ────────────────────

@app.post("/api/v1/chat")
async def chat_with_butler(req: ChatRequest):
    """
    Send a message to the Anthropic Claude-backed Butler Agent.
    """
    if not butler_agent:
        raise HTTPException(503, "Butler Agent not initialized. Check ANTHROPIC_API_KEY.")
    try:
        result = await butler_agent.chat(
            message=req.query,
            user_id=req.user_id or "web_user",
        )
        return {
            "response": result["response"],
            "session_id": req.session_id,
            "model": butler_agent.model if butler_agent else "",
            "job_posted": result.get("job_posted"),
        }
    except Exception as e:
        logger.error("Butler chat error: %s", e)
        raise HTTPException(500, f"Butler chat failed: {e}")


@app.post("/api/v1/query")
async def query_butler_compat(req: ChatRequest):
    """Backward-compatible alias for chat."""
    result = await chat_with_butler(req)
    return {
        "response": result["response"],
        "message": result["response"],
        "session_id": result.get("session_id"),
        "job_posted": result.get("job_posted"),
    }


# ─── Marketplace Endpoints ───────────────────────────────────

@app.get("/api/v1/marketplace/jobs")
async def list_marketplace_jobs(status: Optional[str] = None):
    """List all jobs on the in-memory marketplace."""
    board = JobBoard.instance()
    if status == "open":
        jobs = board.list_open_jobs()
    else:
        jobs = board.list_all_jobs()

    return {
        "total": len(jobs),
        "jobs": [
            {
                "job_id": j.job_id,
                "description": j.description,
                "tags": j.tags,
                "budget_usdc": j.budget_usdc,
                "status": j.status.value,
                "poster": j.poster,
                "posted_at": j.posted_at,
                "deadline_ts": j.deadline_ts,
                "metadata": j.metadata,
            }
            for j in jobs
        ],
    }


@app.get("/api/v1/marketplace/bids/{job_id}")
async def get_marketplace_bids(job_id: str):
    """Get all bids for a specific marketplace job."""
    board = JobBoard.instance()
    bids = board.get_bids(job_id)
    job = board.get_job(job_id)

    return {
        "job_id": job_id,
        "job_status": job.status.value if job else "not_found",
        "total_bids": len(bids),
        "bids": [
            {
                "bid_id": b.bid_id,
                "bidder_id": b.bidder_id,
                "bidder_address": b.bidder_address,
                "amount_usdc": b.amount_usdc,
                "estimated_seconds": b.estimated_seconds,
                "tags": b.tags,
                "submitted_at": b.submitted_at,
            }
            for b in bids
        ],
    }


@app.get("/api/v1/marketplace/workers")
async def list_marketplace_workers():
    """List all registered worker agents."""
    board = JobBoard.instance()
    workers = board.workers

    return {
        "total": len(workers),
        "workers": [
            {
                "worker_id": w.worker_id,
                "address": w.address,
                "tags": w.tags,
                "max_concurrent": w.max_concurrent,
                "active_jobs": w.active_jobs,
            }
            for w in workers.values()
        ],
    }


# ─── Marketplace Post (from ElevenLabs) ──────────────────────

@app.post("/api/v1/marketplace/post")
async def post_job_from_elevenlabs(req: MarketplacePostRequest):
    """
    Receive a structured job JSON from ElevenLabs voice agent
    and post it to the marketplace.
    """
    from agents.src.butler.tools import PostJobTool

    # Coerce theme_technology_focus: string -> list
    if isinstance(req.theme_technology_focus, str):
        req.theme_technology_focus = [
            t.strip() for t in req.theme_technology_focus.replace("/", ",").split(",") if t.strip()
        ]

    # Build description and parameters from the raw job fields
    task = req.task
    params = req.model_dump(
        exclude={"task", "budget_usd", "deadline_hours", "wallet_address"},
        exclude_none=True,
    )

    # Map task name to a tool type
    task_lower = task.lower().replace(" ", "_")
    TASK_TO_TOOL = {
        "hackathon_discovery": "hackathon_registration",
        "hackathon_registration": "hackathon_registration",
        "hotel_booking": "hotel_booking",
        "restaurant_booking": "restaurant_booking_smart",
        "restaurant_booking_smart": "restaurant_booking_smart",
        "call_verification": "call_verification",
        "gift_suggestion": "gift_suggestion",
        "smart_shopping": "smart_shopping",
        "trip_planning": "trip_planning",
        "refund_claim": "refund_claim",
        "fun_activity": "fun_activity",
        "fun_activity_discovery": "fun_activity",
        "event_discovery": "fun_activity",
        "nightlife": "fun_activity",
        "nightlife_adventure": "fun_activity",
        "adventure": "fun_activity",
        "activity_booking": "fun_activity",
    }
    tool_type = TASK_TO_TOOL.get(task_lower, task_lower)

    # Fallback substring matching
    if tool_type == task_lower and tool_type not in TASK_TO_TOOL.values():
        if "hackathon" in task_lower:
            tool_type = "hackathon_registration"
        elif "hotel" in task_lower:
            tool_type = "hotel_booking"
        elif "fun" in task_lower or "event" in task_lower or "activity" in task_lower:
            tool_type = "fun_activity"
        elif "restaurant" in task_lower or "booking" in task_lower:
            tool_type = "restaurant_booking_smart"
        elif "call" in task_lower or "phone" in task_lower:
            tool_type = "call_verification"
        elif "gift" in task_lower:
            tool_type = "gift_suggestion"
        elif "shop" in task_lower or "product" in task_lower or "buy" in task_lower:
            tool_type = "smart_shopping"
        elif "trip" in task_lower or "travel" in task_lower or "flight" in task_lower:
            tool_type = "trip_planning"
        elif "refund" in task_lower or "claim" in task_lower:
            tool_type = "refund_claim"
        elif "nightlife" in task_lower or "adventure" in task_lower:
            tool_type = "fun_activity"

    description = f"{task}: {', '.join(f'{k}={v}' for k, v in params.items())}"

    logger.info(f"ElevenLabs job received: {tool_type} — {description}")

    try:
        post_tool = PostJobTool()
        result_str = await post_tool.execute(
            description=description,
            tool=tool_type,
            parameters=params,
            budget_usd=req.budget_usd,
            deadline_hours=req.deadline_hours,
        )

        response = {
            "success": True,
            "message": result_str,
            "tool_type": tool_type,
            "description": description,
        }

        try:
            parsed = json.loads(result_str)
            response["job_posted"] = parsed
            if parsed.get("formatted_results"):
                response["formatted_results"] = parsed["formatted_results"]
            if parsed.get("execution_result"):
                response["execution_result"] = parsed["execution_result"]
        except (json.JSONDecodeError, TypeError):
            pass

        return response
    except Exception as e:
        logger.error(f"Marketplace post failed: {e}")
        return {
            "success": False,
            "message": f"Failed to post job: {e}",
            "tool_type": tool_type,
        }


# ─── Job Execution (after escrow funded) ─────────────────────

@app.post("/api/v1/marketplace/execute/{job_id}")
async def execute_job_after_escrow(job_id: str):
    """
    Trigger job execution AFTER escrow has been funded.
    """
    board = JobBoard.instance()
    job = board.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    winning_bid = board.get_winning_bid(job_id)

    if not winning_bid:
        raise HTTPException(400, f"No winning bid for job {job_id}")

    worker = board.workers.get(winning_bid.bidder_id)
    if not worker or not worker.executor:
        raise HTTPException(400, f"Worker {winning_bid.bidder_id} has no executor")

    logger.info(f"Executing job {job_id} with worker {winning_bid.bidder_id}")

    # Persist "in_progress" to database
    if db:
        try:
            await db.update_job_status(job_id, "assigned")
            await db.create_update(job_id, agent=winning_bid.bidder_id, status="in_progress", message="Execution started")
        except Exception as e:
            logger.warning(f"DB in_progress update failed: {e}")

    # Pre-execution: analyze similar past tasks
    pattern_hint = None
    if task_memory and db:
        try:
            pattern_hint = await task_memory.analyze_similar(
                description=job.description or "",
                tags=list(job.tags),
                agent_id=winning_bid.bidder_id,
            )
            if pattern_hint.similar_outcomes:
                logger.info(
                    "🧠 Pattern detected for job %s: confidence=%.2f strategy=%s",
                    job_id, pattern_hint.confidence, pattern_hint.recommended_strategy,
                )
                await db.create_update(
                    job_id, agent=winning_bid.bidder_id,
                    status="adaptation",
                    message=pattern_hint.reasoning,
                    data={
                        "confidence": pattern_hint.confidence,
                        "success_rate": pattern_hint.success_rate,
                        "common_failures": pattern_hint.common_failures,
                        "strategy": pattern_hint.recommended_strategy,
                        "similar_tasks_found": len(pattern_hint.similar_outcomes),
                    },
                )
        except Exception as e:
            logger.debug(f"Pre-exec analysis skipped: {e}")

    _exec_start_ms = time.time() * 1000
    try:
        # Run the executor
        exec_result = await worker.executor(job, winning_bid)

        # Format results for display
        from agents.src.butler.tools import format_hackathon_results, strip_markdown
        worker_type = winning_bid.bidder_id

        if worker_type == "hackathon":
            formatted = strip_markdown(format_hackathon_results(exec_result))
        elif worker_type == "caller" and isinstance(exec_result, dict):
            chat_summary = exec_result.get("chat_summary", "")
            booking = exec_result.get("booking_details", {})
            status = exec_result.get("status", "unknown")
            phone = exec_result.get("phone_number", "")

            parts = []
            if chat_summary:
                parts.append(chat_summary)
            else:
                parts.append(f"Call to {phone} — status: {status}")
            if booking:
                details = []
                if booking.get("type"):
                    details.append(f"Type: {booking['type']}")
                if booking.get("guests"):
                    details.append(f"Guests: {booking['guests']}")
                if booking.get("date"):
                    details.append(f"Date: {booking['date']}")
                if booking.get("time"):
                    details.append(f"Time: {booking['time']}")
                if booking.get("name"):
                    details.append(f"Name: {booking['name']}")
                if details:
                    parts.append("\nBooking details: " + ", ".join(details))
            formatted = "\n".join(parts)
        elif isinstance(exec_result, dict):
            raw_text = exec_result.get("result") or exec_result.get("chat_summary") or ""
            if isinstance(raw_text, str) and raw_text.strip():
                formatted = strip_markdown(raw_text)
            else:
                formatted = strip_markdown(json.dumps(exec_result, indent=2, default=str))
        else:
            formatted = strip_markdown(str(exec_result))

        logger.info(f"Job {job_id} execution completed (worker={worker_type})")

        # Direct search fallback for hackathon
        if worker_type == "hackathon" and "couldn't find" in formatted.lower() and "hackathon" in (job.description or "").lower():
            logger.info(f"Attempting direct search fallback for job {job_id}...")
            try:
                from agents.src.hackathon.tools import SearchHackathonsTool
                import json as _json

                loc = job.metadata.get("parameters", {}).get("location", "")
                if loc:
                    search_tool = SearchHackathonsTool()
                    raw = await search_tool.execute(location=loc)
                    search_data = _json.loads(raw)
                    if search_data.get("success") and search_data.get("hackathons"):
                        exec_result = search_data
                        formatted = format_hackathon_results(search_data)
            except Exception as fallback_err:
                logger.warning(f"Direct search fallback failed: {fallback_err}")

        # Persist "completed" to database
        if db:
            try:
                await db.update_job_status(job_id, "completed")
                await db.create_update(
                    job_id, agent=winning_bid.bidder_id,
                    status="completed", message="Execution complete",
                    data=exec_result if isinstance(exec_result, dict) else {"result": str(exec_result)},
                )
            except Exception as e:
                logger.warning(f"DB completed update failed: {e}")

            # Increment worker agent job stats
            try:
                await db.increment_worker_job_stats(
                    winning_bid.bidder_id,
                    success=True,
                    earnings_usdc=winning_bid.amount_usdc,
                )
            except Exception as e:
                logger.warning(f"Worker stats update failed: {e}")

        # ── On-chain completion: markCompleted → confirm delivery → release payment ──
        on_chain_job_id = job.metadata.get("on_chain_job_id") if job.metadata else None
        release_tx = None
        if on_chain_job_id and contracts:
            try:
                proof_data = json.dumps(exec_result, default=str).encode() if isinstance(exec_result, dict) else str(exec_result).encode()
                proof_hash = hashlib.sha256(proof_data).digest()[:32]

                # 1. Mark completed on-chain
                try:
                    mark_completed(contracts, int(on_chain_job_id), proof_hash)
                    logger.info(f"On-chain markCompleted for job #{on_chain_job_id}")
                except Exception as mc_err:
                    logger.warning(f"markCompleted skipped: {mc_err}")

                # 2. Confirm delivery (owner-only)
                try:
                    confirm_delivery(contracts, int(on_chain_job_id))
                    logger.info(f"Delivery confirmed for job #{on_chain_job_id}")
                except Exception as cd_err:
                    logger.warning(f"confirmDelivery skipped: {cd_err}")

                # 3. Release escrow payment to provider
                try:
                    if is_delivery_confirmed(contracts, int(on_chain_job_id)):
                        release_tx = release_payment(contracts, int(on_chain_job_id))
                        logger.info(f"Payment released for job #{on_chain_job_id} — tx: {release_tx}")
                    else:
                        logger.warning(f"Delivery not confirmed, cannot release payment for job #{on_chain_job_id}")
                except Exception as rel_err:
                    logger.warning(f"releasePayment skipped: {rel_err}")

            except Exception as chain_err:
                logger.error(f"On-chain completion failed for job #{on_chain_job_id}: {chain_err}")

        # Persist successful outcome
        _exec_elapsed = int(time.time() * 1000 - _exec_start_ms)
        if task_memory:
            try:
                from agents.src.shared.base_agent import ActiveJob
                _outcome_job = ActiveJob(
                    job_id=int(job_id) if job_id.isdigit() else 0,
                    bid_id=0, job_type=0,
                    description=job.description or "",
                    budget=int(job.budget_usdc * 1e6),
                    deadline=job.deadline_ts,
                    params=job.metadata or {},
                )
                _result_dict = exec_result if isinstance(exec_result, dict) else {"result": str(exec_result), "success": True}
                if "success" not in _result_dict:
                    _result_dict["success"] = True
                await task_memory.persist_outcome(
                    job=_outcome_job, agent_id=winning_bid.bidder_id,
                    result=_result_dict, elapsed_ms=_exec_elapsed,
                    pattern_hint=pattern_hint,
                )
            except Exception:
                logger.warning("Failed to persist task outcome (success path)", exc_info=True)

        return {
            "success": True,
            "job_id": job_id,
            "execution_result": exec_result,
            "formatted_results": formatted,
            "payment_released": release_tx is not None,
            "release_tx": release_tx,
        }
    except Exception as e:
        logger.error(f"Job {job_id} execution failed: {e}")

        # Persist failed outcome
        _exec_elapsed = int(time.time() * 1000 - _exec_start_ms)
        if task_memory:
            try:
                from agents.src.shared.base_agent import ActiveJob
                _outcome_job = ActiveJob(
                    job_id=int(job_id) if job_id.isdigit() else 0,
                    bid_id=0, job_type=0,
                    description=job.description or "",
                    budget=int(job.budget_usdc * 1e6),
                    deadline=job.deadline_ts,
                    params=job.metadata or {},
                )
                await task_memory.persist_outcome(
                    job=_outcome_job, agent_id=winning_bid.bidder_id,
                    result={"success": False, "error": str(e)},
                    elapsed_ms=_exec_elapsed,
                    pattern_hint=pattern_hint,
                )
            except Exception:
                logger.warning("Failed to persist task outcome (error path)", exc_info=True)

        # Persist error to PostgreSQL
        if db:
            try:
                await db.update_job_status(job_id, "expired")
                await db.create_update(job_id, agent=winning_bid.bidder_id, status="error", message=str(e))
            except Exception:
                pass

            # Increment worker agent job stats (failure)
            try:
                await db.increment_worker_job_stats(winning_bid.bidder_id, success=False)
            except Exception:
                pass

        raise HTTPException(500, f"Job execution failed: {e}")


@app.get("/api/v1/marketplace/execute/{job_id}/stream")
async def execute_job_with_sse(job_id: str):
    """Execute job with Server-Sent Events for real-time progress updates."""
    board = JobBoard.instance()
    job = board.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    bids = board.get_bids(job_id)
    winning_bid = next((b for b in bids if b.bidder_id), None)

    if not winning_bid:
        raise HTTPException(400, f"No winning bid for job {job_id}")

    worker = board.workers.get(winning_bid.bidder_id)
    if not worker or not worker.executor:
        raise HTTPException(400, f"Worker {winning_bid.bidder_id} has no executor")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'started', 'message': f'Starting job with {winning_bid.bidder_id}...'})}\n\n"
            await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'event': 'progress', 'message': 'Searching for results...'})}\n\n"

            exec_result = await worker.executor(job, winning_bid)

            from agents.src.butler.tools import format_hackathon_results
            formatted = format_hackathon_results(exec_result)

            if "couldn't find" in formatted.lower() and "hackathon" in (job.description or "").lower():
                yield f"data: {json.dumps({'event': 'progress', 'message': 'Trying additional sources...'})}\n\n"
                try:
                    from agents.src.hackathon.tools import SearchHackathonsTool
                    loc = job.metadata.get("parameters", {}).get("location", "")
                    if loc:
                        search_tool = SearchHackathonsTool()
                        raw = await search_tool.execute(location=loc)
                        search_data = json.loads(raw)
                        if search_data.get("success") and search_data.get("hackathons"):
                            exec_result = search_data
                            formatted = format_hackathon_results(search_data)
                except Exception:
                    pass

            yield f"data: {json.dumps({'event': 'complete', 'data': exec_result, 'formatted': formatted})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ─── Escrow Info (for frontend wallet funding) ───────────────

@app.get("/api/v1/escrow/info")
async def get_escrow_info():
    """Return contract addresses so the frontend can prompt wallet funding."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")
    cluster = get_cluster()
    return {
        "program_id": str(contracts.program_id),
        "usdc_mint": str(USDC_MINT),
        "cluster": cluster.cluster_name,
        "rpc_url": cluster.rpc_url,
        "native_currency": "SOL",
    }


@app.get("/api/v1/escrow/deposit/{job_id}")
async def get_escrow_deposit_info(job_id: int):
    """Check if a job's escrow has been funded and how much USDC is locked."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")
    try:
        dep = get_escrow_deposit(contracts, job_id)
        return {
            "job_id": job_id,
            "funded": dep.get("funded", False),
            "amount_usdc": dep.get("amount_usdc", 0),
            "released": dep.get("released", False),
            "refunded": dep.get("refunded", False),
            "poster": dep.get("poster", ""),
            "provider": dep.get("provider", ""),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get escrow deposit: {e}")


# ─── Job Lifecycle ────────────────────────────────────────────

@app.post("/api/v1/create", response_model=CreateJobResponse)
async def create_and_fund_job(req: CreateJobRequest):
    """Create a job, assign provider, and fund escrow with USDC."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")

    try:
        metadata_uri = req.metadata_uri or f"ipfs://sota-job-{int(time.time())}"

        # 1. Create job
        job_id = create_job(
            contracts,
            metadata_uri=metadata_uri,
            budget_usdc=req.budget_usdc,
            deadline_seconds=req.deadline_seconds,
        )

        # 2. Assign provider
        from solders.pubkey import Pubkey as _Pubkey
        provider_str = req.provider_address or (
            str(contracts.keypair.pubkey()) if contracts.keypair else ""
        )
        if provider_str:
            provider_pk = _Pubkey.from_string(provider_str)
            assign_provider(contracts, job_id, provider_pk)

        # 3. Fund escrow with USDC
        tx = fund_job(
            contracts,
            job_id=job_id,
            provider_pubkey=provider_pk if provider_str else contracts.keypair.pubkey(),
            usdc_amount=req.budget_usdc,
        )

        return CreateJobResponse(
            job_id=job_id,
            tx_hash=tx,
            budget_usdc=req.budget_usdc,
            usdc_locked=req.budget_usdc,
            provider=provider_str,
            message=f"Job #{job_id} created and funded with {req.budget_usdc:.2f} USDC",
        )
    except Exception as e:
        raise HTTPException(500, f"Job creation failed: {e}")


@app.post("/api/v1/status", response_model=JobStatusResponse)
async def check_status(req: JobStatusRequest):
    """Check job status + delivery confirmation state."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")

    try:
        job = get_job(contracts, req.job_id)
        delivery_ok = is_delivery_confirmed(contracts, req.job_id)

        deposit = {"funded": False, "released": False}
        try:
            deposit = get_escrow_deposit(contracts, req.job_id)
        except Exception:
            pass

        status_names = ["OPEN", "ASSIGNED", "COMPLETED", "RELEASED", "CANCELLED"]
        status = status_names[job["status"]] if job["status"] < len(status_names) else "UNKNOWN"

        return JobStatusResponse(
            job_id=req.job_id,
            status=status,
            poster=job["poster"],
            provider=job["provider"],
            budget_usdc=job["budget_usdc"],
            delivery_confirmed=delivery_ok,
            escrow_funded=deposit.get("funded", False),
            escrow_released=deposit.get("released", False),
            message=f"Job #{req.job_id}: {status} | Delivery: {'confirmed' if delivery_ok else 'pending'}",
        )
    except Exception as e:
        raise HTTPException(500, f"Status check failed: {e}")


@app.post("/api/v1/release")
async def release_job_payment(req: ReleaseRequest):
    """Release escrow payment. Requires delivery confirmation."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")

    try:
        delivery_ok = is_delivery_confirmed(contracts, req.job_id)
        if not delivery_ok:
            raise HTTPException(
                400,
                "Cannot release: delivery not confirmed. "
                "Owner must call confirmDelivery first.",
            )

        tx = release_payment(contracts, req.job_id)
        return {
            "job_id": req.job_id,
            "tx_hash": tx,
            "delivery_confirmed": True,
            "message": f"Payment released for job #{req.job_id}.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Release failed: {e}")


# ─── Delivery Confirmation Endpoint ──────────────────────────

@app.post("/api/v1/confirm-delivery")
async def api_confirm_delivery(req: ReleaseRequest):
    """Owner confirms delivery for a job."""
    if not contracts:
        raise HTTPException(503, "Not connected to chain")
    try:
        tx = confirm_delivery(contracts, req.job_id)
        return {
            "job_id": req.job_id,
            "tx_hash": tx,
            "message": f"Delivery confirmed for job #{req.job_id}",
        }
    except Exception as e:
        raise HTTPException(500, f"Confirm delivery failed: {e}")


# ═════════════════════════════════════════════════════════════
#  Agent <-> Butler Communication
# ═════════════════════════════════════════════════════════════

# In-memory fallback for user context
_user_context: Dict[str, Dict[str, Any]] = {}


class AgentDataRequest(BaseModel):
    request_id: str
    job_id: str
    data_type: str
    question: str
    fields: List[str] = []
    context: str = ""
    agent: str = ""


class AgentDataAnswer(BaseModel):
    request_id: str
    data: Dict[str, Any] = {}
    message: str = ""


class AgentUpdate(BaseModel):
    job_id: str
    status: str
    message: str
    data: Dict[str, Any] = {}
    agent: str = ""


class SetUserContextRequest(BaseModel):
    user_id: str = "default"
    profile: Dict[str, Any] = {}


@app.post("/api/agent/set-user-context")
async def set_user_context(req: SetUserContextRequest):
    _user_context[req.user_id] = req.profile
    if db:
        try:
            await db.upsert_user_profile(req.user_id, req.profile)
        except Exception as e:
            print(f"DB upsert_user_profile failed: {e}")
    return {"success": True, "user_id": req.user_id, "fields": list(req.profile.keys())}


@app.get("/api/agent/user-context/{user_id}")
async def get_user_context(user_id: str = "default"):
    if db:
        try:
            profile = await db.get_user_profile(user_id)
            if profile:
                return profile
        except Exception as e:
            print(f"DB get_user_profile failed: {e}")
    return _user_context.get(user_id, {})


@app.post("/api/agent/request-data")
async def handle_agent_data_request(req: AgentDataRequest):
    exchange = ButlerDataExchange.instance()

    if req.data_type == "user_profile":
        profile = None
        if db:
            try:
                profile = await db.get_user_profile("default")
            except Exception:
                pass

        if not profile:
            for uid, ctx in _user_context.items():
                if ctx:
                    profile = ctx
                    break

        if profile:
            if req.fields:
                filtered = {k: v for k, v in profile.items()
                            if k in req.fields and v is not None}
                if filtered:
                    return {
                        "request_id": req.request_id,
                        "data_type": "user_profile",
                        "data": filtered,
                        "source": "stored_context",
                        "message": f"Profile data retrieved ({len(filtered)} fields)",
                    }
            else:
                clean = {k: v for k, v in profile.items()
                         if v is not None and k not in ("id", "createdAt", "updatedAt")}
                return {
                    "request_id": req.request_id,
                    "data_type": "user_profile",
                    "data": clean,
                    "source": "stored_context",
                    "message": f"Full profile retrieved ({len(clean)} fields)",
                }

        if req.job_id:
            board = JobBoard.instance()
            job_listing = board.get_job(req.job_id)
            if job_listing and job_listing.metadata:
                job_params = job_listing.metadata.get("parameters", {})
                if job_params:
                    return {
                        "request_id": req.request_id,
                        "data_type": "user_profile",
                        "data": {
                            "note": "No user profile stored. Use the job parameters below.",
                            **job_params,
                        },
                        "source": "job_metadata",
                        "message": (
                            "No stored user profile available. "
                            "Job parameters provided instead."
                        ),
                    }

    if req.data_type == "preference":
        prefs = None
        if db:
            try:
                profile = await db.get_user_profile("default")
                if profile:
                    prefs = profile.get("preferences")
                    if isinstance(prefs, str):
                        import json as _json
                        prefs = _json.loads(prefs)
            except Exception:
                pass

        if not prefs:
            for uid, ctx in _user_context.items():
                prefs = ctx.get("preferences", {})
                if prefs:
                    break

        if prefs and req.fields:
            matched = {k: v for k, v in prefs.items() if k in req.fields}
            if matched:
                return {
                    "request_id": req.request_id,
                    "data_type": "preference",
                    "data": matched,
                    "source": "stored_context",
                    "message": f"Preferences found ({len(matched)} fields)",
                }

    if req.data_type == "confirmation":
        auto_confirm = os.getenv("BUTLER_AUTO_CONFIRM", "true").lower() == "true"
        if auto_confirm:
            return {
                "request_id": req.request_id,
                "data_type": "confirmation",
                "data": {"confirmed": True},
                "source": "auto_confirm",
                "message": "Auto-confirmed (BUTLER_AUTO_CONFIRM=true)",
            }

    exchange.post_request(req.request_id, req.job_id, req.model_dump())
    return {
        "request_id": req.request_id,
        "data_type": req.data_type,
        "data": {},
        "source": "queued",
        "message": (
            f"Request queued — awaiting user response. "
            f"Agent '{req.agent}' asked: {req.question}"
        ),
    }


@app.get("/api/agent/pending-requests")
async def get_pending_requests(job_id: Optional[str] = None):
    exchange = ButlerDataExchange.instance()
    pending = exchange.peek_pending_requests(job_id)
    return {"pending": pending, "count": len(pending)}


@app.post("/api/agent/answer")
async def answer_agent_request(req: AgentDataAnswer):
    exchange = ButlerDataExchange.instance()
    exchange.submit_answer(req.request_id, {
        "request_id": req.request_id,
        "data": req.data,
        "message": req.message or "Answer provided",
    })
    return {"success": True, "request_id": req.request_id}


@app.post("/api/agent/update")
async def receive_agent_update(update: AgentUpdate):
    exchange = ButlerDataExchange.instance()
    exchange.push_update(update.job_id, update.model_dump())
    return {"received": True, "job_id": update.job_id, "status": update.status}


@app.get("/api/agent/updates/{job_id}")
async def get_agent_updates(job_id: str):
    exchange = ButlerDataExchange.instance()
    updates = exchange.get_updates(job_id)
    return {"job_id": job_id, "updates": updates, "count": len(updates)}


# ═════════════════════════════════════════════════════════════
#  ClawBot Internal Bridge Endpoints
#  Called only by the Next.js API routes (same internal network).
#  Protected by X-Internal-Secret header.
# ═════════════════════════════════════════════════════════════

class InternalReleaseRequest(BaseModel):
    job_id: str        # MarketplaceJob.jobId (UUID string)
    wallet_address: str


class InternalRefundRequest(BaseModel):
    job_id: str


def _verify_internal_secret(request) -> bool:
    secret = os.getenv("INTERNAL_API_SECRET", "")
    if not secret:
        return False  # not configured — reject all
    return request.headers.get("X-Internal-Secret") == secret


from fastapi import Request as _FastAPIRequest, Depends as _Depends


def _check_internal_secret(request: _FastAPIRequest):
    secret = os.getenv("INTERNAL_API_SECRET", "")
    if not secret or request.headers.get("X-Internal-Secret") != secret:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=403, detail="Forbidden")


@app.post("/internal/release-payment")
async def clawbot_release_payment(
    req: InternalReleaseRequest,
    _: None = _Depends(_check_internal_secret),
):
    """
    Release escrow payment to an external ClawBot wallet.
    Called by app/api/marketplace/external/execute/route.ts after successful execution.
    """
    if not contracts:
        raise HTTPException(503, "Blockchain contracts not initialised")

    # Retrieve on-chain job id from MarketplaceJob metadata
    on_chain_job_id = await _get_onchain_job_id(req.job_id)
    if on_chain_job_id is None:
        logger.warning("No on-chain job id found for marketplace job %s", req.job_id)
        return {"success": False, "reason": "no_onchain_job"}

    try:
        confirm_delivery(contracts, int(on_chain_job_id))
    except Exception as e:
        logger.warning("confirm_delivery skipped for job %s: %s", on_chain_job_id, e)

    try:
        tx = release_payment(contracts, int(on_chain_job_id))
        logger.info("Payment released for job %s → tx %s", on_chain_job_id, tx)
        return {"success": True, "tx_hash": tx}
    except Exception as e:
        logger.error("release_payment failed for job %s: %s", on_chain_job_id, e)
        raise HTTPException(500, f"Release failed: {e}")


@app.post("/internal/refund-escrow")
async def clawbot_refund_escrow(
    req: InternalRefundRequest,
    _: None = _Depends(_check_internal_secret),
):
    """
    Refund escrow to the job poster after a failed ClawBot execution.
    Called by app/api/marketplace/external/execute/route.ts on failure.
    """
    if not contracts:
        raise HTTPException(503, "Blockchain contracts not initialised")

    on_chain_job_id = await _get_onchain_job_id(req.job_id)
    if on_chain_job_id is None:
        logger.warning("No on-chain job id found for marketplace job %s", req.job_id)
        return {"success": False, "reason": "no_onchain_job"}

    try:
        tx = refund_escrow(contracts, int(on_chain_job_id))
        logger.info("Escrow refunded for job %s → tx %s", on_chain_job_id, tx)
        return {"success": True, "tx_hash": tx}
    except Exception as e:
        logger.error("refund_escrow failed for job %s: %s", on_chain_job_id, e)
        raise HTTPException(500, f"Refund failed: {e}")


async def _get_onchain_job_id(marketplace_job_id: str) -> Optional[str]:
    """Look up the on-chain job ID from MarketplaceJob.metadata."""
    if _db_pool is None:
        return None
    try:
        row = await _db_pool.fetchrow(
            'SELECT metadata FROM "MarketplaceJob" WHERE "jobId" = $1',
            marketplace_job_id,
        )
        if not row or not row['metadata']:
            return None
        meta = row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata'])
        return str(meta.get('on_chain_job_id', '')) or None
    except Exception as exc:
        logger.warning("_get_onchain_job_id failed: %s", exc)
        return None


# ─── Stale execution token cleanup ───────────────────────────

async def _expire_stale_tokens_loop() -> None:
    """
    Background task: every 60s, expire unused tokens and trigger refunds.
    """
    from agents.src.shared.execution_token import expire_stale_tokens
    while True:
        await asyncio.sleep(60)
        if _db_pool is None:
            continue
        try:
            expired_job_ids = await expire_stale_tokens(_db_pool)
            for job_id in expired_job_ids:
                logger.info("Execution token expired for job %s — triggering refund", job_id)
                on_chain_job_id = await _get_onchain_job_id(job_id)
                if on_chain_job_id and contracts:
                    try:
                        refund_escrow(contracts, int(on_chain_job_id))
                    except Exception as e:
                        logger.warning("Auto-refund failed for job %s: %s", job_id, e)
        except Exception as exc:
            logger.warning("_expire_stale_tokens_loop error: %s", exc)


if __name__ == "__main__":
    import uvicorn

    print("Starting SOTA Butler API...")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "3001")))
