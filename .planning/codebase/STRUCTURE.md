# Codebase Structure

**Analysis Date:** 2026-03-14

## Directory Layout

```
SOTA_HackEurope/
├── app/                           # Next.js Pages Router (main web app)
│   ├── api/                       # API routes (REST endpoints)
│   │   ├── agents/
│   │   ├── auth/
│   │   ├── disputes/
│   │   ├── marketplace/
│   │   ├── tasks/
│   │   └── webhooks/
│   ├── agents/                    # Agent listing page
│   ├── developers/                # Developer portal (deploy, docs, payout)
│   ├── login/                     # Auth page
│   ├── marketplace/               # Marketplace page (job listing/posting)
│   ├── page.tsx                   # Landing page
│   ├── layout.tsx                 # Root layout
│   ├── globals.css                # Global styles
│   └── (other pages)
│
├── mobile_frontend/               # Next.js mobile web app (responsive web app)
│   ├── app/
│   │   ├── api/                   # Mobile-specific API routes (auth, chat, stripe)
│   │   ├── marketplace/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── src/
│   │   ├── components/            # Mobile UI components
│   │   ├── context/               # React context (state management)
│   │   ├── lib/                   # Utilities
│   │   └── (other source)
│   ├── package.json               # Mobile-specific dependencies (ElevenLabs, Three.js, etc.)
│   ├── tsconfig.json              # Mobile TS config
│   └── prisma/                    # Mobile Prisma schema (may differ from root)
│
├── src/                           # Shared TS utilities (imported by both apps)
│   ├── app/
│   │   ├── api/                   # Shared API routes (e.g., agents dashboard)
│   │   └── developers/            # Shared developer portal routes
│   ├── components/
│   │   ├── ui/                    # Reusable UI components (card, button, glass-card, etc.)
│   │   ├── navigation.tsx
│   │   ├── auth-provider.tsx
│   │   ├── wallet-provider.tsx
│   │   ├── theme-provider.tsx
│   │   └── (other shared components)
│   └── lib/
│       ├── auth.ts                # JWT, API key, session utilities
│       ├── prisma.ts              # Prisma client singleton
│       ├── contracts.ts           # Solana contract interaction helpers
│       ├── clawbot-verify.ts      # External agent verification
│       ├── agent-templates.ts     # Predefined agent templates
│       ├── utils.ts               # General utilities
│       └── validators.ts          # Zod schemas for auth, agents, profiles
│
├── agents/                        # Python agent SDK and implementations
│   ├── butler_api.py              # FastAPI server (primary entry point for agents)
│   ├── railway.toml               # Railway deployment config
│   ├── marketplace/
│   │   ├── hub.py                 # Central marketplace hub (job registry, bidding)
│   │   └── (job board, bid tracking)
│   ├── src/
│   │   ├── butler/                # Butler agent (Claude-powered concierge)
│   │   │   ├── agent.py
│   │   │   ├── tools.py           # Tools (RAG, slot filling, job posting, etc.)
│   │   │   └── server.py
│   │   ├── hackathon/             # Hackathon finder agent
│   │   ├── caller/                # Voice call agent
│   │   ├── smart_shopper/         # Shopping automation agent
│   │   ├── trip_planner/          # Travel planning agent
│   │   ├── refund_claim/          # Refund automation agent
│   │   ├── restaurant_booker/     # Restaurant booking agent
│   │   ├── competitor_fun/        # Competitor analysis agent
│   │   ├── fun_activity/          # Activity finder agent
│   │   ├── gift_suggestion/       # Gift recommendation agent
│   │   ├── x402/                  # HTTP 402 (payment required) handler
│   │   ├── manager/               # Job manager agent
│   │   ├── caller/                # Caller agent
│   │   ├── shared/                # Shared Python utilities
│   │   │   ├── hub_connector.py   # WebSocket client for hub connection
│   │   │   ├── auto_bidder.py     # Autonomous bidding logic
│   │   │   ├── tool_base.py       # Base class for tools
│   │   │   ├── config.py          # Configuration (API keys, URLs)
│   │   │   ├── chain_config.py    # Solana chain configuration
│   │   │   ├── chain_contracts.py # Solana contract interaction
│   │   │   ├── database_postgres.py # PostgreSQL utilities
│   │   │   ├── hmac_signer.py     # HMAC signing for external agents
│   │   │   ├── incident_io.py     # Incident.io integration
│   │   │   ├── serpapi_client.py  # SerpAPI (search) client
│   │   │   ├── a2a.py             # Agent-to-agent communication
│   │   │   ├── butler_comms.py    # Butler data exchange protocol
│   │   │   └── slot_questioning.py # Slot-filling dialogue
│   │   ├── sota_sdk/              # SOTA SDK (cost calculation, chain utilities)
│   │   │   ├── chain/             # Solana chain utilities
│   │   │   └── cost/              # Cost calculation
│   │   └── tests/                 # Python tests
│   └── (other Python files)
│
├── anchor/                        # Solana smart contracts (Rust/Anchor)
│   ├── programs/
│   │   └── sota_marketplace/
│   │       ├── src/
│   │       │   ├── lib.rs         # Contract entry point
│   │       │   ├── instructions/  # Per-instruction modules
│   │       │   │   ├── create_job.rs
│   │       │   │   ├── assign_provider.rs
│   │       │   │   ├── mark_completed.rs
│   │       │   │   ├── release_payment.rs
│   │       │   │   ├── confirm_delivery.rs
│   │       │   │   ├── refund.rs
│   │       │   │   ├── raise_dispute.rs
│   │       │   │   ├── cancel_job.rs
│   │       │   │   └── (other instructions)
│   │       │   └── (other Rust files)
│   │       ├── Cargo.toml
│   │       └── (Anchor config)
│   ├── app/                       # Client code for contract interaction
│   ├── target/                    # Build artifacts (debug, release, IDL)
│   ├── tests/                     # Rust tests
│   ├── migrations/                # Anchor migrations
│   ├── Anchor.toml
│   └── (other Anchor files)
│
├── prisma/                        # Database schema (PostgreSQL)
│   ├── schema.prisma              # Prisma data model
│   ├── migrations/                # Migration files (20251206..., etc.)
│   └── seed.js                    # Database seed script
│
├── docs/                          # Documentation
│   ├── CLAUDE.md                  # Claude agent guidelines
│   ├── backend-technical.md       # Backend API documentation
│   ├── frontend-devportal.md      # Developer portal UI spec
│   ├── frontend-mobile.md         # Mobile app spec
│   ├── mobile-backend.md          # Mobile backend spec
│   ├── team-overview.md           # Team and project overview
│   └── (other docs)
│
├── .planning/                     # GSD planning directory (created by orchestrator)
│   └── codebase/                  # Codebase analysis documents
│
├── middleware.ts                  # Next.js middleware (auth redirects)
├── tsconfig.json                  # Root TypeScript config
├── package.json                   # Root dependencies (main app)
├── package-lock.json              # Lock file
├── pnpm-lock.yaml                 # PNPM lock file
├── next.config.ts                 # Next.js configuration
├── eslint.config.mjs              # ESLint configuration
├── postcss.config.mjs             # PostCSS configuration
├── Dockerfile                     # Docker image for main app
├── railway.toml                   # Railway deployment config (agents)
├── start.sh                       # Startup script
├── stop.sh                        # Shutdown script
├── test_agents.py                 # Agent testing script
├── test_execute.py                # Execution testing script
└── README.md                      # Project README
```

## Directory Purposes

**app/ (Next.js Web App):**
- Purpose: Main public-facing web application (landing, marketplace, developer portal)
- Contains: Pages, layouts, API routes
- Key files: `page.tsx` (landing), `/api/**` (REST endpoints)

**mobile_frontend/ (Mobile Web App):**
- Purpose: Responsive mobile version of SOTA with voice agent chat and wallet integration
- Contains: Mobile-optimized pages, mobile-specific API routes, 3D animations (Three.js)
- Key files: `app/page.tsx`, mobile components in `src/components/`

**src/ (Shared Code):**
- Purpose: TypeScript utilities shared across both web apps
- Contains: Reusable UI components, auth helpers, validators, database utilities
- Key files: `/lib/auth.ts`, `/lib/validators.ts`, `/lib/prisma.ts`

**agents/ (Python Agent System):**
- Purpose: Distributed agent network and FastAPI bridge
- Contains: Individual agent implementations, SDK utilities, marketplace hub
- Key files: `butler_api.py` (entry point), `/shared/` (SDKes)

**anchor/ (Smart Contracts):**
- Purpose: Solana smart contracts for trustless job escrow and payments
- Contains: Rust instructions, deployment artifacts
- Key files: `lib.rs`, `/instructions/` modules

**prisma/ (Database):**
- Purpose: PostgreSQL schema and migrations
- Contains: Prisma data model, migration history
- Key files: `schema.prisma`

**docs/ (Documentation):**
- Purpose: Project and API documentation
- Contains: Architecture guides, API specs, team info

## Key File Locations

**Entry Points:**

- `app/page.tsx`: Landing page (hero, features, testimonials)
- `app/marketplace/page.tsx`: Marketplace (job listing, posting)
- `app/developers/**`: Developer portal (deploy, docs, payout)
- `agents/butler_api.py`: FastAPI server for Butler and marketplace APIs
- `agents/marketplace/hub.py`: Central job registry and bidding coordinator
- `anchor/programs/sota_marketplace/src/lib.rs`: Smart contract program

**Configuration:**

- `tsconfig.json`: TypeScript compiler options, path aliases (`@/*` → `src/*`)
- `package.json`: Root app dependencies
- `mobile_frontend/package.json`: Mobile app dependencies
- `prisma/schema.prisma`: Database schema (models, relationships, indexes)
- `next.config.ts`: Next.js configuration
- `anchor/Anchor.toml`: Anchor framework configuration

**Core Logic:**

- `src/lib/auth.ts`: Session/API key management, encryption, password hashing
- `src/lib/validators.ts`: Zod schemas for input validation (authSchema, agentSchema, etc.)
- `src/lib/contracts.ts`: Solana contract invocation helpers
- `app/api/agents/route.ts`: Agent CRUD operations
- `app/api/marketplace/execute/route.ts`: Job execution endpoint (agent reports result)
- `agents/src/shared/hub_connector.py`: WebSocket client that connects agents to hub
- `agents/src/shared/auto_bidder.py`: Autonomous bidding logic
- `agents/src/butler/agent.py`: Butler (Claude-powered) agent implementation
- `agents/src/{agent-name}/agent.py`: Individual agent implementation (hackathon, caller, etc.)
- `agents/src/{agent-name}/tools.py`: Tools (callables) exposed by the agent

**Testing:**

- `agents/tests/`: Python test directory (one test file per agent)
- Frontend tests: Co-located in component files (Jest/Vitest imports) — no dedicated test directory
- `test_agents.py`, `test_execute.py`: Manual testing scripts at project root

## Naming Conventions

**Files:**

- TypeScript pages: `page.tsx` (Next.js convention)
- TypeScript API routes: `route.ts` (Next.js convention)
- TypeScript utilities: `kebab-case.ts` (e.g., `clawbot-verify.ts`, `agent-templates.ts`)
- Python modules: `snake_case.py` (e.g., `hub_connector.py`, `auto_bidder.py`)
- Solana instructions: `instruction_name.rs` (e.g., `create_job.rs`, `assign_provider.rs`)

**Directories:**

- Feature directories: `kebab-case` (e.g., `developers/`, `mobile_frontend/`)
- Python packages: `snake_case` (e.g., `src/butler/`, `src/shared/`)
- Pages/routes: Match their route pattern (e.g., `app/developers/deploy/`, `app/api/agents/external/`)

**Classes & Types:**

- TypeScript classes: PascalCase (e.g., `HubConnector`, `AuthError`)
- Zod schemas: camelCase ending with "Schema" (e.g., `agentSchema`, `authSchema`)
- Python classes: PascalCase (e.g., `ToolManager`, `SlotFiller`)
- Prisma models: PascalCase (e.g., `User`, `Agent`, `MarketplaceJob`)

**Variables & Functions:**

- TypeScript: camelCase (e.g., `getCurrentUser()`, `validateApiKey()`)
- Python: snake_case (e.g., `execute_job()`, `place_bid()`)

## Where to Add New Code

**New Feature (User-facing):**
- Primary code: `app/{feature-name}/page.tsx` and subpages
- Components: `src/components/` for shared, local to page for feature-specific
- API routes: `app/api/{resource}/route.ts`
- Tests: Co-locate in component files or create `/tests/` directory

**New Agent (Python):**
- Implementation: `agents/src/{agent_name}/`
  - `agent.py`: Main agent class
  - `tools.py`: Tools/capabilities
  - `server.py`: FastAPI server with lifespan and endpoints
- Shared utilities: Use/extend from `agents/src/shared/`
- Hub connection: Use `HubConnector` in `server.py` lifespan
- Tests: `agents/tests/{agent_name}_test.py`

**New Utility/Helper (Shared):**
- Validators/schemas: `src/lib/validators.ts`
- Auth logic: `src/lib/auth.ts`
- General utilities: `src/lib/utils.ts`
- Component utilities: `src/components/`
- Python utilities: `agents/src/shared/`

**New Smart Contract Instruction:**
- Implementation: `anchor/programs/sota_marketplace/src/instructions/{instruction_name}.rs`
- Register in: `anchor/programs/sota_marketplace/src/lib.rs` (add to `#[program]`)
- Accounts/state: Define in `/src/state.rs` or inline
- Tests: `anchor/tests/{instruction_name}.ts` (TypeScript)

**Database Schema Change:**
- Modify: `prisma/schema.prisma`
- Create migration: `pnpm db:migrate` (auto-generates file in `prisma/migrations/`)
- Commit: Migration files are version-controlled

## Special Directories

**node_modules/:**
- Purpose: NPM/PNPM dependencies
- Generated: Yes (via `pnpm install`)
- Committed: No (in .gitignore)

**.next/:**
- Purpose: Next.js build output and dev server cache
- Generated: Yes (via `next build` or `next dev`)
- Committed: No (in .gitignore)

**anchor/target/:**
- Purpose: Rust build artifacts, compiled smart contracts, IDL files
- Generated: Yes (via `anchor build`)
- Committed: No (in .gitignore)

**prisma/migrations/:**
- Purpose: Database migration history (one file per schema change)
- Generated: Yes (via `prisma migrate dev`)
- Committed: Yes (tracked in git)

**.planning/:**
- Purpose: GSD planning documents (created by `/gsd:map-codebase` command)
- Generated: Yes (by Claude agent)
- Committed: No (`.planning/` is typically in .gitignore, but created by orchestrator)

**.env & .env.* files:**
- Purpose: Environment variables and secrets
- Generated: Manual (created by developers)
- Committed: No (.env in .gitignore; .env.example is safe to commit as template)

---

*Structure analysis: 2026-03-14*
