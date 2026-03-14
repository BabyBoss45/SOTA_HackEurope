# Feature Research

**Domain:** AI Agent Marketplace (task bidding, execution, payment) -- hackathon demo polish
**Researched:** 2026-03-14
**Confidence:** HIGH (based on existing codebase analysis + industry patterns)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or broken during demo.

#### Job Status Tracking

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Distinct visual status badges per job phase | Every marketplace (Uber, Fiverr, Upwork) shows clear status. Jury expects it. | LOW | Already have `StatusBadge` component and status field in `MarketplaceJob` schema (`open`, `selecting`, `assigned`, `completed`, `expired`, `cancelled`). Issue: marketplace UI shows `executing/queued/completed/failed` which does not match DB states. Must reconcile. |
| Linear progress pipeline (e.g. Collecting Bids -> Agent Selected -> In Progress -> Done) | Users need to see WHERE they are in the flow, not just a label | MEDIUM | The `stages` array exists on `Task` interface in marketplace page but is hardcoded in demo data. Real jobs from API do not populate stages. Wire real status transitions into the stage pipeline. |
| Auto-refresh / live updates on marketplace page | Stale data = broken demo. Jobs created in chat must appear on marketplace without manual reload. | LOW | Polling already exists (`fetchData` on interval). Verify interval is short enough (5-10s for demo). WebSocket would be ideal but overkill for hackathon. |
| Toast/notification when job status changes | User needs confirmation their action had effect, especially after payment | LOW | `showToast` already exists and is used. Ensure it fires on every meaningful state change. |

#### Bidding Timer

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Visible countdown timer showing time remaining for bids | Any auction/bidding system shows a countdown. Without it users have no idea what is happening. | LOW | `BidProgressBar` component exists in `ChatScreen.tsx` with 15s duration. Works correctly in chat. |
| Timer must not reset on unrelated UI events | Timer resetting = confusion and broken trust. Users lose track of where they are. | LOW | Currently `setBidProgress({ active: true, duration: 15 })` is called once in `postJobToMarketplace`. Verify no re-renders reset the `startTime` in the `useEffect`. The component re-creates interval on mount which is correct, but parent re-renders could unmount/remount it. Wrap in `React.memo` or stabilize. |
| Clear "collecting bids" messaging | User must understand what is happening: agents are competing for the job | LOW | Already says "Let me find the best specialist for your request..." -- good. |

#### Payment Flow

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Two equal payment options: Stripe USD and crypto USDC | Project requirement. Jury expects both to work. Currently Stripe dominates and crypto is secondary. | MEDIUM | `StripePayment` component exists with Apple Pay + card. Crypto path exists (`transferFunds` tool) but is not presented as equal choice at payment time. Need a payment method selector BEFORE showing Stripe or wallet flow. |
| Payment confirmation with clear amount | Users must know what they are paying before they pay | LOW | Already shows `$X.XX USDC` in Stripe header. Ensure same clarity for crypto path. |
| Post-payment status feedback | "Payment confirmed -> Agent working -> Result delivered" must be visible | LOW | `onSuccess` callback already adds transcript line and triggers execution. Verify it works end-to-end. |

#### Login / Auth

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Clean email/password form with proper validation | Any app has this. Sloppy login = instant credibility hit with jury. | LOW | Login page exists at `/app/login/page.tsx` with email+password, sign-in/sign-up toggle, proper validation. Already well-structured with icons, labels, focus rings. |
| Loading states on form submission | Prevents double-submit, shows responsiveness | LOW | Already has `loading` state with `Loader2` spinner. Done. |
| Error messages inline (not alerts) | Modern UX expectation | LOW | Already renders error in styled div below form. Done. |
| Redirect after login | User should land somewhere useful | LOW | Already `router.push("/")` after sign-in. Consider redirecting to chat instead. |

### Differentiators (Competitive Advantage)

Features that make SOTA stand out in a hackathon demo. Not expected, but impress judges.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Voice-first task submission (ElevenLabs orb) | Most AI marketplaces are text-only. Voice creates "wow" moment for demo. | ALREADY BUILT | `AgentOrb` + ElevenLabs integration working. This is SOTA's strongest differentiator. Protect it -- do not break it during polish. |
| Real-time agent bidding visualization | Showing agents competing in real-time (bids appearing with price, reputation, ETA) is highly visual and memorable. Aligns with "Confidence Signal" pattern from agentic AI UX. | MEDIUM | Bid data structure exists (`Bid` interface with agent, price, reputation, eta). Currently only shown in demo data. Wire real bid WebSocket events into the marketplace orderbook view. Even 2-3 animated bids appearing during demo would be impressive. |
| Orderbook-style marketplace view | Financial trading metaphor makes the marketplace feel sophisticated and different from Fiverr/Upwork list views | ALREADY BUILT | `viewMode: "orderbook"` option exists. Unique visual identity. |
| On-chain escrow with Solana | Trustless payment via smart contract escrow. Jury at a blockchain hackathon expects this to actually work. | ALREADY BUILT | Anchor contracts exist. Stripe bridges fiat to on-chain escrow. Verify the bridge actually funds escrow on-chain after Stripe payment. |
| Agent reputation scores visible | Transparency into agent quality builds trust. Aligns with "Trust Calibration" pattern. | LOW | `reputation` field exists on `Agent`, `WorkerAgent`, `ExternalAgent` models. Already rendered as star ratings in marketplace UI. Ensure real data populates this. |
| Inline task results in chat | Seeing results delivered directly in conversation (not redirecting to another page) is seamless UX | ALREADY BUILT | `addLine("assistant", data.formatted_results)` after execution. Natural chat flow. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but would hurt the hackathon demo or create unnecessary complexity.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Wallet connection at login | "Web3 app should require wallet" | Scares away non-crypto users immediately. PROJECT.md explicitly says wallet only at payment time. Jury may not have Phantom installed. | Defer wallet prompt to payment step. Offer Stripe as frictionless default. |
| Complex multi-step job creation wizard | "Users need to specify details" | Kills the conversational UX that is SOTA's differentiator. Butler should extract details naturally via chat. | Keep Butler as the sole job creation interface. No forms. |
| Real-time WebSocket for everything | "Everything should update instantly" | WebSocket complexity = more bugs during demo. Current polling works fine for the 1-3 jobs in a demo scenario. | Polling every 5s for marketplace. WebSocket only for agent hub (already exists). |
| Full dispute resolution flow | "Marketplace needs dispute handling" | Too complex for hackathon. No one will dispute during a 5-minute demo. Schema exists but UI is unnecessary. | Show dispute model in schema as "future feature" during presentation if asked. |
| Multiple payment currencies beyond USD/USDC | "Support ETH, SOL, BTC" | Doubles payment complexity. USDC is the stablecoin standard on Solana. USD covers fiat. Two options is the sweet spot. | Stick to Stripe USD + USDC on Solana. Period. |
| OAuth/social login (Google, GitHub) | "Everyone has social login" | Adds auth provider dependency, more failure points during demo. Email/password is reliable and fast. | Email/password with clean UX. Wallet connect only for payment. |

## Feature Dependencies

```
[Butler Chat] ──creates──> [Marketplace Job]
    |                           |
    |                    [Bid Collection Timer]
    |                           |
    |                    [Agent Selection]
    |                           |
    └──triggers──────> [Payment Selector]
                           /        \
                    [Stripe USD]  [Crypto USDC]
                           \        /
                        [Escrow Funded]
                              |
                       [Task Execution]
                              |
                       [Results in Chat]
                              |
                    [Marketplace Status Updated]
```

### Dependency Notes

- **Butler Chat creates Marketplace Job:** `postJobToMarketplace()` in ChatScreen posts to `/marketplace/post`. This is the entry point. If this breaks, nothing else works.
- **Bid Timer requires Job to exist:** Timer starts via `setBidProgress` immediately after posting. Must not fire if post fails.
- **Payment Selector requires Agent Selection:** Payment only makes sense after a winning bid is chosen. Currently auto-selected by backend.
- **Stripe USD and Crypto USDC are parallel paths:** User picks one. Must not require both. Currently Stripe is hardcoded as the path; crypto path needs equal UX treatment.
- **Escrow funding requires payment completion:** `onSuccess` callback triggers execution. Both paths must call the same `onSuccess`.
- **Marketplace Status sync requires job ID mapping:** Chat creates jobs via Butler API, marketplace reads from `/api/agents/dashboard`. These must use the same job IDs.

## MVP Definition (Hackathon Demo)

### Must Fix for Demo (P0)

- [x] Butler chat creates jobs that appear on marketplace -- verify data flow
- [ ] Job status on marketplace reflects real phases (open -> selecting -> assigned -> completed) not just hardcoded demo data
- [ ] Bidding timer (15s) runs once without resetting on re-renders or new chat messages
- [ ] Payment selector shows two equal options: "Pay with Card ($X.XX)" and "Pay with USDC ($X.XX)" before committing to either path
- [ ] Login form renders cleanly on mobile viewport (currently desktop-optimized, verify responsive behavior)

### Should Fix if Time Allows (P1)

- [ ] Real bid data shown during collection window (even one real bid appearing animated)
- [ ] Marketplace auto-refreshes within 5s of job creation (verify polling interval)
- [ ] After payment, marketplace job status updates to "in_progress" then "completed" in real time
- [ ] Login redirects to chat screen (not home page) for faster demo flow

### Nice to Have (P2)

- [ ] Confidence scores from agents shown during bid phase
- [ ] Transaction explorer link shown after crypto payment
- [ ] Job detail modal on marketplace shows full stage pipeline

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Job status sync (real DB states -> UI) | HIGH | MEDIUM | P0 |
| Stable bidding timer (no reset bug) | HIGH | LOW | P0 |
| Dual payment selector (Stripe + USDC equal) | HIGH | MEDIUM | P0 |
| Login form mobile polish | MEDIUM | LOW | P0 |
| Real bid visualization | HIGH | MEDIUM | P1 |
| Marketplace auto-refresh timing | MEDIUM | LOW | P1 |
| Post-payment status flow | HIGH | LOW | P1 |
| Chat-to-marketplace job ID sync | HIGH | MEDIUM | P0 |

**Priority key:**
- P0: Must work flawlessly for live demo
- P1: Significantly improves demo impression
- P2: Nice polish, skip if time is short

## Competitor Feature Analysis

| Feature | Fiverr/Upwork | AutoGPT/CrewAI | SOTA Approach |
|---------|---------------|-----------------|---------------|
| Job creation | Form-based wizard | Code/prompt config | Conversational via Butler (differentiator) |
| Agent selection | Manual browse + hire | Automatic orchestration | Competitive bidding with timer (unique) |
| Status tracking | Linear pipeline (ordered -> in progress -> delivered -> reviewed) | Logs/terminal output | Marketplace orderbook + chat inline updates |
| Payment | Stripe only (fiat) | Free/self-hosted | Dual: Stripe USD + Solana USDC (differentiator) |
| Results delivery | Separate delivery page | File output / API response | Inline in chat conversation (differentiator) |
| Login | Email + social OAuth | API keys / no auth | Email/password, wallet only at payment |

## Sources

- [Smashing Magazine: Designing for Agentic AI](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/) -- UX patterns for progress, transparency, escalation, intent preview
- [UXmatters: Designing for Autonomy](https://www.uxmatters.com/mt/archives/2025/12/designing-for-autonomy-ux-principles-for-agentic-ai.php) -- Trust calibration, progressive autonomy
- [Stripe: Accept Stablecoin Payments](https://docs.stripe.com/payments/accept-stablecoin-payments) -- USDC payment integration via Stripe itself (1.5% fee vs 2.9% for cards)
- [Stripe: Stablecoin Payments](https://docs.stripe.com/payments/stablecoin-payments) -- Same checkout for fiat + crypto
- [UXPilot: Glassmorphism Best Practices](https://uxpilot.ai/blogs/glassmorphism-ui) -- Glass design restraint, readability on dark themes
- [Prototypr: Expressing Time in UI](https://blog.prototypr.io/expressing-time-in-ui-ux-design-5-rules-and-a-few-other-things-eda5531a41a7) -- Countdown timer UX principles
- [FasterCapital: Auction Countdown Timers](https://fastercapital.com/topics/utilizing-auction-countdown-timers.html) -- Bidding timer best practices
- Codebase analysis: `app/marketplace/page.tsx`, `mobile_frontend/src/components/ChatScreen.tsx`, `mobile_frontend/src/components/StripePayment.tsx`, `app/login/page.tsx`, `prisma/schema.prisma`

---
*Feature research for: SOTA AI Agent Marketplace hackathon demo polish*
*Researched: 2026-03-14*
