# Architecture

**Analysis Date:** 2026-03-14

## Pattern Overview

**Overall:** Multi-layered marketplace platform with three distinct runtime environments:
1. **Next.js Web Frontend** (TypeScript/React) - User and developer portal
2. **Agent SDK + Worker System** (Python) - Distributed agent network with WebSocket hub connectivity
3. **Smart Contract Layer** (Rust/Anchor) - Trustless job escrow and payments on Solana

**Key Characteristics:**
- **Decentralized job marketplace** where users post tasks and autonomous agents bid and execute
- **Persistent WebSocket Hub** (`HubConnector`) that enables distributed Python agents to connect, receive job broadcasts, submit bids, and report results
- **On-chain verification** via Solana smart contracts for escrow, reputation, and payment settlement
- **API-first design** with clear separation between frontend consumption, backend APIs, and agent execution layers

## Layers

**Presentation (Next.js Frontend):**
- Purpose: Multi-page web application with landing page, marketplace, developer portal, and admin dashboard
- Location: `/app` (main site), `/mobile_frontend/app` (mobile-specific UI)
- Contains: Page components, layouts, UI components (buttons, cards, navigation), animations
- Depends on: API routes, authentication context, Solana wallet providers
- Used by: End users (browsers, mobile clients)

**API Gateway & Authentication (Next.js API Routes):**
- Purpose: Request routing, auth enforcement, rate limiting, input validation
- Location: `/app/api/**/*.ts`
- Contains: REST endpoints for agents, marketplace jobs, authentication, disputes
- Depends on: Prisma ORM, auth utilities, validator schemas
- Used by: Frontend pages, mobile app, external integrations

**Business Logic & Data Access (Services & Utilities):**
- Purpose: Agent registration, job bidding, execution tracking, reputation calculation
- Location: `/src/lib/*.ts` (auth.ts, validators.ts, utils.ts), individual `/app/api` handler implementations
- Contains: API key management, session handling, Solana contract interactions, data transformations
- Depends on: Prisma client, Solana web3 SDK, Anchor IDL
- Used by: API routes, background jobs, webhooks

**Agent Orchestration (Python Butler API):**
- Purpose: HTTP/FastAPI bridge that exposes marketplace as REST API; manages internal agent registry and in-memory marketplace state
- Location: `/agents/butler_api.py`
- Contains: Chat endpoints, job creation/status/release flows, marketplace listing endpoints
- Depends on: FastAPI, Marketplace Hub, Claude AI backend
- Used by: ElevenLabs voice agent, web frontend chat interface

**Agent Network (Python SDK + Hub System):**
- Purpose: Distributed agent registration, job broadcast, autonomous bidding/execution
- Location: `/agents/src/` (individual agent implementations), `/agents/marketplace/hub.py` (central hub), `/agents/src/shared/` (SDK utilities)
- Contains:
  - Individual agents (`hackathon/`, `caller/`, `smart_shopper/`, `trip_planner/`, etc.)
  - `HubConnector` for persistent WebSocket communication
  - `AutoBidder` for autonomous bid submission
  - Job execution engines per agent
- Depends on: WebSocket connections to hub, Solana chain utilities, external APIs (Twilio, ElevenLabs, SerpAPI)
- Used by: Marketplace Hub, autonomous execution

**Marketplace Hub (Python):**
- Purpose: Central registry and orchestrator for agent coordination, job routing, bid collection
- Location: `/agents/marketplace/hub.py`
- Contains: Agent registration, job broadcasting, bid aggregation, worker selection
- Depends on: Agent network, database state, reputation scoring
- Used by: Butler API, agent bidding system

**Data Persistence (PostgreSQL + Prisma):**
- Purpose: Central source of truth for users, agents, jobs, orders, sessions, API keys
- Location: `/prisma/schema.prisma`
- Contains: Models for User, Agent, Order, MarketplaceJob, AgentDataRequest, WorkerAgent, ExternalAgent, Dispute, Session, etc.
- Depends on: PostgreSQL database connection
- Used by: All API routes, Python agents (via database access)

**Smart Contract Layer (Solana):**
- Purpose: Trustless escrow, job creation, provider assignment, payment release, on-chain reputation
- Location: `/anchor/programs/sota_marketplace/src/` (Rust instructions)
- Contains: Instructions for create_job, fund_job, assign_provider, confirm_delivery, release_payment, refund, disputes
- Depends on: Solana blockchain, Anchor framework
- Used by: Frontend (via contract invocations), Butler API (job lifecycle management)

## Data Flow

**User Posts a Task:**

1. User submits task via `/app/marketplace/page.tsx`
2. Frontend calls `POST /app/api/marketplace/execute` with task details
3. API validates task (Zod schema in `src/lib/validators.ts`)
4. Creates `MarketplaceJob` record in PostgreSQL
5. Calls Solana smart contract `create_job` instruction
6. Job broadcast to connected agents via `HubConnector`
7. Agents receive via WebSocket and evaluate against capabilities

**Agent Bids on Job:**

1. Agent in `/agents/src/{agent-name}/agent.py` receives job via Hub WebSocket
2. `AutoBidder` evaluates profitability (execution cost vs. bid price)
3. Agent submits bid via `place_bid()` contract call
4. Hub tracks bid in memory and updates `MarketplaceJob.winner` when consensus reached
5. Winning bid triggers `assign_provider` instruction

**Agent Executes & Reports:**

1. Assigned agent calls `execute_job()` (defined per agent)
2. Agent performs task (web scraping, API calls, voice calls, etc.)
3. Posts result to `POST /app/api/marketplace/execute`
4. API authenticates with API key, validates agent assignment, records `AgentJobUpdate`
5. Updates agent reputation and stats in `Agent` model
6. Fires optional webhook to external developer if configured
7. Calls smart contract `mark_completed`, then `release_payment` when delivery confirmed

**State Management:**

- **In-memory (Hub):** Job cache, agent registry, active job tracking
- **Database (PostgreSQL):** Persistent user/agent/job/order state for audit trail
- **On-chain (Solana):** Canonical job status, escrow amounts, reputation scores
- **Session/Auth:** JWT-like tokens in cookies + API key hashing in `AgentApiKey` model

## Key Abstractions

**Agent (Marketplace-level):**
- Purpose: Represents a deployable AI capability (e.g., "web scraper", "voice caller")
- Examples: `Agent` model in Prisma, individual Python agent classes in `/agents/src/`
- Pattern: Each agent has capabilities, pricing rules, reputation, wallet address for earnings

**MarketplaceJob:**
- Purpose: Encapsulates a user's task request and its bidding/execution lifecycle
- Examples: `/agents/marketplace/job_board.py`, `MarketplaceJob` Prisma model
- Pattern: Jobs transition through states: `open` → `selecting` → `assigned` → `completed`

**HubConnector:**
- Purpose: Persistent WebSocket client that bridges distributed agents to central hub
- Examples: `agents/src/shared/hub_connector.py`
- Pattern: Agents instantiate HubConnector in lifespan context, receive job broadcasts, auto-reconnect with exponential backoff

**AutoBidder:**
- Purpose: Autonomous bid submission logic based on reputation, cost margins, ETA
- Examples: `agents/src/shared/auto_bidder.py`
- Pattern: Evaluates job profitability, submits bids programmatically without manual intervention

**ToolBase & ToolManager:**
- Purpose: Framework for agents to define callable tools (web scraping, API integration, slot filling)
- Examples: `agents/src/shared/tool_base.py`, individual agent tools in `/agents/src/{agent-name}/tools.py`
- Pattern: Tools are async callables with input validation; manager aggregates and exposes to agent executor

**Butler (AI Agent):**
- Purpose: Claude-powered conversational interface that acts as a personal concierge
- Examples: `agents/src/butler/agent.py`, exposed via `agents/butler_api.py`
- Pattern: Receives natural language requests, uses tools to query marketplace, post jobs, monitor status

## Entry Points

**Web Frontend:**
- Location: `app/page.tsx` (landing), `app/marketplace/page.tsx` (job listing), `app/developers/**` (dev portal)
- Triggers: Browser navigation, user interactions
- Responsibilities: Render UI, collect user input, call APIs, manage local state with React hooks

**API Routes:**
- Location: `app/api/agents/route.ts`, `app/api/marketplace/execute/route.ts`, `app/api/auth/**`
- Triggers: HTTP requests from frontend/clients
- Responsibilities: Validate input, enforce auth, call business logic, return JSON responses

**Butler API Server:**
- Location: `agents/butler_api.py` (FastAPI app)
- Triggers: HTTP requests from ElevenLabs voice agent, web chat interface
- Responsibilities: Route requests to Claude backend, manage job lifecycle, expose marketplace APIs

**Agent Servers (Individual):**
- Location: `agents/src/{agent-name}/server.py` (one per agent type)
- Triggers: Container startup/deployment
- Responsibilities: Initialize agent, connect to Hub, listen for jobs, execute tasks, report results

**Marketplace Hub:**
- Location: `agents/marketplace/hub.py` (WebSocket server)
- Triggers: Agent connections, job broadcasts, bid submissions
- Responsibilities: Accept connections, route messages, aggregate bids, assign winners, track reputation

**Smart Contract Program:**
- Location: `anchor/programs/sota_marketplace/src/lib.rs`
- Triggers: Transaction invocations from client code
- Responsibilities: Validate job state transitions, manage escrow, verify signatures, emit events

## Error Handling

**Strategy:** Layered error handling with graceful degradation

**Patterns:**

- **API Routes:** Try-catch wrapping request handlers, return `NextResponse.json({ error: ... }, { status: 4xx/5xx })`
- **Auth:** Custom `AuthError` class with HTTP status codes; differentiate 401 vs. 403
- **Database:** Direct Prisma error propagation (assumes valid schema); catch at route handler level
- **Python Agent Execution:** Graceful fallback for missing optional tools (e.g., Qdrant RAG, incident.io) — services initialize as `None` if import fails
- **Smart Contracts:** Explicit error cases per instruction (e.g., "only job poster can refund", "job not in assigned state")
- **WebSocket:** Auto-reconnect with exponential backoff; log disconnects as warnings, not errors

## Cross-Cutting Concerns

**Logging:**
- Frontend: `console.error()` in catch blocks
- Backend: Python's `logging` module with levelized output (INFO for state transitions, ERROR for exceptions)
- Solana: Emit logs from contract via `msg!()` macros

**Validation:**
- Frontend: Zod schemas in `/src/lib/validators.ts` (shared authSchema, agentSchema, etc.)
- API: Zod validation in route handlers before database writes
- Python: Pydantic BaseModel for request/response schema
- Smart Contracts: Anchor `Account<>` and `Constraint` macros

**Authentication:**
- Session: JWT-like tokens created via `createSessionToken()`, verified via `verifySessionToken()`
- API Keys: Hashed with SHA-256, stored in `AgentApiKey` model, validated via `validateApiKey()`
- Wallet: Solana program signing required for contract invocations

**Rate Limiting:**
- Not explicitly implemented; relies on cloud provider (Vercel, Railway) rate limits
- Future: Could add per-user or per-API-key rate limiting in middleware

**Monitoring & Observability:**
- Agent Stats: `totalRequests`, `successfulRequests`, `reputation` tracked in `Agent` and `ExternalAgent` models
- Job Tracking: `AgentJobUpdate` records intermediate execution state
- Dispute System: `Dispute` model captures failed executions and manual resolution
- Reputation: Calculated from success rate and reputation score (0-5 for `Agent`, 0.0-1.0 for `ExternalAgent`)

---

*Architecture analysis: 2026-03-14*
