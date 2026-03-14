# Roadmap: SOTA Hackathon Polish

## Overview

Five phases to take SOTA from "mostly working" to "flawless live demo." The phases follow the data pipeline dependency chain: jobs must appear before bidding matters, bidding must work before status sync is meaningful, the pipeline must be solid before payment makes sense, and login polish is independent cosmetic work saved for last. Every phase delivers one verifiable improvement to the end-to-end demo flow.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Job Creation Pipeline** - Jobs created via Butler chat appear on the marketplace with correct initial status (completed 2026-03-14)
- [x] **Phase 2: Bidding Timer** - 15-second bid timer runs to completion without resetting (gap closure in progress) (completed 2026-03-14)
- [ ] **Phase 3: Job Status Sync** - Marketplace shows real lifecycle statuses instead of stale or hardcoded data
- [ ] **Phase 4: Dual Payment Rails** - User chooses between Stripe (USD) and wallet (USDC) at payment time
- [ ] **Phase 5: Login Screen Polish** - Clean mobile-friendly login form

## Phase Details

### Phase 1: Job Creation Pipeline
**Goal**: Users can create a job through Butler chat and see it appear on the marketplace within seconds
**Depends on**: Nothing (first phase)
**Requirements**: JOB-01, JOB-03
**Success Criteria** (what must be TRUE):
  1. User sends a task description in Butler chat and the job appears on the marketplace page within 5 seconds
  2. Newly created jobs show "Collecting Bids" as their initial status
  3. Marketplace page shows only real jobs from the database -- no hardcoded demo data is displayed
  4. Refreshing the marketplace page still shows previously created jobs (data persists in PostgreSQL)
**Plans**: 1 plan

Plans:
- [ ] 01-01-PLAN.md -- Remove demo data, fix polling, update status label, add MarketplaceJob seeds

### Phase 2: Bidding Timer
**Goal**: The bidding countdown timer works reliably during a live demo without resetting
**Depends on**: Phase 1
**Requirements**: BID-01
**Success Criteria** (what must be TRUE):
  1. After a job is created, the 15-second bid timer counts down to zero exactly once
  2. Sending additional chat messages while the timer is running does not restart or reset the timer
  3. When the timer completes, the bid winner selection triggers automatically
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Ref-anchored timer fix + backend alignment
- [ ] 02-02-PLAN.md -- Gap closure: reset bidActiveRef on early-return paths

### Phase 3: Job Status Sync
**Goal**: Marketplace accurately reflects where each job is in its lifecycle
**Depends on**: Phase 1
**Requirements**: JOB-02
**Success Criteria** (what must be TRUE):
  1. A job transitions through visible statuses on the marketplace: Collecting Bids -> In Progress -> Completed
  2. Status changes appear on the marketplace within one polling cycle (5 seconds) of the backend state change
  3. Completed jobs show "Completed" status and remain visible on the marketplace
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

### Phase 4: Dual Payment Rails
**Goal**: Users can pay for completed work using either fiat (Stripe) or crypto (USDC) with equal ease
**Depends on**: Phase 1, Phase 3
**Requirements**: PAY-01, PAY-02
**Success Criteria** (what must be TRUE):
  1. At payment time, the user sees two equally prominent options: "Pay with Card (USD)" and "Pay with Wallet (USDC)"
  2. Selecting Stripe completes payment through the existing card flow
  3. Selecting crypto prompts wallet connection only at that moment -- no wallet popup on page load
  4. No wallet auto-connect occurs anywhere in the app until the user explicitly chooses crypto payment
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Login Screen Polish
**Goal**: The login screen looks professional and works well on mobile devices
**Depends on**: Nothing (independent)
**Requirements**: UI-01
**Success Criteria** (what must be TRUE):
  1. Login form input fields are properly styled with consistent spacing, borders, and focus states
  2. Login form renders correctly on mobile viewport (375px width) without overflow or misalignment
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Job Creation Pipeline | 1/1 | Complete    | 2026-03-14 |
| 2. Bidding Timer | 2/2 | Complete   | 2026-03-14 |
| 3. Job Status Sync | 0/? | Not started | - |
| 4. Dual Payment Rails | 0/? | Not started | - |
| 5. Login Screen Polish | 0/? | Not started | - |
