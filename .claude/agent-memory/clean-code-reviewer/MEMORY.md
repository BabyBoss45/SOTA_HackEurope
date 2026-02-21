# Clean Code Reviewer Memory - Euro_SOTA Project

## Project Structure
- `agents/src/shared/job_board.py` - Original in-process job board (singleton, process-local)
- `agents/src/shared/hub_connector.py` - WebSocket client for marketplace Hub (new, 2026-02-21)
- `agents/src/shared/chain_config.py` - Solana config, JobType IntEnum, keypair loading
- `agents/src/shared/auto_bidder.py` - AutoBidderMixin + JOB_TYPE_TAGS mapping + job_types_to_tags()
- `agents/src/shared/base_agent.py` - BaseArchiveAgent ABC, ActiveJob dataclass
- `agents/marketplace/` - WebSocket-based marketplace hub (FastAPI, port 3002 standalone, mounted at /hub on 3001)
  - `models.py` - Pydantic v2 models; BidAcceptedMsg has ONLY job_id+bid_id (no job data!)
  - `registry.py` - In-memory agent registry (tracks WebSocket connections)
  - `bidding.py` - Bid collection + winner selection engine
  - `router.py` - Job lifecycle orchestration (match -> broadcast -> bid -> notify)
  - `hub.py` - FastAPI app, REST endpoints, WebSocket handler at `/ws/agent`
- `agents/butler_api.py` - Mounts marketplace hub at /hub (port 3001)
- `agents/__main__.py` - CLI entry point, AGENT_PORT_ENVS mapping
- `agents/sota_sdk/` - Agent SDK for third-party developers

## Agent Port Map
- Butler: 3001, Manager: 3002 (but server.py defaults to 3001!), Caller: 3003
- x402: 3004, Hackathon: 3005, (gap 3006), Gift: 3007, Restaurant: 3008
- Refund: 3009, Smart Shopper: 3010, Trip Planner: 3011

## Architecture Patterns
- Hub mounted as sub-app at /hub on butler_api (port 3001)
- WS path: /hub/ws/agent (mounted), /ws/agent (standalone)
- Winner selection: lowest price under budget, ties broken by earliest `submitted_at`
- Tag matching: set intersection between job tags and agent tags
- All hub state is in-memory (no DB)
- SDK uses lazy imports for chain modules (only loaded when private key set)
- All 7 worker agents integrate HubConnector in FastAPI lifespan
- Manager does NOT connect to hub (orchestrator, not bidder)
- Factory functions: `create_<agent>_agent()` -> initialize + register_on_board (no start())

## Known Issues (hub connector review, 2026-02-21)
- CRITICAL: bid_accepted has only job_id+bid_id; hub_connector reads description/budget/deadline/metadata -> all zero/empty
  Both internal hub_connector AND SDK _resolve_job have this same bug
- 4 agents wrong job_type in /v1/rpc: restaurant=12(s/b 1/9), shopper=8(s/b 11), trip=9(s/b 12), gift=11(s/b 8)
- Manager defaults to port 3001 (collision with butler)
- .env.example files reference ws://localhost:3002/ws/agent (s/b :3001/hub/ws/agent)
- 5 newer agents never call agent.start() -- _running stays False
- x402 missing from docker-compose.yml
- COMPOSITE/JOB_SCOURING missing from JOB_TYPE_TAGS
- Caller lifespan comment misleading ("if SOTA_HUB_URL is set" -- always connects)

## Known Issues (hub review, 2026-02-20)
- hub.py module-level singletons (DIP violation)
- fire-and-forget asyncio.create_task in router.py
- "registered" ack not in MessageType enum
- JOB_CANCELLED defined but never sent
- No inbound WS message validation
- No bounds on budget_usdc/amount_usdc
- Race window: bids arrive after sleep() returns
- No registration timeout, no stale-connection reaper
- Agent IDs predictable (name_counter)
- CORS wildcard + credentials

## Known Issues (SDK full review, 2026-02-20)
- Mutable class-level defaults (tags=[], bid_strategy=DefaultBidStrategy())
- Cost module never wired into agent lifecycle
- _resolve_job fallback reads fields BidAcceptedMsg doesn't contain (same as connector bug)
- No per-job timeout, no concurrency limit
- send() silently drops on disconnect
- Tag lowering duplicated 3 times in bidding.py
- budget_usdc as float (precision risk for 6-decimal ERC20)

## Recurring Patterns to Watch
- Tag lowering duplication across hub AND SDK AND connector
- bid_accepted missing job data -- recurs in both SDK and hub_connector
- Fire-and-forget create_task without error handling
- USDC as float (precision risk)
- Sync web3 calls in async contexts

## Conventions
- Pydantic v2, `from __future__ import annotations`, logging.getLogger(__name__)
- Dataclasses for internal state, Pydantic for API boundaries
- Type hints throughout
