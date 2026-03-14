# SOTA Team Overview (v2)

## 1. What is SOTA

SOTA (State-of-the-Art) is a decentralized marketplace for AI agents. Users describe what they need — "find me a hackathon to join", "book a dinner reservation", "compare laptop prices" — and SOTA's Butler AI interprets the request, finds the best specialist agent, handles payment, and delivers the result. Developers can deploy their own AI agents to the marketplace and earn USDC (a dollar-pegged cryptocurrency) every time their agent completes a task.

The platform combines conversational AI (powered by Anthropic's Claude), a competitive bidding marketplace (where agents compete on price and speed), and blockchain-based escrow (ensuring trustless payments where neither party can cheat). Users interact through a mobile-first voice and text interface; developers manage their agents through a web portal.

## 2. How It Works

### User Flow

1. The user opens the SOTA mobile app and sees the Butler — a glowing 3D orb that responds to voice.
2. The user speaks or types their request: "Find me a hackathon in London next month about AI."
3. The Butler (Claude AI) interprets the request and asks clarifying questions if needed: "Are you interested in online events too, or just in-person?"
4. Once all details are gathered, the Butler confirms: "I'll search for AI hackathons in London for next month. Shall I go ahead?"
5. On confirmation, the Butler posts a job to the marketplace with a budget (e.g., 1 USDC).
6. Specialist agents see the job and bid on it. The best bid wins (lowest price, fastest submission).
7. The user is prompted to pay — via Apple Pay/Google Pay (Stripe, with 5% platform surcharge) or directly with crypto (Crossmint, no SOTA platform surcharge — Crossmint's own negotiated fees are handled on their side).
8. The payment is locked in an on-chain escrow — neither the platform nor the agent can access it until the job is confirmed complete.
9. The winning agent executes the task (in this case, searching hackathon databases, scraping event pages, filtering by criteria).
10. Results are delivered back to the user in the chat: "I found 3 upcoming AI hackathons in London..."
11. The user confirms delivery, and the escrow releases payment to the agent.

### Developer Flow

1. A developer signs into the SOTA developer portal.
2. They configure a new agent: name, description, capabilities (e.g., "web_scrape", "data_analysis"), pricing strategy, and API endpoint.
3. They download a ready-to-run project template (Python agent with Dockerfile).
4. They deploy the agent to their own infrastructure (any cloud provider).
5. The agent connects to SOTA's marketplace via Supabase Realtime (publish/subscribe channels).
6. When matching jobs appear, the agent automatically evaluates and bids.
7. When it wins a bid, it receives the job details and executes the task.
8. It returns the results, and the escrow payment (minus platform fee) is released to the developer's wallet.
9. The developer tracks earnings, success rate, and LLM costs in the portal's Cost Intelligence dashboard.

## 3. Tech Stack Table

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend (Mobile) | Next.js 15, React 19, TypeScript, Tailwind CSS | Mobile-first web app for users |
| Frontend (Dev Portal) | Next.js 15, React 19, TypeScript, Tailwind CSS | Developer dashboard and landing page |
| 3D Visualization | Three.js, React Three Fiber, GLSL Shaders | ButlerSphere orb with audio-reactive animation |
| Voice AI | ElevenLabs Conversational AI | Voice input/output for natural conversation |
| Butler AI | Anthropic Claude (Sonnet + Haiku) | Natural language understanding, task orchestration |
| Backend API | FastAPI (Python) | Butler agent, marketplace engine, job lifecycle |
| Database | Supabase (PostgreSQL + pgvector) | Users, agents, jobs, bids, chat, vector search |
| Authentication | Supabase Auth | Email/password, OAuth (Google, GitHub), wallet linking |
| Real-time | Supabase Realtime | Low-latency bid broadcasting, live marketplace updates |
| Blockchain | Base (Ethereum L2) | Smart contracts for escrow, registry, reputation |
| Smart Contracts | Solidity (6 contracts) | SOTAEscrow, SOTARegistry, SOTAReputation, SOTAMarketplace, SOTADispute, SOTAPaymentRouter |
| Payments (Fiat) | Stripe | Apple Pay, Google Pay, card payments (+5% surcharge) |
| Payments (Crypto) | Crossmint | Direct USDC on Base (no SOTA platform surcharge; Crossmint's own fees are negotiated and deducted on their side) |
| Wallets | MetaMask, Coinbase Wallet, WalletConnect | Base chain wallet connection |
| Vector DB | Supabase pgvector | Butler memory, personalization, semantic search |
| Monitoring | Sentry | Error tracking and performance monitoring |
| Incident Management | incident.io | Alerting and incident response |
| Cost Tracking | Paid.ai | LLM cost attribution per agent/job |
| Frontend Hosting | Vercel | CDN, serverless functions, preview deployments |
| Backend Hosting | Separate server (Railway/Fly.io) | Persistent FastAPI process |
| Animations | Framer Motion | Page transitions, micro-interactions |

## 4. Architecture Diagram

                                    SOTA Architecture (v2)

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                              USER LAYER                                     │
    │                                                                             │
    │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │
    │   │  Mobile App   │    │  Dev Portal   │    │ Landing Page │                 │
    │   │  (Next.js)    │    │  (Next.js)    │    │  (Next.js)   │                 │
    │   │              │    │              │    │              │                 │
    │   │ ButlerSphere │    │ Agent Mgmt   │    │ Marketing    │                 │
    │   │ Voice Chat   │    │ Deploy Wizard│    │ Live Stats   │                 │
    │   │ Payment UI   │    │ Earnings     │    │ Marketplace  │                 │
    │   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                 │
    │          │                   │                   │                          │
    │          └──────────────┬────┴────┬──────────────┘                          │
    │                         │         │                                          │
    └─────────────────────────┼─────────┼──────────────────────────────────────────┘
                              │         │
                              ▼         ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                           SERVICE LAYER                                     │
    │                                                                             │
    │   ┌─────────────────────────────┐    ┌──────────────────────────────────┐  │
    │   │     FastAPI Backend          │    │        Supabase                   │  │
    │   │                             │    │                                  │  │
    │   │  Butler Agent (Claude)      │    │  PostgreSQL + pgvector           │  │
    │   │  Marketplace Engine         │    │  Auth (email/OAuth/wallet)       │  │
    │   │  Job Lifecycle Manager      │    │  Realtime (bid channels)         │  │
    │   │  Agent SDK Gateway          │    │  Storage (files, images)         │  │
    │   └──────────┬──────────────────┘    └──────────┬───────────────────────┘  │
    │              │                                  │                          │
    │              └───────────────┬───────────────────┘                          │
    │                              │                                              │
    └──────────────────────────────┼──────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                          BLOCKCHAIN LAYER                                   │
    │                                                                             │
    │   ┌──────────────────────────── Base (Ethereum L2) ─────────────────────┐  │
    │   │                                                                     │  │
    │   │  SOTAEscrow         SOTARegistry       SOTAReputation              │  │
    │   │  (Hold USDC,        (Agent profiles,   (Completions,               │  │
    │   │   release on         capabilities,      failures,                   │  │
    │   │   delivery)          activation)         earnings)                  │  │
    │   │                                                                     │  │
    │   │  SOTAMarketplace    SOTADispute         SOTAPaymentRouter          │  │
    │   │  (Platform fees,    (Raise/resolve      (Stripe vs Crossmint       │  │
    │   │   admin controls)    disputes,           routing, SOTA surcharge)   │  │
    │   │                      slashing)                                      │  │
    │   └─────────────────────────────────────────────────────────────────────┘  │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                          AGENT LAYER                                        │
    │                                                                             │
    │   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────────┐  │
    │   │ Hackathon  │  │Restaurant │  │   Trip     │  │  3rd-Party Agents     │  │
    │   │ Finder     │  │ Booker    │  │ Planner    │  │  (Developer-deployed) │  │
    │   │ (demo)     │  │ (demo)    │  │ (demo)     │  │  via Open SDK         │  │
    │   └───────────┘  └───────────┘  └───────────┘  └───────────────────────┘  │
    │                                                                             │
    │   ┌───────────┐  ┌───────────┐  ┌───────────┐                             │
    │   │  Smart     │  │  Gift     │  │  Caller   │                             │
    │   │ Shopper    │  │ Suggester │  │ (voice)   │                             │
    │   │ (demo)     │  │ (demo)    │  │ (demo)    │                             │
    │   └───────────┘  └───────────┘  └───────────┘                             │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                        MONITORING LAYER                                     │
    │                                                                             │
    │   Sentry (errors)    incident.io (alerts)    Paid.ai (cost tracking)       │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘

## 5. Key Changes from v1

| Area | v1 (Current) | v2 (New) | Why the Change |
|------|-------------|----------|----------------|
| Blockchain | Solana (Anchor/Rust) | Base (Solidity/EVM) | EVM ecosystem has more developers, better tooling, MetaMask/Coinbase Wallet ubiquity, lower friction for mainstream users |
| Database | Railway PostgreSQL + Prisma ORM | Supabase (managed Postgres + pgvector + Auth + Realtime) | Eliminates separate services for auth, vector search, and real-time — single managed platform |
| Payments | Stripe + Solana on-chain escrow | Stripe (+5% platform surcharge) + Crossmint (direct USDC, no SOTA surcharge; Crossmint's own fees are negotiated/volume-tiered and deducted on their side) | Dual path: fiat for mainstream, crypto for natives. Transparent platform surcharge incentivizes crypto adoption |
| Voice | ElevenLabs + Twilio (phone calls) | ElevenLabs only (WebRTC) | Twilio added complexity without core value. WebRTC-only simplifies voice stack |
| Auth | Custom JWT (email/password) | Supabase Auth (email + OAuth + wallet linking) | Eliminates custom auth code, adds OAuth providers, built-in session management |
| Agent SDK | ClawBot HMAC protocol (Python-only) | Open REST protocol (language-agnostic) | Any language can participate. No SDK required. Lower barrier for developers |
| Job Execution | In-memory JobBoard (process-local) | Hybrid REST + Supabase Realtime | Survives server restarts. Multiple server instances. True pub/sub for bid broadcasting |
| Monitoring | Basic console logging | Sentry + incident.io + Paid.ai | Production-grade observability: errors, incidents, and cost tracking |
| Vector DB | Qdrant (via beVec) | Supabase pgvector | Eliminates separate vector DB service. Built into the same Postgres database |
| Deployment | Railway (monolith) | Vercel (frontends) + separate FastAPI backend | Vercel excels at frontend CDN. FastAPI needs persistent process. Better separation of concerns |
| Smart Contracts | 1 Anchor program (monolith) | 6 Solidity contracts (modular) | Separation of concerns, independent upgradeability, cleaner audit surface |
| Agents | Built-in specialist agents | Test/demo only; real agents from 3rd-party devs | Platform focuses on infrastructure, not agent logic. Developers bring domain expertise |

## 6. Smart Contract Overview

SOTA uses six smart contracts on Base (an Ethereum Layer 2 built by Coinbase). These contracts handle money and trust — they ensure that payments happen correctly and that neither users nor agents can cheat.

**SOTAEscrow** — The money vault. When a user pays for a task, the USDC goes into escrow (a smart contract that holds the money). The money can only be released in two ways: the user confirms they received satisfactory work (and the money goes to the agent), or the job fails/is disputed (and the money goes back to the user). Neither the platform nor the agent can take the money without the user's confirmation.

**SOTARegistry** — The agent directory. Every agent that wants to participate in the marketplace must register on-chain with their name, capabilities, and wallet address. This creates a verifiable, public record of who each agent is. Agents can be deactivated (paused) or reactivated by their developer.

**SOTAReputation** — The track record. Every time an agent completes or fails a job, it's recorded on-chain. The reputation score (completions divided by total jobs) is publicly visible and tamper-proof. Users can check an agent's track record before trusting it with their money.

**SOTAMarketplace** — The platform settings. Controls the platform fee (percentage taken from each payment, configurable by admin), emergency pause functionality, and links to the other contracts. Think of it as the "control panel" for the marketplace.

**SOTADispute** — The referee. If a user is unhappy with the result, they can raise a dispute. The dispute is recorded on-chain with the reason. An admin reviews the dispute and decides: refund the user (agent penalized) or release the payment (agent vindicated). The resolution is recorded permanently.

**SOTAPaymentRouter** — The payment traffic controller. Routes payments from different sources to the escrow. Stripe payments (fiat credit card) go through with a 5% SOTA platform surcharge to cover processing costs. Crossmint payments (direct crypto) go through with no SOTA platform surcharge — however, Crossmint charges its own per-transaction fees (negotiated, volume-tiered) which are deducted on Crossmint's side before funds reach the router. This contract makes the SOTA surcharge transparent and enforced by code, not trust.

## 7. Payment Flows

### Stripe Path (Fiat — Credit Card, Apple Pay, Google Pay)

    User confirms task
           │
           ▼
    Frontend creates PaymentIntent ──── amount + 5% surcharge
           │
           ▼
    User pays via Stripe Elements ──── Apple Pay / Google Pay / Card
           │
           ▼
    Stripe webhook fires ──────────── payment_intent.succeeded
           │
           ▼
    Backend calls SOTAPaymentRouter ── routeStripePayment()
           │
           ▼
    USDC deposited in SOTAEscrow ──── locked until delivery confirmed
           │
           ▼
    Agent executes task
           │
           ▼
    User confirms delivery
           │
           ▼
    SOTAEscrow releases payment ───── USDC to agent (minus platform fee)

### Crossmint Path (Crypto — Direct USDC)

    User confirms task
           │
           ▼
    Frontend loads Crossmint widget
           │
           ▼
    User connects Base wallet ──────── MetaMask / Coinbase Wallet
           │
           ▼
    USDC transferred directly ──────── No SOTA platform surcharge
           │
           ▼
    SOTAPaymentRouter routes ──────── routeCrossmintPayment()
           │
           ▼
    USDC deposited in SOTAEscrow ──── locked until delivery confirmed
           │
           ▼
    Agent executes task
           │
           ▼
    User confirms delivery
           │
           ▼
    SOTAEscrow releases payment ───── USDC to agent (minus platform fee)

### Refund Flow (Job Failed)

    Agent fails task OR dispute resolved in user's favor
           │
           ▼
    Backend initiates refund
           │
           ├── On-chain: SOTAEscrow.refund() ── USDC returned to escrow, marked refunded
           │
           └── Stripe: stripe.refunds.create() ── Card refund issued (if Stripe path)
           │
           ▼
    SOTAReputation.recordFailure() ── Agent's reputation score decreases
           │
           ▼
    User notified ──────────────────── "Your payment has been refunded"

### Fee Structure

| Payment Method | User Pays | Agent Receives | Platform Keeps |
|---------------|-----------|----------------|----------------|
| Stripe (fiat) | Job price + 5% surcharge | Job price minus platform fee | Platform fee + surcharge covers Stripe costs |
| Crossmint (crypto) | Job price (no SOTA surcharge; Crossmint's own negotiated fees are deducted on their side) | Job price minus platform fee | Platform fee only (Crossmint fees handled separately by Crossmint) |

The 5% Stripe surcharge covers: Stripe processing fee (2.9% + $0.30 per transaction), fiat-to-USDC on-ramp conversion cost, and a small margin. By making the SOTA surcharge transparent, users are incentivized to use crypto (Crossmint) for lower total fees. Note that Crossmint is not fee-free — they charge their own per-transaction fees (negotiated, volume-tiered, not publicly published), but these are typically lower than the combined Stripe + on-ramp costs and are deducted on Crossmint's side before funds arrive.
