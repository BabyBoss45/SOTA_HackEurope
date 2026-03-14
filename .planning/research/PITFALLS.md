# Domain Pitfalls

**Domain:** AI Agent Marketplace -- hackathon polish (real-time sync, timers, dual payment, wallet flows)
**Researched:** 2026-03-14

## Critical Pitfalls

Mistakes that cause demo failures or require significant rework.

---

### Pitfall 1: Bidding Timer Resets on Every Re-render

**What goes wrong:** The `BidProgressBar` component in `ChatScreen.tsx` (line 49-98) uses `useState` for progress and `useEffect` with `Date.now()` as start time. The component's `duration` and `onComplete` are in the dependency array. If the parent re-renders and creates a new `onComplete` callback reference, the effect restarts, resetting the timer to zero. Currently `onComplete` is `() => setBidProgress(null)` -- an inline arrow function that creates a new reference on every parent render.

**Why it happens:** React re-creates inline functions on every render. When `useEffect` lists `onComplete` in its dependency array, the cleanup runs and the interval restarts from `Date.now()`. New chat messages trigger `setTranscript`, which re-renders the parent, which re-creates the callback, which kills the timer.

**Consequences:** During a live demo, every incoming message (from ElevenLabs voice, from Butler response) resets the 15-second bid countdown. The timer never completes, bids never resolve, the demo flow stalls.

**Prevention:**
1. Wrap `onComplete` in `useRef` inside `BidProgressBar` so the effect does not depend on callback identity:
   ```typescript
   const onCompleteRef = useRef(onComplete);
   onCompleteRef.current = onComplete;
   useEffect(() => {
     // ... use onCompleteRef.current instead of onComplete
   }, [duration]); // remove onComplete from deps
   ```
2. Alternatively, memoize the callback in the parent with `useCallback` and stable deps.
3. Store the `startTime` in a `useRef` rather than computing from `Date.now()` inside the effect -- this survives re-renders without resetting.

**Detection:** Test the timer while simultaneously sending a chat message. If the countdown jumps back to 15s, this pitfall is active.

**Phase:** Must fix in Phase 1 (timer/sync fixes). This is the single most visible demo bug.

**Confidence:** HIGH -- verified directly in the codebase at `ChatScreen.tsx` lines 49-67.

---

### Pitfall 2: Job Status Mismatch Between Butler Backend and Marketplace UI

**What goes wrong:** The Butler backend (Python FastAPI at `BUTLER_URL/marketplace/post`) creates and manages jobs with its own status lifecycle. The Next.js marketplace page (`app/marketplace/page.tsx`) reads from Prisma via `/api/tasks`. These are two separate data paths. A job posted through Butler may not appear on the marketplace page, or may show stale status, because:
- Butler writes to its own database/state, while `/api/tasks` reads from `prisma.marketplaceJob`
- Status values differ: Butler uses `open/selecting/assigned/completed`, the marketplace UI expects `executing/queued/completed/failed` (mapped in `api/tasks/route.ts` lines 92-111)
- The marketplace polls every 5 seconds (`setInterval(fetchTasks, 5000)` at line 260), but if Butler hasn't written to the shared Postgres yet, the job is invisible

**Why it happens:** Two separate services (Python backend, Next.js frontend) share a database but have no real-time notification channel. The 5-second polling interval creates a window where the user posts a job in the chat, switches to the marketplace tab, and sees nothing.

**Consequences:** During demo: "I just asked Butler to book a hotel... where is it on the marketplace?" The jury sees an empty marketplace or stale data.

**Prevention:**
1. After `postJobToMarketplace` succeeds in `ChatScreen.tsx`, trigger an immediate fetch on the marketplace page (e.g., via a shared event bus, `BroadcastChannel`, or simply a query param that forces refresh).
2. Reduce polling interval to 2 seconds during active demo.
3. Add an optimistic task entry to the marketplace UI immediately upon job creation, then reconcile when the backend confirms.
4. Verify that Butler's `/marketplace/post` endpoint actually writes to the same `MarketplaceJob` table that `/api/tasks` reads from.

**Detection:** Post a job via Butler chat, then immediately open the marketplace page. If the job does not appear within 2-3 seconds, this pitfall is active.

**Phase:** Phase 1 (sync fixes). Core demo flow depends on this.

**Confidence:** HIGH -- verified from two independent code paths: `ChatScreen.tsx` posts to `BUTLER_URL/marketplace/post` (Python), `api/tasks/route.ts` reads from `prisma.marketplaceJob` (Next.js).

---

### Pitfall 3: Stripe Payment Creates Intent But Never Bridges to On-Chain Escrow

**What goes wrong:** The `StripePayment` component creates a Stripe `PaymentIntent` via `/api/stripe/create-payment-intent` (which stores metadata like `jobId`, `agentAddress`, `usdcAmountRaw`). After successful payment, `onSuccess` in `ChatScreen.tsx` (line 626-643) posts to `BUTLER_URL/marketplace/execute/{boardJobId}` to trigger task execution. But there is no webhook handler that converts the Stripe payment confirmation into an on-chain escrow funding transaction. The metadata is stored but never acted upon.

**Why it happens:** The Stripe-to-Solana bridge is the hardest integration piece. It requires a webhook endpoint that listens for `payment_intent.succeeded`, reads the metadata, then uses a backend keypair to fund the on-chain escrow PDA. This was deferred as "not for hackathon" but the UI pretends it works.

**Consequences:** Two scenarios during demo:
1. If paying with Stripe: Payment succeeds in Stripe but the escrow on-chain is never funded. The Solana explorer link shows an unfunded escrow.
2. If the jury inspects the blockchain: The escrow account is empty despite the "Payment confirmed!" message.

**Prevention:**
1. For hackathon demo: Fake the escrow funding. After Stripe payment succeeds, have the backend use a pre-funded devnet wallet to fund the escrow. This is a demo-only shortcut.
2. Add a clear message: "Payment confirmed. Escrow funding simulated (devnet)." so the jury understands the architecture without expecting a real bridge.
3. Do NOT try to build a production Stripe-to-Solana bridge during the hackathon -- it requires a custodial wallet service, proper key management, and error handling that is out of scope.

**Detection:** Complete a Stripe payment and check the escrow account on Solana explorer. If it shows 0 balance, this pitfall is active.

**Phase:** Phase 2 (payment polish). Non-blocking for core demo if messaging is clear.

**Confidence:** HIGH -- verified in codebase: `create-payment-intent/route.ts` stores metadata but no webhook handler exists (checked `app/api/webhooks/` -- only `incident-io` exists).

---

### Pitfall 4: Wallet Auto-Connect Race Condition on Page Load

**What goes wrong:** Two competing auto-connect mechanisms exist:
1. `AutoConnectDemo` component in `providers.tsx` (lines 30-47) selects "Demo Wallet" and calls `connect()`
2. `WalletConnectButton` component (lines 43-52) also tries to auto-connect the demo wallet on mount
3. `WalletProvider` has `autoConnect` set to `true` (line 90)

Three independent pieces of code all trying to connect the same wallet on mount creates a race condition. If the `HardcodedWalletAdapter.connect()` is called while a previous `connect()` is still resolving (the `_connecting` flag check at line 56 is not awaited), the wallet can end up in an inconsistent state where `connected` is `true` but `publicKey` is null, or where multiple `connect` events are emitted.

**Why it happens:** The wallet adapter pattern expects one connection trigger. Having `autoConnect`, `AutoConnectDemo`, and `WalletConnectButton` all competing creates unpredictable ordering.

**Consequences:** On page load, the wallet sometimes appears connected but `publicKey` is null. When the user tries to pay, `address` is null, causing the job to be posted without `wallet_address`, and Stripe payment fails with "agentAddress must be a valid Solana address" because the fallback is `SystemProgram.programId`.

**Prevention:**
1. Remove either `AutoConnectDemo` or the auto-connect logic in `WalletConnectButton` -- keep exactly one.
2. The safest approach: keep `autoConnect={true}` on `WalletProvider` and remove both manual auto-connect mechanisms. The wallet adapter library handles this correctly when only one trigger exists.
3. Add a guard: if `connecting` is already true, skip the connect attempt.

**Detection:** Reload the page 10 times rapidly. If the wallet badge occasionally shows "No wallet connected" or the address flickers, this pitfall is active.

**Phase:** Phase 1 (wallet fixes). Affects payment flow reliability.

**Confidence:** HIGH -- three auto-connect paths verified in `providers.tsx` lines 30-47, `WalletConnectButton.tsx` lines 43-52, and `providers.tsx` line 90 (`autoConnect`).

---

## Moderate Pitfalls

### Pitfall 5: Marketplace Falls Back to Demo Data Silently

**What goes wrong:** In `app/marketplace/page.tsx` lines 233-249, if the API returns empty tasks OR throws an error, the marketplace renders hardcoded demo data (`demoTasks`). The user and jury see fake jobs with no indication they are looking at mock data. After posting a real job, the real job may appear briefly then vanish if the next poll returns empty (replaced by demo data).

**Prevention:**
1. Show a subtle indicator when displaying demo data (e.g., "Showing sample data -- no active jobs yet").
2. Merge real and demo data rather than replacing: if API returns 1 real job, show it alongside demo jobs.
3. Better: remove demo data entirely for the demo. An empty marketplace that fills up when Butler posts a job is more impressive than a pre-populated fake one.

**Detection:** Check the network tab -- if `/api/tasks` returns `{ tasks: [] }`, the UI still shows 6 jobs.

**Phase:** Phase 1 (sync fixes). Directly undermines the "real marketplace" narrative.

**Confidence:** HIGH -- verified in marketplace page source.

---

### Pitfall 6: Dual Payment UX Shows Only Stripe, Not Crypto Option

**What goes wrong:** The project requirement says "two equal options: Stripe (USD) / wallet (USDC)" but the current `ChatScreen.tsx` only triggers `StripePayment` after job posting (line 299). There is no UI for choosing to pay with the connected Solana wallet instead. The wallet is connected (for demo purposes) but never used for payment.

**Prevention:**
1. When payment is needed, show a choice card: "Pay with Card ($X.XX)" vs "Pay with USDC (X.XX USDC)".
2. For the USDC path, create a simple SPL token transfer from the connected wallet to the escrow PDA. The `HardcodedWalletAdapter` can sign this transaction.
3. Place the choice BEFORE the Stripe Elements load -- loading Stripe is slow (~1-2s) and should not block the crypto option.

**Detection:** Complete the full flow: chat -> job -> payment. If you only see Stripe and no USDC option, this pitfall is active.

**Phase:** Phase 2 (payment UX). Key differentiator for a Solana hackathon project.

**Confidence:** HIGH -- verified: no USDC payment path exists in `ChatScreen.tsx`.

---

### Pitfall 7: `fetchTasks` Callback Creates Re-render Loop Risk

**What goes wrong:** The `fetchTasks` function in `marketplace/page.tsx` line 227 is wrapped in `useCallback` with `[error]` as dependency. Inside `fetchTasks`, `setError(null)` is called. This means: fetch -> setError(null) -> error changes -> fetchTasks recreated -> useEffect re-runs -> another fetch. The `useEffect` at line 258 depends on `fetchTasks`, so every error state change triggers a new interval setup.

**Prevention:**
1. Remove `error` from `useCallback` deps. Use a ref for the error check instead.
2. Move `fetchTasks` outside the component or use a ref-based approach.
3. At minimum, verify the interval isn't being created multiple times by checking the dev console for duplicate fetch calls.

**Detection:** Open the Network tab and count `/api/tasks` calls. If you see more than one every 5 seconds, this is active.

**Phase:** Phase 1. Causes unnecessary load and potential UI jank.

**Confidence:** HIGH -- verified in source: `useCallback([error])` + `useEffect([fetchTasks])`.

---

### Pitfall 8: `HardcodedWalletAdapter` Exposes Private Key in Client Bundle

**What goes wrong:** `NEXT_PUBLIC_HARDCODED_WALLET_KEY` is a base58-encoded secret key loaded in the browser via `process.env.NEXT_PUBLIC_HARDCODED_WALLET_KEY` (HardcodedWalletAdapter.ts line 34). Any `NEXT_PUBLIC_` env var is included in the client-side JavaScript bundle. Anyone can inspect the bundle and extract the private key.

**Prevention:**
1. For hackathon demo: this is acceptable IF the wallet is devnet-only and contains only devnet SOL. Document this explicitly.
2. Do NOT fund this wallet with mainnet SOL or real USDC.
3. Add a comment in the code: `// DEMO ONLY: devnet wallet. Never use on mainnet.`
4. After the hackathon, remove this adapter entirely.

**Detection:** Search the built JS bundle for the key value.

**Phase:** Not a demo blocker but must be acknowledged. Mention to jury as "demo wallet for devnet only."

**Confidence:** HIGH -- `NEXT_PUBLIC_` prefix guarantees client-side exposure per Next.js documentation.

---

## Minor Pitfalls

### Pitfall 9: ExpressCheckoutElement Does Not Call `elements.submit()` Before Confirm

**What goes wrong:** The Stripe `ExpressCheckoutElement` (Apple Pay / Google Pay) in `StripePayment.tsx` calls `confirmPayment` directly in `handleExpressCheckout`. Per Stripe docs, `elements.submit()` must be called before `stripe.confirmPayment()` when using the `ExpressCheckoutElement`. Skipping this step can cause the payment to fail silently on some browsers/devices.

**Prevention:** Add `await elements.submit()` before `stripe.confirmPayment()` in `handleExpressCheckout`.

**Detection:** Test Apple Pay on an iPhone. If it spins and then shows "Payment failed", this is likely the cause.

**Phase:** Phase 2 (payment polish).

**Confidence:** MEDIUM -- based on Stripe documentation patterns; exact behavior depends on Stripe SDK version.

---

### Pitfall 10: Stale Closure in `onComplete` Could Fire After Unmount

**What goes wrong:** In `BidProgressBar`, if the component unmounts (e.g., user navigates away) before the interval fires `onComplete`, the cleanup function clears the interval. However, there is a small window where the interval callback reads `pct >= 100` and calls `onComplete()` in the same tick as the cleanup. This calls `setBidProgress(null)` on an unmounted parent.

**Prevention:** Use a mounted ref:
```typescript
const mountedRef = useRef(true);
useEffect(() => () => { mountedRef.current = false; }, []);
```
Check `mountedRef.current` before calling `onComplete`.

**Detection:** React strict mode in development will show "setState on unmounted component" warning.

**Phase:** Phase 1 (timer fix). Fix alongside the timer reset issue.

**Confidence:** MEDIUM -- standard React lifecycle issue.

---

### Pitfall 11: Polling Replaces Selected Task With Stale Data

**What goes wrong:** On the marketplace page, `selectedTask` stores a task object. Every 5 seconds, `fetchTasks` replaces `data` with fresh data from the API. The `selectedTask` state still holds the old object reference. If the user has expanded a task detail panel, the displayed data becomes stale while the list updates around it.

**Prevention:** Store only `selectedTaskId` instead of the full task object. Derive the selected task from `data.tasks.find(t => t.id === selectedTaskId)` on each render.

**Detection:** Open a task detail, wait 10 seconds, and compare the detail panel data with the list data.

**Phase:** Phase 1 (sync fixes). Minor UX issue.

**Confidence:** HIGH -- verified in source: `selectedTask` is stored as full object at line 193.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Timer/countdown fix | Timer restarts on parent re-render (Pitfall 1) | Use refs for callbacks and start time |
| Job status sync | Two data paths, no real-time bridge (Pitfall 2) | Verify shared database, reduce poll interval, add optimistic updates |
| Job status sync | Demo data masks missing real data (Pitfall 5) | Remove demo fallback or label it clearly |
| Stripe payment | No Stripe-to-escrow bridge (Pitfall 3) | Simulate escrow funding on devnet, be transparent |
| Stripe payment | Express checkout missing `submit()` call (Pitfall 9) | Add `elements.submit()` before confirm |
| Dual payment UX | No USDC payment option exists (Pitfall 6) | Build payment choice card before loading Stripe |
| Wallet connection | Triple auto-connect race condition (Pitfall 4) | Keep exactly one auto-connect mechanism |
| Wallet connection | Private key in client bundle (Pitfall 8) | Acceptable for devnet demo, document explicitly |
| Marketplace polling | Re-render loop from callback deps (Pitfall 7) | Remove `error` from `useCallback` deps |
| Marketplace UX | Selected task goes stale (Pitfall 11) | Store ID not object |

## Sources

- Direct codebase analysis of `ChatScreen.tsx`, `StripePayment.tsx`, `WalletConnectButton.tsx`, `providers.tsx`, `app/marketplace/page.tsx`, `api/tasks/route.ts`, `api/marketplace/execute/route.ts`, `create-payment-intent/route.ts`, `HardcodedWalletAdapter.ts`, `solanaConfig.ts`
- React documentation on `useEffect` dependency arrays and stale closures (HIGH confidence)
- Stripe documentation on `ExpressCheckoutElement` integration patterns (MEDIUM confidence)
- Solana wallet-adapter-react documentation on `autoConnect` behavior (HIGH confidence)
- Next.js documentation on `NEXT_PUBLIC_` environment variable exposure (HIGH confidence)
