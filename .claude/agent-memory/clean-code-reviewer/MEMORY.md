# Clean Code Reviewer Memory - Euro_SOTA Project

## Project Structure
- `agents/src/shared/job_board.py` - Original in-process job board (singleton, process-local)
- `agents/marketplace/` - WebSocket-based marketplace hub (FastAPI, port 3002)
  - `models.py` - Pydantic v2 models for protocol messages and REST API
  - `registry.py` - In-memory agent registry (tracks WebSocket connections)
  - `bidding.py` - Bid collection + winner selection engine
  - `router.py` - Job lifecycle orchestration (match -> broadcast -> bid -> notify)
  - `hub.py` - FastAPI app, REST endpoints, WebSocket handler at `/ws/agent`
- `agents/sota_sdk/` - Agent SDK for third-party developers
  - `agent.py` - SOTAAgent base class (main entry point, boot sequence)
  - `models.py` - Job, Bid, BidResult, JobResult dataclasses
  - `config.py` - Env-based configuration (marketplace URL, chain config)
  - `server.py` - Embedded FastAPI health/status server
  - `marketplace/client.py` - WS client with auto-reconnect + exponential backoff
  - `marketplace/bidding.py` - BidStrategy ABC, DefaultBidStrategy, CostAwareBidStrategy
  - `chain/` - wallet.py, contracts.py (delivery proof, payment), registry.py
  - `tools/` - BaseTool (Pydantic + ABC), ToolManager registry

## Architecture Patterns
- Winner selection: lowest price under budget, ties broken by earliest `submitted_at`
- Tag matching: set intersection between job tags and agent tags
- All hub state is in-memory (no DB)
- SDK uses lazy imports for chain modules (only loaded when private key set)
- TYPE_CHECKING guard for agent<->server circular import

## Known Issues (hub review, 2026-02-20, updated)
- hub.py module-level singletons (DIP violation) -- use FastAPI lifespan state
- fire-and-forget asyncio.create_task in router.py -- tasks are local vars, may GC
- "registered" ack not in MessageType enum (hub.py line 200)
- JOB_CANCELLED defined but never sent anywhere
- CRITICAL: No inbound WS message validation -- KeyError on missing fields kills connection
- CRITICAL: No bounds on budget_usdc/amount_usdc -- negative bid always wins
- Race window: bids can arrive after sleep() returns but before status changes
- No registration timeout on WS accept (DoS vector)
- JSON decode error kills entire agent connection (should be per-message)
- No bid-rejection feedback sent to agents (silent drop)
- No "no winner" notification to bidders when job expires
- Agent IDs are predictable (name_counter) -- no crypto random
- CORS wildcard + credentials (hub.py lines 61-67)
- `import uuid` inside method body (router.py line 70)
- Inline response dict construction (list_jobs, get_job, list_agents) -- no response models
- No stale-connection reaper despite last_heartbeat field existing

## Known Issues (SDK full review, 2026-02-20)
- CRITICAL: Mutable class-level defaults (tags=[], bid_strategy=DefaultBidStrategy()) -- shared across all subclasses
- CRITICAL: Cost module never wired into agent lifecycle (initialize_cost_tracking, send_outcome never called)
- CRITICAL: _resolve_job fallback reads fields BidAcceptedMsg doesn't contain (description, tags, budget, etc.)
- Hub sends "registered" ack with agent_id -- SDK silently drops it
- web3 import at top of agent.py forces dependency for off-chain agents
- from . import cost in __init__.py crashes if paid package not installed
- No per-job timeout -- hanging execute() blocks forever
- No concurrency limit -- burst of accepted bids spawns unlimited tasks
- Shutdown wait for active jobs has no timeout
- send() in MarketplaceClient silently drops on disconnect, no retry/queue
- No registration ack wait -- agent starts listening before confirmed
- set_agent_tags via hasattr instead of on BidStrategy ABC interface
- JobResult dataclass exported but never used (execute returns raw dict)
- get_contract_addresses() and _load_abi() called repeatedly without caching
- budget_usdc as float throughout (precision risk for 6-decimal ERC20)
- build_and_send uses legacy gasPrice instead of EIP-1559
- register_agent/is_agent_active never called from boot sequence
- get_job returns positional tuple indices -- fragile if contract changes
- Duplicate Job dict parsing in 3 places (should be Job.from_hub_message classmethod)
- Tag lowering duplicated 3 times in bidding.py
- dotenv load_dotenv runs at import time with assumed project path structure

## Recurring Patterns to Watch
- Tag lowering duplication across hub AND SDK
- Sync web3 calls (build_and_send, wait_for_receipt) in async contexts
- Fire-and-forget create_task without error handling
- USDC as float (6 decimal ERC20, divided by 1e6) -- precision risk

## Known Issues (cost module review, 2026-02-20)
- `auto_instrument()` uses "google_genai" but paid-python expects "gemini"
- `wrap_gemini` imports `PaidGoogleGenAI` -- class may not exist; undocumented
- `wrap_mistral` imports `PaidMistral` -- class not in docs; only auto_instrument supported
- `report_tokens()` puts token fields at costData top-level; should be in `attributes` sub-dict
- `paid_tracing` context manager never used -- `send_outcome` docs claim it runs inside one
- `initialize_cost_tracking` never called from agent._boot() -- dead code path
- `CostTracker.log_llm_call`/`log_external_cost` never called from anywhere
- `CostTracker` is process-wide singleton, not thread-safe (dict mutation from concurrent tasks)
- No try/except around paid-python imports in signals.py/config.py (crashes if pkg missing)
- `report()` puts metadata at data top-level alongside costData -- may not be intended
- No `PAID_API_KEY` env var set; uses custom `SOTA_PAID_API_KEY` -- initialize_tracing may ignore it

## Paid.ai SDK Notes (paid-python >=1.0.5)
- auto_instrument valid names: anthropic, gemini, openai, openai-agents, bedrock, langchain, instructor, mistral
- Wrapper classes documented: PaidOpenAI, PaidAsyncOpenAI (openai); PaidAnthropic, PaidAsyncAnthropic (anthropic)
- Google/Gemini and Mistral wrappers not explicitly documented -- prefer auto_instrument for those
- costData token format uses `attributes` sub-dict, not top-level keys
- paid_tracing(external_customer_id, external_product_id=...) -- context manager for cost attribution
- signal(event_name, data, enable_cost_tracing) -- emits events within tracing context

## Conventions
- Pydantic v2, `from __future__ import annotations`, logging.getLogger(__name__)
- Dataclasses for internal state, Pydantic for API boundaries
- Type hints throughout
