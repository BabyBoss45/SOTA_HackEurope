---
phase: 04-dual-payment-rails
plan: 02
subsystem: payments, ui
tags: [solana, spl-token, usdc, wallet-adapter, react, payment-routing]

# Dependency graph
requires:
  - phase: 04-dual-payment-rails
    plan: 01
    provides: PaymentMethodContext (stripe | usdc | null) for session-scoped payment selection
provides:
  - UsdcPayment inline chat bubble component with SPL token transfer
  - ChatScreen dual payment routing (Stripe vs USDC based on session method)
affects: [05-polish, payment integration, demo flow]

# Tech tracking
tech-stack:
  added: []
  patterns: [dual-payment-routing, spl-token-transfer-chat-bubble]

key-files:
  created:
    - mobile_frontend/src/components/UsdcPayment.tsx
  modified:
    - mobile_frontend/src/components/ChatScreen.tsx

key-decisions:
  - "Reused stripe-payment CSS classes for UsdcPayment to maintain visual consistency without new styles"
  - "Kept stripePayment state name in ChatScreen to minimize diff -- data structure is identical for both paths"
  - "Silent reset on wallet transaction rejection (no error toast) matching SendToButler.tsx pattern"

patterns-established:
  - "Dual payment routing: usePaymentMethod() in ChatScreen decides StripePayment vs UsdcPayment rendering"
  - "SPL token transfer chat bubble: same props interface as Stripe, reusable for any payment component"

requirements-completed: [PAY-01]

# Metrics
duration: 2min
completed: 2026-03-14
---

# Phase 4 Plan 2: USDC Payment Component + ChatScreen Routing Summary

**UsdcPayment SPL token transfer chat bubble with ChatScreen dual-rail routing between Stripe and USDC based on session payment method**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T13:26:19Z
- **Completed:** 2026-03-14T13:28:39Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created UsdcPayment component mirroring StripePayment interface with on-chain USDC SPL token transfer
- Wired ChatScreen to route payment rendering based on PaymentMethodContext (usdc -> UsdcPayment, stripe/null -> StripePayment)
- Both payment paths trigger task execution on success with appropriate messaging

## Task Commits

Each task was committed atomically:

1. **Task 1: Create UsdcPayment inline chat bubble component** - `2eedac0` (feat)
2. **Task 2: Wire ChatScreen to route payment by method** - `1d1fe3d` (feat)

## Files Created/Modified
- `mobile_frontend/src/components/UsdcPayment.tsx` - Inline USDC payment chat bubble with SPL token transfer, error/retry, loading states
- `mobile_frontend/src/components/ChatScreen.tsx` - Added usePaymentMethod hook and conditional UsdcPayment vs StripePayment rendering

## Decisions Made
- Reused existing `stripe-payment-container`, `stripe-pay-btn`, and `stripe-payment-success` CSS classes for UsdcPayment to maintain visual consistency
- Kept `stripePayment` state variable name in ChatScreen to minimize diff -- the data structure (jobId, amount, agentAddress, boardJobId, userId) is identical for both payment paths
- On user wallet rejection: silent reset to idle (no error callback) matching existing SendToButler.tsx behavior

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - BUTLER_ADDRESS env var already configured from prior setup. USDC payment requires user to have a connected wallet with USDC balance.

## Next Phase Readiness
- Both Stripe and USDC payment rails are now fully wired end-to-end in chat
- PAY-01 requirement satisfied: dual payment flow from gate screen through chat to payment completion
- Ready for Phase 5 polish work

---
*Phase: 04-dual-payment-rails*
*Completed: 2026-03-14*
