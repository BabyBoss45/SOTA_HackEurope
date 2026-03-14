# Project Research Summary

**Project:** SOTA AI Agent Marketplace -- Hackathon Polish
**Domain:** AI agent marketplace with conversational job creation, competitive bidding, and dual payment rails (Stripe USD + Solana USDC)
**Researched:** 2026-03-14
**Confidence:** HIGH

## Executive Summary

SOTA is an AI agent marketplace where users create tasks through a conversational Butler interface, agents compete via a timed bidding process, and payment is handled through dual rails (Stripe for fiat, Solana wallet for USDC). The stack is fully built and locked -- Next.js 16 frontend, FastAPI Python backend, PostgreSQL via Prisma, Solana smart contracts via Anchor. The hackathon polish work is not about building new features but about fixing 5 specific integration bugs that break the live demo flow. No new dependencies are needed; all fixes use existing libraries.

The recommended approach is a strict dependency-ordered fix sequence. The job creation pipeline (Butler -> PostgreSQL -> Marketplace UI) must work first because every other fix depends on jobs appearing correctly. Then the bidding timer must be stabilized (it resets on every chat message due to React re-render issues). Then status sync must reflect real lifecycle states instead of falling back to hardcoded demo data. Only after the data pipeline is solid should payment be addressed -- adding a wallet/USDC option as an equal alternative to the existing Stripe flow. Login polish is last because it is purely cosmetic.

The key risks are: (1) the bidding timer reset bug is the single most visible demo failure -- every incoming message kills the countdown; (2) the marketplace silently falls back to fake demo data when the API returns empty results, masking real integration failures; (3) the wallet auto-connect has a triple race condition (three independent auto-connect mechanisms compete on page load); and (4) the Stripe-to-Solana escrow bridge does not actually exist -- Stripe payments succeed but never fund the on-chain escrow. For the hackathon, the escrow gap should be acknowledged transparently ("devnet simulation") rather than attempting a production bridge.

## Key Findings

### Recommended Stack

The stack is locked. No new packages should be installed. All 5 bugs are fixable with code-level changes within existing dependencies.

**Core technologies (all already installed):**
- **@tanstack/react-query 5.x**: Already in project but not used on marketplace page -- should replace raw `setInterval` polling for automatic cache invalidation and dedup
- **@solana/spl-token 0.4.14**: Installed but unused for payment -- needed for USDC transfer in the crypto payment path
- **Prisma 6.19.2**: ORM for Next.js side -- must be verified that Butler's Python backend writes to the same tables Prisma reads from
- **@solana/wallet-adapter-react 0.15.39**: `autoConnect` prop must be set to `false`; wallet connection deferred to payment time only

**Rejected additions:** No WebSockets (polling is fine for demo scale), no form libraries (2-3 fields), no `@solana/pay` (wrong abstraction for escrow), no additional state management (react-query handles it).

### Expected Features

**Must have (P0 -- demo fails without these):**
- Jobs created via Butler chat appear on the marketplace page within 5 seconds
- Job status reflects real lifecycle phases: Collecting Bids -> In Progress -> Completed
- Bidding timer (15s) runs once to completion without resetting on new messages
- Payment selector shows two equal options (Stripe USD and Solana USDC) before committing to either path
- Login form renders cleanly on mobile viewport

**Should have (P1 -- significantly improves demo impression):**
- Real bid data shown during collection window (even one animated bid appearing)
- Post-payment status flow visible on marketplace in near-real-time
- Login redirects to chat screen instead of home page

**Defer (P2+ / post-hackathon):**
- Dispute resolution flow (schema exists, no UI needed for 5-minute demo)
- Multi-currency beyond USD/USDC
- OAuth/social login
- WebSocket real-time updates (polling is adequate)
- Production Stripe-to-Solana escrow bridge

### Architecture Approach

The system has three layers: a React/Next.js presentation layer, a dual API layer (Next.js routes for reads + FastAPI for writes/AI), and a data layer split between PostgreSQL (persistent) and in-memory JobBoard (transient). The critical architectural issue is dual data ownership -- Python (asyncpg) and Next.js (Prisma) both write to the same PostgreSQL tables without coordination. For hackathon scale this is acceptable because the flows are sequential in practice, but it demands careful verification that both sides use the same table and status values.

**Major components:**
1. **ChatScreen** -- user conversation hub, triggers job creation, displays bid timer, hosts payment UI
2. **Butler API (FastAPI)** -- Claude-powered chat, job posting via PostJobTool, marketplace management, agent orchestration
3. **JobBoard (in-memory singleton)** -- bid collection, winner selection, execution dispatch; writes to PostgreSQL as side effect
4. **Marketplace UI** -- polls `/api/tasks` every 5s, displays job cards with status badges; currently falls back to demo data on empty response
5. **Solana Smart Contracts** -- escrow lifecycle (`create_job` -> `fund_job` -> `release_payment`); exists but not fully wired to frontend payment flow

### Critical Pitfalls

1. **Timer resets on every re-render** -- `onComplete` is an inline arrow function recreated each render, causing `useEffect` to restart the interval. Fix: wrap callback in `useRef`, store `startedAt` as absolute timestamp, remove `onComplete` from deps.

2. **Job status mismatch between Butler backend and marketplace UI** -- Butler writes to Python-side database, marketplace reads from Prisma. Status enum values differ between the two. Fix: verify shared database table, reconcile status strings, reduce poll interval for demo.

3. **Marketplace silently shows demo data** -- when API returns empty or errors, hardcoded fake jobs are displayed with no indicator. Fix: remove demo data fallback entirely for the hackathon demo so the real pipeline is visible.

4. **Triple wallet auto-connect race condition** -- `AutoConnectDemo`, `WalletConnectButton`, and `WalletProvider.autoConnect=true` all compete to connect on mount, leaving wallet in inconsistent state. Fix: keep exactly one auto-connect mechanism, or remove all and connect only at payment time.

5. **No Stripe-to-escrow bridge** -- Stripe payment succeeds but on-chain escrow is never funded. Fix: for demo, simulate escrow funding from a pre-funded devnet wallet; be transparent about it.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Job Creation Pipeline
**Rationale:** Foundation for everything. If jobs do not appear in the database, marketplace UI shows nothing, status sync is irrelevant, and payment has nothing to pay for.
**Delivers:** Butler chat creates a job -> job appears on marketplace page within 5 seconds with correct initial status ("Collecting Bids").
**Addresses:** Bug 1 (jobs not appearing), Pitfall 2 (status mismatch), Pitfall 5 (demo data fallback)
**Avoids:** Pitfall 7 (re-render loop in fetchTasks callback -- fix useCallback deps while touching marketplace page)
**Key work:** Verify `PostJobTool.execute()` writes to `MarketplaceJob` table via Prisma-compatible schema. Remove demo data fallback. Fix `useCallback([error])` dependency issue. Store `selectedTaskId` instead of full task object.

### Phase 2: Bidding Timer Stabilization
**Rationale:** After Phase 1, jobs appear. But the 15s bid timer resetting on every message is the most visible demo bug. Quick to fix, high impact.
**Delivers:** Timer counts down from 15s exactly once, survives parent re-renders and incoming messages.
**Addresses:** Bug 2 (timer reset), Pitfall 1 (re-render timer reset), Pitfall 10 (stale closure on unmount)
**Avoids:** Over-engineering with memoization -- the fix is architectural (absolute timestamps + useRef), not React.memo.
**Key work:** Refactor `BidProgressBar` to use `startedAt` prop (absolute time), wrap `onComplete` in `useRef`, add mounted ref guard. Align `bid_window_seconds` in Python backend to 15s to match frontend timer.

### Phase 3: Job Status Sync
**Rationale:** With jobs appearing and timer working, the marketplace still shows stale statuses. Status transitions must reflect real lifecycle.
**Delivers:** Marketplace shows real-time-ish status: open -> selecting -> assigned -> in_progress -> completed. Labels match user expectations ("Collecting Bids", "In Progress", "Completed").
**Addresses:** Bug 5 (status sync), Pitfall 2 (status mismatch between backend and UI)
**Key work:** Add `prisma.marketplaceJob.update()` calls at each lifecycle transition in `butler_api.py`. Verify `/api/tasks` status mapping matches DB values. Ensure `AgentJobUpdate` rows are written for granular progress.

### Phase 4: Dual Payment (Stripe + Wallet)
**Rationale:** Requires working job pipeline (Phase 1) and status sync (Phase 3). The Stripe path already works; this adds wallet/USDC as an equal alternative. Key differentiator at a Solana hackathon.
**Delivers:** Payment method picker with two equal buttons. Stripe path unchanged. Crypto path connects wallet on demand, transfers USDC via SPL token instruction, triggers same execution endpoint on success.
**Addresses:** Bug 4 (wallet at payment only), Pitfall 4 (auto-connect race), Pitfall 6 (no crypto option), Pitfall 3 (escrow bridge gap)
**Avoids:** Building a production Stripe-to-Solana bridge -- simulate escrow funding on devnet.
**Key work:** Create `PaymentMethodPicker` component. Remove all auto-connect mechanisms. Set `autoConnect={false}` on `WalletProvider`. Wire `fund_job` contract call for USDC path. Both paths call `POST /marketplace/execute/{boardJobId}` on success.

### Phase 5: Login Screen Polish
**Rationale:** Purely cosmetic. No data flow dependencies. Lowest risk, lowest impact on core demo.
**Delivers:** Clean mobile-friendly login form, no wallet connection at login, proper input styling with focus states and mobile keyboard hints.
**Addresses:** Bug 3 (login UI polish)
**Key work:** Refine `.auth-input` CSS, add `autoComplete` and `inputMode` attributes, verify responsive layout. Redirect to chat after login instead of home page.

### Phase Ordering Rationale

- **Phases 1-3 form a data pipeline:** Job creation -> timer -> status sync. Each phase validates the previous one works correctly. Fixing them in order means each phase has a testable deliverable.
- **Phase 4 depends on Phases 1-3:** Payment needs a valid `jobId`, correct status tracking, and a working execution trigger. Building payment before the pipeline works means testing against broken infrastructure.
- **Phase 5 is independent:** Login polish can be done anytime but is last because it has zero impact on the core demo flow (create job -> bid -> pay -> execute -> see results).
- **This ordering avoids the biggest pitfall:** trying to fix payment before the data pipeline works, which leads to chasing ghost bugs where payment "fails" but the real issue is the job never reached the database.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Dual Payment):** The Solana escrow contract interface (`create_job`, `fund_job`) needs verification against actual deployed contract. The USDC SPL token transfer for devnet needs the correct mint address and ATA setup. Consider `/gsd:research-phase` for this.
- **Phase 1 (Job Pipeline):** The exact write path in `PostJobTool.execute()` and `Database` class needs tracing to confirm table compatibility between asyncpg writes and Prisma reads. However, this is codebase-specific analysis, not external research.

Phases with standard patterns (skip research-phase):
- **Phase 2 (Timer):** Well-documented React pattern (useRef for callbacks, absolute timestamps). No ambiguity.
- **Phase 3 (Status Sync):** Standard Prisma update calls + status mapping. Clear from existing code.
- **Phase 5 (Login Polish):** Standard CSS/HTML form improvements. No research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Stack is locked. All recommendations use existing dependencies. Based on direct `package.json` and codebase analysis. |
| Features | HIGH | Feature list derived from existing codebase + project requirements. External sources (Smashing Mag, UXmatters, Stripe docs) corroborate UX patterns. |
| Architecture | HIGH | Architecture mapped from direct code analysis of all relevant files. Data flows verified by tracing actual function calls. |
| Pitfalls | HIGH | All critical pitfalls verified with specific line numbers in source code. React lifecycle issues are well-documented patterns. |

**Overall confidence:** HIGH

### Gaps to Address

- **Escrow contract ABI/IDL:** The exact Anchor contract interface for `fund_job` needs verification. The contract exists but the frontend integration is incomplete. During Phase 4 planning, read the contract IDL and confirm parameter types.
- **USDC mint address on devnet:** Need to confirm which USDC mint is being used (Solana devnet has multiple test USDC tokens). Check `solanaConfig.ts` and contract initialization.
- **Backend bid_window_seconds default:** Research identified a 15s frontend vs 60s backend timer mismatch. The exact default in `JobBoard` should be confirmed and set to 15 for demo. If the backend value is configurable per-call, this is trivial; if hardcoded, it requires a code change.
- **Prisma-asyncpg table compatibility:** Both ORMs write to the same PostgreSQL. Prisma uses its own migration format. Verify that `asyncpg` raw SQL writes use column names and types matching the Prisma schema exactly (especially `status` enum values).

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all referenced source files (ChatScreen.tsx, butler_api.py, marketplace/page.tsx, api/tasks/route.ts, StripePayment.tsx, WalletConnectButton.tsx, providers.tsx, HardcodedWalletAdapter.ts, prisma/schema.prisma, job_board.py, tools.py, database.py)
- React documentation on `useEffect` dependency arrays and stale closures
- Solana wallet-adapter-react documentation on `autoConnect` behavior
- Next.js documentation on `NEXT_PUBLIC_` environment variable exposure

### Secondary (MEDIUM confidence)
- [Smashing Magazine: Designing for Agentic AI](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/) -- UX patterns for progress transparency
- [Stripe: Accept Stablecoin Payments](https://docs.stripe.com/payments/accept-stablecoin-payments) -- USDC payment integration patterns
- Stripe documentation on `ExpressCheckoutElement` integration (`elements.submit()` requirement)

### Tertiary (LOW confidence)
- Anchor contract interface assumptions -- need IDL verification during Phase 4 planning

---
*Research completed: 2026-03-14*
*Ready for roadmap: yes*
