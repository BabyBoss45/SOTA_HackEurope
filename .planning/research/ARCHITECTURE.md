# Architecture Research

**Domain:** AI agent marketplace with dual payment rails (hackathon polish)
**Researched:** 2026-03-14
**Confidence:** HIGH (based on direct codebase analysis)

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Marketplace UI   │  │  ChatScreen      │  │  Developer Portal │  │
│  │  (polling /api/   │  │  (Butler + Voice  │  │  (agent deploy)   │  │
│  │   tasks @ 5s)     │  │   + Stripe pay)   │  │                   │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘  │
├───────────┼─────────────────────┼──────────────────────────────────┤
│           │  NEXT.JS API LAYER  │                                    │
│  ┌────────▼─────────┐  ┌───────▼──────────┐  ┌──────────────────┐  │
│  │ GET /api/tasks    │  │ POST /api/stripe/ │  │ POST /api/       │  │
│  │ (Prisma read)     │  │ create-payment-   │  │ marketplace/     │  │
│  │                   │  │ intent            │  │ execute           │  │
│  └────────┬─────────┘  └──────────────────┘  └──────────────────┘  │
├───────────┼────────────────────────────────────────────────────────┤
│           │         PYTHON FASTAPI LAYER                            │
│  ┌────────▼─────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Butler API       │  │  JobBoard         │  │  Marketplace Hub  │  │
│  │  /api/v1/chat     │  │  (in-memory       │  │  (WebSocket for   │  │
│  │  /api/v1/         │  │   singleton)       │  │   external agents)│  │
│  │  marketplace/post │  │                   │  │                   │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘  │
│           │                     │                                    │
│  ┌────────▼─────────────────────▼──────────────────────────────┐   │
│  │              Worker Agents (in-process)                       │   │
│  │  hackathon | caller | restaurant | trip | gift | shopper ... │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                      DATA LAYER                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  PostgreSQL       │  │  In-Memory        │  │  Solana Chain     │  │
│  │  (Prisma ORM)     │  │  (JobBoard state) │  │  (escrow, rep)    │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **ChatScreen** | User conversation, job posting trigger, bid timer display, Stripe/wallet payment UI | Butler API (HTTP), Stripe API, Solana wallet adapter |
| **Marketplace UI** | Displays all jobs with status, polls for updates | Next.js `/api/tasks` (HTTP polling every 5s) |
| **Next.js `/api/tasks`** | Reads MarketplaceJob + AgentJobUpdate from Prisma, transforms to dashboard format | PostgreSQL via Prisma |
| **Next.js `/api/stripe/create-payment-intent`** | Creates Stripe PaymentIntent with job metadata | Stripe API |
| **Butler API (FastAPI)** | Chat with Claude, job posting, marketplace management | JobBoard (in-process), Worker agents, Solana contracts, Database |
| **JobBoard** | In-memory job registry, bid collection, winner selection, execution dispatch | Worker evaluators/executors (function calls), Database (via injected pool) |
| **Worker Agents** | Evaluate jobs, place bids, execute tasks | JobBoard (registered callbacks), external APIs (Twilio, SerpAPI, etc.) |
| **PostgreSQL** | Persistent source of truth for jobs, bids, users, agents | Prisma (from Next.js), asyncpg (from Python) |
| **Solana Smart Contracts** | Escrow, payment release, on-chain reputation | Called from Butler API (Python) and frontend (JS) |

## Data Flow

### Flow 1: Job Creation (Butler Chat to Marketplace)

This is the critical path that currently has integration gaps.

```
User types/speaks task
    |
    v
ChatScreen.handleSendText() ──HTTP──> Butler API /api/v1/chat
    |                                       |
    |                                       v
    |                              Claude AI processes message
    |                                       |
    |                              Butler tools detect job intent
    |                                       |
    |                                       v
    |                              PostJobTool.execute()
    |                                       |
    |                                       v
    |                              JobBoard.post_and_select(job)
    |                                       |
    |                              ┌────────┤
    |                              |        v
    |                              |  Workers evaluate & bid
    |                              |  (bid_window_seconds wait)
    |                              |        |
    |                              |        v
    |                              |  Winner selected
    |                              └────────┤
    |                                       |
    |                                       v
    |                              [WRITE TO DB] ← ─ ─ ─ ─ ─ GAP: this step
    |                              MarketplaceJob row created    is inconsistent
    |                              AgentJobUpdate rows for bids
    |                                       |
    v                                       v
ChatScreen receives response       /api/tasks reads from Prisma
with job_posted data               Marketplace UI polls every 5s
    |                                       |
    v                                       v
StripePayment or                   Job appears (or doesn't) on
wallet prompt shown                marketplace page
```

**Key gap:** The JobBoard operates in-memory in the Python process. Jobs are written to PostgreSQL via the `Database` class, but the write happens *inside* `PostJobTool.execute()`. If that write fails silently, or the job completes before it's written, the marketplace UI (which reads from Prisma/PostgreSQL) never sees it.

### Flow 2: Bidding Timer

```
ChatScreen.postJobToMarketplace()
    |
    ├── setBidProgress({ active: true, duration: 15 })  ← Frontend timer (15s)
    |
    ├── fetch(BUTLER_URL + "/marketplace/post")  ← HTTP request
    |         |
    |         v
    |   JobBoard.post_and_select()
    |         |
    |         ├── asyncio.sleep(bid_window_seconds)  ← Backend timer (60s default)
    |         |
    |         v
    |   Return result after bid window closes
    |
    v
setBidProgress(null)  ← Progress bar removed on HTTP response
```

**Key problem:** The frontend shows a 15-second progress bar, but the backend `bid_window_seconds` defaults to 60 seconds. The progress bar completes visually, then the user waits ~45 more seconds with no feedback. The HTTP request blocks until `post_and_select()` returns. Any new chat message during this wait does NOT reset the timer because `bidProgress` state is independent of chat state -- this is actually correct behavior, but the UI needs to show that the request is still pending.

### Flow 3: Dual Payment (Stripe + Solana Wallet)

```
Job completed, escrow needs funding
    |
    v
Butler API returns job_posted.escrow.needs_user_funding = true
    |
    v
ChatScreen.triggerStripePayment(jobResult)
    |
    ├── Option A: StripePayment component rendered inline
    |       |
    |       v
    |   POST /api/stripe/create-payment-intent
    |       → Stripe PaymentIntent created
    |       → clientSecret returned
    |       |
    |       v
    |   User pays via Apple Pay / Google Pay / Card
    |       |
    |       v
    |   onSuccess callback → POST /marketplace/execute/{boardJobId}
    |       → Agent executes task
    |       → Results displayed in chat
    |
    └── Option B: Solana wallet payment (NOT YET IMPLEMENTED AS EQUAL OPTION)
            |
            v
        transferFunds tool exists but is a generic SOL transfer,
        NOT an escrow-funding USDC transaction
```

**Key problem:** Wallet payment is not an equal alternative to Stripe. The `transferFunds` client tool sends raw SOL (not USDC), does not call `fund_job` on the smart contract, and is not surfaced in the same payment UI as Stripe. The Solana escrow flow (`create_job` -> `fund_job` -> `assign_provider` -> `confirm_delivery` -> `release_payment`) exists in the contract but is not wired into the ChatScreen payment flow.

### Flow 4: Job Status Sync

```
                PostgreSQL (source of truth for UI)
                    |
        ┌───────────┼───────────┐
        |           |           |
   Write path    Write path   Read path
   (Python DB)   (Next.js     (Next.js
    asyncpg)      Prisma)      Prisma)
        |           |           |
   Butler API    /api/         /api/tasks
   job_board    marketplace/    GET
   updates      execute         |
        |           |           v
        v           v      Marketplace UI
   MarketplaceJob            (5s poll)
   AgentJobUpdate
```

**Key problem:** There are TWO write paths to the database (Python asyncpg and Next.js Prisma) but no event-driven notification. The marketplace UI polls every 5 seconds, which means up to 5 seconds of stale data. More critically, status values are inconsistent:

| JobBoard (Python in-memory) | PostgreSQL `status` field | Dashboard UI mapping |
|-----------------------------|---------------------------|---------------------|
| `OPEN` | `"open"` | `"queued"` |
| `SELECTING` | `"selecting"` | `"queued"` |
| `ASSIGNED` | `"assigned"` | `"executing"` |
| (no equivalent) | `"completed"` | `"completed"` |
| `EXPIRED` | `"expired"` | `"failed"` |

The Python backend writes `"assigned"` when a winner is selected but the job may still be executing. The Next.js `/api/tasks` route also checks `AgentJobUpdate.status` for `"in_progress"` and `"completed"`, which can override the `MarketplaceJob.status`. This dual-source logic works but makes debugging difficult.

## Architectural Patterns

### Pattern 1: In-Memory Singleton with DB Sync

**What:** The `JobBoard` is a process-local singleton that holds all active job state in Python dicts. Database writes happen as side effects via the injected `Database` class.

**When to use:** Hackathon-appropriate for low-scale, single-process deployment.

**Trade-offs:**
- Pro: Fast, no external dependencies for job matching
- Con: State lost on process restart, no cross-process visibility
- Con: DB sync is best-effort (exceptions caught and logged, not retried)

### Pattern 2: HTTP Polling for Real-Time UI

**What:** The marketplace page polls `GET /api/tasks` every 5 seconds using `setInterval`.

**When to use:** When WebSocket infrastructure is not worth the complexity. Acceptable for hackathon.

**Trade-offs:**
- Pro: Simple, works with Vercel serverless
- Con: Up to 5s delay for status changes
- Con: Unnecessary load when no changes exist

**For the hackathon demo:** 5-second polling is fine. The demo flow is: create job in chat -> walk audience through marketplace showing it appear -> show execution -> show payment. The 5-second delay is imperceptible in a live walkthrough.

### Pattern 3: Stripe-First Payment with Deferred Execution

**What:** Payment is collected via Stripe *before* task execution. The `onSuccess` callback triggers `POST /marketplace/execute/{boardJobId}` which starts the agent work.

**When to use:** When you want guaranteed payment before spending compute.

**Trade-offs:**
- Pro: No risk of unpaid work
- Con: User pays before seeing results (acceptable for small amounts)
- Con: Stripe webhook for confirmation is fire-and-forget (no retry/DLQ -- acceptable per project constraints)

## Anti-Patterns Present in Codebase

### Anti-Pattern 1: Dual Data Ownership

**What people do:** Both Python (asyncpg) and Next.js (Prisma) write to the same `MarketplaceJob` table without coordination.

**Why it's a problem:** Race conditions. If Butler API writes status `"assigned"` and the Next.js execute route writes status `"completed"` at the same time, last-write-wins. No optimistic locking.

**For the hackathon fix:** Acceptable. The flows are sequential in practice (Python writes first, then Next.js may write later). Add explicit status transition logging to make debugging easier.

### Anti-Pattern 2: Timer Mismatch Between Frontend and Backend

**What people do:** Frontend shows a 15-second bid timer, backend waits 60 seconds.

**Why it's a problem:** User sees timer complete, then waits with no feedback for 45 more seconds.

**Fix:** Either reduce `bid_window_seconds` to 15 in the JobBoard for demo purposes, or extend the frontend timer to match. The simpler fix: set `bid_window_seconds=15` in `PostJobTool.execute()` since the demo agents respond in <2 seconds anyway.

### Anti-Pattern 3: Wallet Payment Not Wired to Escrow

**What people do:** The `transferFunds` tool sends raw SOL, not USDC, and does not call `fund_job` on the smart contract.

**Why it's a problem:** The "wallet payment" option is a completely different flow from the Stripe path. It does not fund escrow, does not trigger execution, and uses the wrong token (SOL vs USDC).

**Fix for hackathon:** Create a proper `fundJobWithWallet` flow that: (1) calls `fund_job` on the Anchor contract with USDC, (2) on success, triggers `POST /marketplace/execute/{boardJobId}` same as Stripe does.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Stripe** | PaymentIntent API via Next.js route, Elements SDK in React | Works. Missing: webhook for payment confirmation (relies on client-side `confirmPayment` result) |
| **Solana/Anchor** | Python `solders` + `anchorpy` for contract calls; JS `@solana/web3.js` + wallet adapter for frontend | Contract functions exist (`create_job`, `fund_job`, `release_payment`) but frontend only uses generic SOL transfer |
| **Anthropic Claude** | Python SDK in Butler Agent | Works. Claude detects job intent and calls `PostJobTool` |
| **ElevenLabs** | React SDK for voice, client tools for wallet/marketplace | Works. Voice agent triggers same `postJobToMarketplace` flow |
| **PostgreSQL** | Prisma (Next.js) + asyncpg (Python) | Two ORMs hitting same DB. No conflict in practice for hackathon scale |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| ChatScreen <-> Butler API | HTTP POST (direct fetch) | Cross-origin, CORS configured |
| Butler API <-> JobBoard | In-process function call | Same Python process, no network |
| Marketplace UI <-> Next.js API | HTTP GET polling (5s) | Same origin, no CORS issues |
| Next.js API <-> PostgreSQL | Prisma ORM | Connection pooling via Prisma |
| Butler API <-> PostgreSQL | asyncpg pool | Separate connection pool from Prisma |
| ChatScreen <-> Stripe | React Elements SDK + Next.js route | PaymentIntent created server-side |
| ChatScreen <-> Solana | Wallet adapter (client-side signing) | Transactions signed in browser |

## Build Order for Fixes

Based on dependency analysis, the five active issues should be fixed in this order:

### Phase 1: Job Creation Pipeline (foundation for everything else)

**Fix:** Ensure `PostJobTool.execute()` reliably writes `MarketplaceJob` to PostgreSQL with correct status, tags, bids, and winner before returning.

**Why first:** If jobs don't appear in the database, the marketplace UI shows nothing and status sync is irrelevant. This is the critical data pipeline.

**Dependencies:** None. This is the foundation.

**Components touched:** `agents/src/butler/tools.py` (PostJobTool), `agents/src/shared/database.py` (write path)

### Phase 2: Timer Alignment

**Fix:** Set `bid_window_seconds=15` in the PostJobTool call to JobBoard, matching the frontend timer. Alternatively, make the frontend timer duration dynamic based on a config value.

**Why second:** After Phase 1, jobs will appear on the marketplace. But the timer mismatch makes the chat flow feel broken. This is a quick config change.

**Dependencies:** Phase 1 (jobs must be created correctly for timer to matter)

**Components touched:** `agents/src/butler/tools.py` (bid_window_seconds parameter), `mobile_frontend/src/components/ChatScreen.tsx` (BidProgressBar duration)

### Phase 3: Status Sync

**Fix:** Ensure the Python backend writes status transitions to PostgreSQL at each lifecycle stage: `open` -> `selecting` -> `assigned` -> `in_progress` -> `completed`. The `/api/tasks` route already handles these statuses correctly in its mapping logic.

**Why third:** With Phases 1-2 done, jobs appear and the timer works. But the marketplace shows stale statuses. This fix ensures real-time-ish accuracy.

**Dependencies:** Phase 1 (database writes must work)

**Components touched:** `agents/butler_api.py` (execute_job_after_escrow), `agents/src/shared/database.py` (status updates), `agents/src/shared/job_board.py` (status callbacks)

### Phase 4: Wallet Payment as Equal Option

**Fix:** In ChatScreen, when `escrow.needs_user_funding` is true, show two buttons: "Pay with Card" (existing Stripe flow) and "Pay with Wallet" (new flow that calls `fund_job` on the Anchor contract with USDC via wallet adapter). Both flows should trigger execution via `POST /marketplace/execute/{boardJobId}` on success.

**Why fourth:** Requires the job pipeline and status sync to be working. The Stripe path already works as proof of concept.

**Dependencies:** Phases 1-3 (correct job_id needed for `fund_job`, status sync needed to show payment result)

**Components touched:** `mobile_frontend/src/components/ChatScreen.tsx` (payment UI), new component or extension of StripePayment for wallet option, Solana contract interaction utilities

### Phase 5: Login Screen Polish

**Fix:** Wallet connection only at payment time, not at login. Clean up login fields.

**Why last:** Purely cosmetic. Does not affect data flow or integration. The WalletConnectButton already auto-connects a demo wallet, so this is about removing it from the login screen and deferring to payment time.

**Dependencies:** Phase 4 (wallet connection flow at payment time must be designed first)

**Components touched:** Login page components, WalletConnectButton placement

## Scaling Considerations

Not relevant for hackathon, but noted for completeness:

| Concern | At Demo (5 users) | At 1K users | At 10K users |
|---------|-------------------|-------------|--------------|
| JobBoard in-memory | Fine | Needs Redis/DB backing | Needs distributed queue |
| 5s polling | Fine | Fine with CDN | Replace with WebSocket/SSE |
| Dual DB writers | Fine | Add transaction IDs | Single write path with event sourcing |
| Stripe + Solana | Fine | Add webhook verification | Add payment reconciliation service |

## Sources

- Direct codebase analysis (all file paths referenced above)
- Prisma schema at `/prisma/schema.prisma`
- Solana contract interfaces at `/agents/src/shared/chain_contracts.py`
- Next.js API routes at `/app/api/tasks/route.ts`, `/app/api/marketplace/execute/route.ts`
- Butler API at `/agents/butler_api.py`
- JobBoard at `/agents/src/shared/job_board.py`
- ChatScreen at `/mobile_frontend/src/components/ChatScreen.tsx`
- StripePayment at `/mobile_frontend/src/components/StripePayment.tsx`

---
*Architecture research for: SOTA AI Agent Marketplace hackathon polish*
*Researched: 2026-03-14*
