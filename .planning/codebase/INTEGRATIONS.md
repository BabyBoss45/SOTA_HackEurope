# External Integrations

**Analysis Date:** 2026-03-14

## APIs & External Services

**LLM & AI:**
- **Anthropic Claude** - Core Butler Agent intelligence
  - SDK: `anthropic>=0.39.0`
  - Auth: `ANTHROPIC_API_KEY` (sk-ant-...)
  - Model: Claude Sonnet (primary), configurable via `LLM_MODEL`
  - Usage: Agent reasoning, task planning, response generation
  - Endpoint: `https://api.anthropic.com/v1/`

- **OpenAI GPT-4o** - Competitor Fun Agent (alternative LLM)
  - SDK: `openai>=1.40.0`
  - Auth: `OPENAI_API_KEY` (sk-proj-...)
  - Model: `gpt-4o` (configurable via `OPENAI_MODEL`)
  - Usage: Competitive analysis, fun responses
  - Location: `agents/src/competitor_fun/openai_runner.py`

**Voice & Conversation:**
- **ElevenLabs Conversational AI** - Voice interface + call handling
  - SDK: `elevenlabs>=1.0.0`, `@elevenlabs/react^0.14.0`
  - Auth: `ELEVENLABS_API_KEY` (xi-api-key header)
  - Agent ID: `ELEVENLABS_AGENT_ID` (conversational agent configuration)
  - Phone ID: `ELEVENLABS_PHONE_ID` (for Twilio integration)
  - Caller Agent: `ELEVENLABS_CALLER_AGENT_ID` (falls back to main agent)
  - Endpoints:
    - Token generation: `https://api.elevenlabs.io/v1/convai/conversation/token`
    - WebRTC streaming: ElevenLabs proprietary
  - Usage: Mobile app voice interface, phone call agent
  - Implementation: `mobile_frontend/app/api/elevenlabs/token/route.ts`

- **Twilio VoIP** - Phone call infrastructure
  - SDK: `twilio>=9.3.0`
  - Auth: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
  - Phone: `TWILIO_PHONE_NUMBER` (E.164 format, e.g., +14155552670)
  - Usage: Inbound/outbound calls for Caller Agent
  - Location: `agents/src/caller/agent.py`, `agents/src/caller/server.py`
  - Call summaries: Optional webhook via `CALL_SUMMARY_WEBHOOK_URL`

**Payment Processing:**
- **Stripe** - Credit card payments + webhooks
  - SDK: `stripe@20.3.1`, `@stripe/stripe-js@8.7.0`, `@stripe/react-stripe-js@5.6.0`
  - Auth:
    - Server: `STRIPE_SECRET_KEY` (sk_test_... or sk_live_...)
    - Client: `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (pk_test_... or pk_live_...)
  - Webhook Secret: `STRIPE_WEBHOOK_SECRET` (whsec_...)
  - API Version: 2026-01-28.clover
  - Endpoints:
    - Create payment intent: `POST /mobile_frontend/app/api/stripe/create-payment-intent/route.ts`
    - Webhook handler: `POST /mobile_frontend/app/api/stripe/webhook/route.ts`
    - Refund endpoint: `POST /mobile_frontend/app/api/stripe/refund/route.ts`
  - Flow: Frontend → Stripe → Webhook → On-chain USDC transfer
  - Metadata passed: `jobId`, `agentAddress` (Solana wallet), `usdcAmountRaw`

**Search & Information:**
- **SerpAPI** - Web search, shopping, flights, hotels, local search
  - SDK: `google-search-results>=2.4.2`
  - Auth: `SERPAPI_API_KEY`
  - Usage:
    - Gift Suggestion Agent: Product search, price comparison
    - Smart Shopper Agent: E-commerce price scraping
    - Restaurant Booker: Restaurant search + info
    - Trip Planner: Flight, hotel, local search
  - Location: `agents/src/shared/serpapi_client.py`

**Web Scraping & Automation:**
- **Playwright** - Browser automation
  - SDK: `playwright>=1.40.0`
  - Auth: None (headless browser)
  - Usage: Hackathon registration form filling, dynamic content extraction
  - Location: Hackathon Agent (`agents/src/hackathon/agent.py`)

- **BeautifulSoup4** - HTML parsing
  - SDK: `beautifulsoup4>=4.12.0`
  - Usage: Static HTML scraping, gift suggestions, restaurant details
  - Location: Shared agents

**Cost Tracking:**
- **Paid.ai** - LLM usage cost tracking
  - SDK: `paid-python>=1.0.5`
  - Auth: `SOTA_PAID_API_KEY`
  - Usage: Monitor Claude/OpenAI API costs per agent
  - Implementation: Optional integration in Butler Agent

**Incident Management:**
- **incident.io** - On-call alerting + incident tracking
  - Auth: `INCIDENT_IO_API_KEY`
  - Alert Source: `INCIDENT_IO_ALERT_SOURCE_ID`
  - Usage: Critical error alerts
  - Location: `agents/src/shared/incident_io.py`
  - Optional: Falls back gracefully if not configured

## Data Storage

**Databases:**
- **PostgreSQL** - Primary relational database
  - Connection: `DATABASE_URL` (postgresql://user:password@host:5432/sota)
  - Client: Prisma (TypeScript ORM), asyncpg (Python async driver)
  - Provider: Railway (production) or local container (dev)
  - Models: `prisma/schema.prisma` (User, Agent, Order, MarketplaceJob, ExternalAgent, WorkerAgent, etc.)
  - Migrations: Prisma manage schema changes

- **Qdrant** - Vector database for embeddings
  - Connection: `QDRANT_URL`, `QDRANT_API_KEY`
  - Client: `qdrant-client>=1.7.0`
  - Usage: Semantic search for task patterns, user profile memory
  - Collections: QDRANT_COLLECTION (dynamically created)
  - Implementation: `agents/src/shared/task_memory.py`, `agents/src/shared/slot_questioning.py`
  - Optional: Falls back if not configured

**File Storage:**
- **Local filesystem only** - No cloud storage integration detected
  - Call summaries: Stored in PostgreSQL as `CallSummary.storageUri` (optional)
  - Agent API keys: Encrypted in database via cryptography library

**Caching:**
- **In-memory** - Python dictionaries + FastAPI dependency injection
  - Rate limiter state: In-memory dict in `mobile_frontend/app/api/elevenlabs/token/route.ts`
  - Agent registry: FastAPI cache + marketplace hub WebSocket registry
  - No Redis detected

**Optional Cloud Services:**
- **Firebase Firestore** - User profile storage (optional fallback)
  - SDK: `firebase-admin>=6.2.0`, `google-cloud-firestore>=2.16.0`
  - Usage: User preferences, profile data (not primary flow)
  - Not used in main schema but available for extended features

## Authentication & Identity

**Auth Provider:**
- **Custom JWT** - Platform-managed authentication
  - Library: `jsonwebtoken@9.0.3` (TypeScript)
  - Flow:
    1. User registers via `mobile_frontend/app/api/auth/register/route.ts`
    2. Password hashed with bcryptjs (10 rounds)
    3. JWT issued on login via `mobile_frontend/app/api/auth/login/route.ts`
    4. Token stored in httpOnly cookie or localStorage
    5. Token validation on protected routes
  - Session storage: `Session` model in Prisma (expiry tracking)
  - Session ID: UUID-based, tracked per user

- **Solana Wallet** - Web3 authentication
  - Adapter: `@solana/wallet-adapter-react@0.15.39`
  - Wallets supported: Via `@solana/wallet-adapter-wallets@0.19.37`
    - Phantom, Magic Eden, Ledger, etc.
  - Flow: Sign message → Verify signature → Derive public key
  - Used for: Agent marketplace transactions, on-chain identity
  - Location: `mobile_frontend/src/providers.tsx`, wallet components

- **ElevenLabs Token** - Ephemeral voice session tokens
  - Generated per request via `mobile_frontend/app/api/elevenlabs/token/route.ts`
  - Rate limited: 10 requests per minute per IP
  - Expires: Token lifetime controlled by ElevenLabs (typically minutes)

## Monitoring & Observability

**Error Tracking:**
- **incident.io** (optional)
  - SDK: None (direct HTTP API calls via `agents/src/shared/incident_io.py`)
  - Auth: `INCIDENT_IO_API_KEY`
  - Usage: Critical service alerts
  - Fallback: Console logging if not configured

**Logs:**
- **Console/stdout** - Standard approach
  - Python: `logging` module, configured in FastAPI startup
  - TypeScript: console methods + Next.js built-in logging
  - Structured: Pino-pretty for pretty JSON logs (optional)
  - Railway: Captures stdout → Logs dashboard

**Observability:**
- Cost tracking: Paid.ai (`SOTA_PAID_API_KEY`)
- Agent metrics: TaskPatternMemory + reputation engine
- Database query logging: Prisma debug mode (via environment)

## CI/CD & Deployment

**Hosting:**
- **Vercel** - Frontend deployment
  - Apps: Main app (`src/`) and mobile app (`mobile_frontend/`)
  - Config: Implicit via `vercel.json` or Next.js defaults
  - Env vars: Set via Vercel dashboard
  - Build: `pnpm build` (prisma generate + next build)

- **Railway** - Backend deployment
  - Apps: Butler API + individual agent services
  - Config: `railway.toml` (main app), `agents/railway.toml` (agents)
  - Docker: Railway auto-detects Dockerfile or uses nixpacks
  - Env vars: Set via Railway dashboard
  - Database: Railway PostgreSQL (built-in)
  - Networking: Internal DNS for service-to-service communication

**Deployment Flow:**
1. Git push to main branch
2. Railway detects changes (webhook-based or polling)
3. Build triggered: `pnpm build` (JavaScript) or `pip install -e .` (Python)
4. Environment vars injected from Railway dashboard
5. Service restarts with new code
6. Database migrations run automatically (Prisma postinstall hook)

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - PostgreSQL connection
- `ANTHROPIC_API_KEY` - Claude access
- `ELEVENLABS_AGENT_ID` - Voice agent config
- `ELEVENLABS_API_KEY` - Voice service auth
- `STRIPE_SECRET_KEY` - Payment processing
- `STRIPE_WEBHOOK_SECRET` - Webhook validation
- `SOLANA_CLUSTER` - Network selection (devnet/testnet/mainnet)
- `RPC_URL` - Solana RPC endpoint

**Optional but recommended:**
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` - Phone calls
- `SERPAPI_API_KEY` - Web search
- `OPENAI_API_KEY` - GPT-4o fallback
- `QDRANT_URL`, `QDRANT_API_KEY` - Vector search
- `INCIDENT_IO_API_KEY` - Error alerts
- `SOTA_PAID_API_KEY` - Cost tracking
- `PRIVATE_KEY` - Solana keypair (agent wallet)

**Secrets location:**
- **Development:** `.env` files (git-ignored)
- **Production:** Railway environment dashboard
- **Never committed:** See forbidden_files in documentation

## Webhooks & Callbacks

**Incoming (Platform listens):**
- **Stripe** - Payment intent completion
  - Endpoint: `POST /mobile_frontend/app/api/stripe/webhook/route.ts`
  - Signature validation: Via `STRIPE_WEBHOOK_SECRET`
  - Events handled: `payment_intent.succeeded`, `charge.refunded`
  - Flow: Webhook → Verify signature → Trigger on-chain USDC transfer

- **ElevenLabs** - Call summaries (optional)
  - Endpoint: Configured via `CALL_SUMMARY_WEBHOOK_URL`
  - Auth: `CALL_SUMMARY_SECRET` (if required)
  - Payload: Call metadata, transcript, summary
  - Storage: `CallSummary` model in Prisma

- **Marketplace Hub** - WebSocket agent bidding
  - Connection: `SOTA_HUB_URL` (ws://localhost:3001/hub/ws/agent)
  - Protocol: WebSocket with JSON messages
  - Agents connect to receive job broadcasts

**Outgoing (Platform calls external):**
- **Solana RPC** - On-chain transactions
  - Endpoint: `RPC_URL` (https://api.devnet.solana.com)
  - Methods: Send transaction, get account info, confirm
  - SDK: @solana/web3.js

- **Agent Webhook URLs** - External agent callbacks (marketplace)
  - Field: `Agent.webhookUrl` (optional, per-agent)
  - Usage: Platform → ExternalAgent → Callback with results
  - Signing: HMAC-SHA256 (secret in `Agent.publicKey`)

---

*Integration audit: 2026-03-14*
