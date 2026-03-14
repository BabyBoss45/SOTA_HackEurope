# Technology Stack

**Project:** SOTA AI Agent Marketplace -- Hackathon Polish
**Researched:** 2026-03-14
**Context:** Bug fixes and UX polish for 5 specific issues. Stack is LOCKED -- no framework changes, only fix patterns within existing tech.

## Current Stack (Locked -- Do Not Change)

| Layer | Technology | Version | Status |
|-------|-----------|---------|--------|
| Frontend | Next.js | 16.1.6 (main) / 15.5.7 (mobile) | Locked |
| UI | React 19 + Tailwind 4 + Framer Motion | 19.2.x | Locked |
| Backend API | FastAPI (Python 3.12) | 0.115.0+ | Locked |
| ORM | Prisma | 6.19.2 | Locked |
| Database | PostgreSQL | 13+ | Locked |
| Blockchain | Solana + Anchor | web3.js 1.98.4 | Locked |
| Payments | Stripe | 20.3.1 | Locked |
| State Mgmt | @tanstack/react-query | 5.62-5.90 | Locked |
| Wallet | @solana/wallet-adapter-react | 0.15.39 | Locked |
| Validation | Zod (TS) + Pydantic (Python) | 3.24+ / 2.9+ | Locked |

## Bug-Specific Stack Recommendations

These are not new dependencies -- they are patterns and correct usage of existing libraries to fix the 5 demo-critical bugs.

---

### Bug 1: Jobs Created via Butler Not Appearing on Marketplace

**Root cause analysis:** The marketplace page (`app/marketplace/page.tsx`) polls `/api/tasks` every 5 seconds via `setInterval`. The Butler backend posts jobs to its in-memory marketplace hub AND writes to PostgreSQL via Prisma (`MarketplaceJob` model). The `/api/tasks` route reads from Prisma. The likely issue is either: (a) the Butler backend writes to its in-memory hub but fails to persist to Postgres, or (b) the status mapping in `/api/tasks/route.ts` filters out newly created jobs.

**Pattern to use:** No new libraries needed. Fix the data flow:

| What | How | Confidence |
|------|-----|------------|
| Verify Prisma write in `butler_api.py` `marketplace/post` | Ensure `MarketplaceJob.create()` fires after hub job creation | HIGH |
| Polling interval (5s) is adequate for demo | Keep `setInterval(fetchTasks, 5000)` as-is | HIGH |
| Do NOT add WebSockets for this | Polling is simpler, demo-reliable, already working | HIGH |
| Use `@tanstack/react-query` `refetchInterval` instead of raw `setInterval` | Already in the project but not used on marketplace page -- would give automatic cache invalidation, dedup, and stale-while-revalidate | MEDIUM |

**Recommended approach:** Trace the `POST /api/v1/marketplace/post` handler in `butler_api.py` to confirm it calls `prisma.marketplaceJob.create()`. If it only writes to the in-memory `JobBoard`, add the Prisma persist step. The frontend polling is fine.

**If switching to react-query (optional but cleaner):**
```typescript
// Already installed: @tanstack/react-query 5.x
import { useQuery } from "@tanstack/react-query";

const { data } = useQuery({
  queryKey: ["marketplace-tasks"],
  queryFn: () => fetch("/api/tasks").then(r => r.json()),
  refetchInterval: 5000,
  staleTime: 2000,
});
```

---

### Bug 2: Bidding Timer (15s) Resets on New Messages

**Root cause analysis:** `BidProgressBar` in `ChatScreen.tsx` uses `useEffect` with `[duration, onComplete]` as dependencies. The `onComplete` callback is `() => setBidProgress(null)` which is stable. However, the component is wrapped in `<AnimatePresence>` and conditionally rendered via `bidProgress?.active`. If any parent re-render causes `bidProgress` state to be re-set (e.g., a new message triggers state update that cascades), the component unmounts/remounts and the timer resets.

**Pattern to use:**

| What | How | Confidence |
|------|-----|------------|
| Store bid start time as `Date.now()` in state, not just `{ active, duration }` | `setBidProgress({ active: true, duration: 15, startedAt: Date.now() })` | HIGH |
| Pass `startedAt` as prop to `BidProgressBar` | Component calculates elapsed from absolute time, survives re-renders | HIGH |
| Stabilize `onComplete` with `useRef` | Prevent re-render cycles from dependency changes | HIGH |
| Do NOT use `useMemo`/`useCallback` wrapping for this | The fix is architectural (absolute time), not memoization | HIGH |

**Key code pattern:**
```typescript
// In BidProgressBar, use startedAt instead of relative timing
function BidProgressBar({ duration, startedAt, onComplete }) {
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      // ... progress calculation
      if (elapsed >= duration) {
        clearInterval(interval);
        onCompleteRef.current?.();
      }
    }, 100);
    return () => clearInterval(interval);
  }, [duration, startedAt]); // stable deps, no reset
}
```

---

### Bug 3: Login Screen UI Polish (Mobile)

**Root cause analysis:** `AuthScreen.tsx` uses inline Tailwind classes and CSS custom properties (`var(--text-muted)`, `var(--accent)`, `var(--red)`). The form inputs use a `.auth-input` CSS class. The layout is `flex flex-1 items-center justify-center px-6` which should center properly. Issues are likely: inconsistent input styling, missing focus states, or spacing problems.

**Pattern to use:**

| What | How | Confidence |
|------|-----|------------|
| Use existing `.auth-input` class in `globals.css` | Standardize padding, border-radius, focus ring | HIGH |
| Framer Motion `motion.input` for name field animation | Already used correctly with `AnimatePresence mode="wait"` | HIGH |
| Add `autoComplete` attributes to inputs | `autoComplete="email"` and `autoComplete="current-password"` for mobile keyboard hints | HIGH |
| Use `inputMode="email"` on email field | Shows email keyboard on mobile | HIGH |
| Do NOT add a form library (react-hook-form, formik) | Overkill for 2-3 fields, existing useState pattern is fine | HIGH |

**CSS polish checklist (use existing Tailwind + CSS vars):**
```css
/* In globals.css -- refine .auth-input */
.auth-input {
  width: 100%;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.auth-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}
.auth-input::placeholder {
  color: var(--text-muted);
}
```

---

### Bug 4: Wallet Connection Only at Payment, Dual Stripe/USDC Options

**Root cause analysis:** Currently `WalletConnectButton.tsx` auto-connects a demo wallet on mount and renders a wallet selection list. The requirement is: wallet should NOT connect at login -- only when the user chooses to pay with crypto. Payment UI should show two equal options: Stripe (USD) and Wallet (USDC).

**Pattern to use:**

| What | How | Confidence |
|------|-----|------------|
| Remove auto-connect from `WalletConnectButton` | Delete the `useEffect` that calls `handleConnect(demoWallet)` on mount | HIGH |
| Create a `PaymentMethodPicker` component | Two equal buttons: "Pay with Card (USD)" and "Pay with Crypto (USDC)" | HIGH |
| Stripe path: use existing `StripePayment` component as-is | Already works with `ExpressCheckoutElement` + `PaymentElement` | HIGH |
| Crypto path: trigger wallet connect only when user picks USDC | Use `useWallet().select()` + `connect()` on demand, then SPL token transfer | HIGH |
| Use `@solana/spl-token` (already installed v0.4.14) for USDC transfer | `createTransferInstruction` for SPL token transfers | HIGH |
| Do NOT use `@solana/pay` | Adds complexity, not needed for direct escrow funding | HIGH |
| Keep `WalletModalProvider` in providers but remove auto-connect logic | `autoConnect: false` in `WalletProvider` config | HIGH |

**Payment picker pattern:**
```typescript
// New component: PaymentMethodPicker
function PaymentMethodPicker({ jobId, amount, agentAddress, onComplete }) {
  const [method, setMethod] = useState<"choose" | "stripe" | "crypto">("choose");

  if (method === "choose") {
    return (
      <div className="payment-options">
        <button onClick={() => setMethod("stripe")}>
          Pay ${amount} USD (Card / Apple Pay)
        </button>
        <button onClick={() => setMethod("crypto")}>
          Pay {amount} USDC (Solana Wallet)
        </button>
      </div>
    );
  }
  if (method === "stripe") return <StripePayment {...props} />;
  if (method === "crypto") return <CryptoPayment {...props} />;
}
```

---

### Bug 5: Job Status Sync on Marketplace (Collecting Bids -> In Progress -> Completed)

**Root cause analysis:** The `/api/tasks/route.ts` maps `MarketplaceJob.status` to dashboard statuses. The status field values are: `open`, `selecting`, `assigned`, `completed`, `expired`, `cancelled`. The mapping already handles these. The issue is likely that `butler_api.py` does not update `MarketplaceJob.status` when the job transitions (e.g., after bid selection, after agent execution, after completion).

**Pattern to use:**

| What | How | Confidence |
|------|-----|------------|
| Add status update calls in `butler_api.py` at each lifecycle point | `prisma.marketplaceJob.update({ where: { jobId }, data: { status: "assigned" } })` | HIGH |
| Map lifecycle events to frontend labels | `open` = "Collecting Bids", `assigned` = "In Progress", `completed` = "Completed" | HIGH |
| Use `AgentJobUpdate` model for granular progress | Already exists, write updates at each stage | HIGH |
| Polling (5s) is sufficient for demo | Status transitions happen on the order of seconds-minutes | HIGH |
| Do NOT add SSE/WebSocket for status updates | Polling is simpler, demo-reliable, and the interval is already fast enough | HIGH |

**Status mapping for UI labels:**
```typescript
const STATUS_LABELS: Record<string, string> = {
  open: "Collecting Bids",
  selecting: "Selecting Agent",
  assigned: "In Progress",
  completed: "Completed",
  expired: "Expired",
  cancelled: "Cancelled",
};
```

---

## Alternatives Considered (and Rejected)

| Category | Considered | Why Rejected |
|----------|-----------|--------------|
| Real-time updates | WebSocket / SSE from FastAPI | Overkill for 5s polling at hackathon scale. Adds connection management complexity. Polling already works. |
| Form library | react-hook-form | Only 2-3 inputs on login screen. useState is adequate. Adding a library for this is over-engineering. |
| Payment SDK | @solana/pay | Designed for merchant point-of-sale, not escrow funding. Direct SPL token transfer via existing `@solana/spl-token` is simpler. |
| State management | Zustand / Jotai for global job state | @tanstack/react-query already installed and handles server state. No need for another state lib. |
| Timer library | use-timer / react-countdown | The timer bug is architectural (relative vs absolute time), not a missing library. |

## Libraries Already Installed -- Use These

These are in the project but underutilized for the bugs at hand:

| Library | Current Use | Should Also Use For |
|---------|-------------|-------------------|
| `@tanstack/react-query` 5.x | Possibly unused on marketplace page | Marketplace data fetching with `refetchInterval` (cleaner than raw `setInterval`) |
| `@solana/spl-token` 0.4.14 | Imported but crypto payment path may be incomplete | USDC transfer for the crypto payment option |
| `zod` 3.24+ | Schema validation | Login form validation (optional, forms are simple enough without) |
| `framer-motion` / `motion/react` 12.x | Animations throughout | Payment method picker transitions |

## What NOT to Install

| Library | Why Not |
|---------|---------|
| `socket.io` / `ws` (client) | No WebSocket needed. 5s polling is fine for hackathon demo. |
| `react-hook-form` | 2 input fields. useState works. |
| `zustand` / `jotai` / `recoil` | react-query handles server state. No complex client state needed. |
| `@solana/pay` | Wrong abstraction for escrow funding. |
| `swr` | react-query already installed and is more feature-rich. |
| `pusher` / `ably` | Real-time push is overkill. Polling works. |

## Installation

No new packages required. All fixes use existing dependencies:

```bash
# Nothing to install. All libraries are already in package.json.
# The fixes are code-level changes, not dependency changes.
```

## Key Version Notes

| Package | Installed | Notes |
|---------|-----------|-------|
| `@tanstack/react-query` | 5.62-5.90 | v5 API uses `useQuery({ queryKey, queryFn })` syntax (not v4 `useQuery(key, fn)`) |
| `@stripe/react-stripe-js` | 5.6.0 | Supports `ExpressCheckoutElement` for Apple Pay/Google Pay (already used) |
| `@solana/wallet-adapter-react` | 0.15.39 | `autoConnect` prop on `WalletProvider` controls auto-connection behavior |
| `framer-motion` | 12.x | Note: mobile_frontend imports from `motion/react`, main app from `framer-motion` -- both work but are different import paths for v12 |
| `prisma` | 6.19.2 | Supports `findMany`, `create`, `update` -- all needed for job lifecycle |

## Sources

- Codebase analysis: `app/marketplace/page.tsx`, `app/api/tasks/route.ts`, `mobile_frontend/src/components/ChatScreen.tsx`, `mobile_frontend/src/components/AuthScreen.tsx`, `mobile_frontend/src/components/WalletConnectButton.tsx`, `mobile_frontend/src/components/StripePayment.tsx`, `agents/butler_api.py`, `prisma/schema.prisma`
- Confidence level: HIGH -- all recommendations based on direct code analysis of existing codebase, no external sources needed since stack is locked
