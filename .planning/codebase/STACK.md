# Technology Stack

**Analysis Date:** 2026-03-14

## Languages

**Primary:**
- TypeScript 5.9+ - Main frontend and API code in `src/` and `mobile_frontend/`
- Python 3.12+ - Agent backend systems in `agents/`
- Rust 2021 edition - Solana smart contracts in `anchor/programs/sota_marketplace/`

**Secondary:**
- JavaScript/JSX - React components and configuration files
- GLSL - Shader code for 3D graphics in `mobile_frontend/src/components/shaders/`

## Runtime

**Environment:**
- Node.js (v18+ implied by Next.js 16)
- Python 3.12+
- Solana Rust toolchain (for smart contract development)

**Package Manager:**
- pnpm 10.22.0+ - Monorepo package management for JavaScript packages
- Python pip/uv - Python dependency management
- Yarn - Rust/Solana tooling

Lockfiles:
- `pnpm-lock.yaml` - Present and committed
- `package-lock.json` - Present in mobile_frontend (legacy)
- Python: `requirements.txt` + `pyproject.toml`

## Frameworks

**Core Web:**
- Next.js 16.1.6 (main app in `src/`) - Server/Client rendering
- Next.js 15.5.7 (mobile_frontend) - Mobile app variant
- React 19.2.0 / 19.2.1 - UI library
- React DOM 19.2.0 / 19.2.1 - DOM rendering

**Backend/API:**
- FastAPI 0.115.0+ - Python REST API (`agents/butler_api.py`)
- Uvicorn 0.32.0+ - ASGI server for Python
- Prisma 6.19.2 - ORM for PostgreSQL

**Web3/Blockchain:**
- @solana/web3.js 1.98.4 - Solana blockchain interaction
- @coral-xyz/anchor 0.32.1 - Solana program framework (client + server)
- @solana/spl-token 0.4.14 - SPL token standard (USDC)
- @solana/wallet-adapter-react 0.15.39 - Solana wallet integration
- @solana/wallet-adapter-react-ui 0.9.39 - Wallet UI components
- @solana/wallet-adapter-wallets 0.19.37 - Multiple wallet support

**UI & Styling:**
- Tailwind CSS 4+ - Utility-first CSS framework
- Framer Motion 12.23-12.33 - Animation library
- Lucide React 0.474.0+ - Icon library
- Three.js 0.181.2 - 3D graphics library (mobile_frontend)
- @react-three/fiber 9.4.2 - React renderer for Three.js
- @react-three/drei 10.7.7 - Three.js utility components
- Radix UI (@radix-ui/react-slot) - Headless UI components
- class-variance-authority 0.7.1 - CSS variant management
- clsx 2.1.1 - className utilities

**Data Management:**
- @tanstack/react-query 5.62-5.90 - Server state management
- Zod 3.24-3.25 - TypeScript-first schema validation
- Pydantic 2.9.0+ - Python data validation

**Testing:**
- pytest 8.0.0+ - Python testing framework
- pytest-asyncio 0.24.0+ - Async test support
- Mock/patch patterns (Python standard library)

**Build/Dev:**
- TypeScript 5+ - Type checking
- ESLint 9.39.2 - JavaScript/TypeScript linting
- Prettier (via ESLint config) - Code formatting
- Tailwind CSS PostCSS plugin - CSS generation
- PostCSS - CSS processing
- Autoprefixer - CSS vendor prefixes

## Key Dependencies

**Critical:**
- Anthropic SDK (`anthropic>=0.39.0`) - Claude LLM integration for Butler Agent
- OpenAI SDK (`openai>=1.40.0`) - GPT-4o for Competitor Fun Agent
- ElevenLabs (`elevenlabs>=1.0.0`, `@elevenlabs/react^0.14.0`) - Voice AI for call agent + conversational interface
- Stripe (`stripe@20.3.1`, `@stripe/stripe-js@8.7.0`, `@stripe/react-stripe-js@5.6.0`) - Payment processing
- Twilio (`twilio>=9.3.0`) - VoIP/phone integration for caller agent

**LLM/AI Orchestration:**
- LangGraph (`langgraph>=0.2.0`) - Agent graph orchestration
- LangChain (`langchain-core>=0.3.0`) - LLM tool abstraction
- Sentence Transformers (`sentence-transformers>=3.0.0`) - Text embeddings
- mem0ai (`mem0ai>=0.0.10`) - Memory/conversation context storage

**Vector/Search:**
- Qdrant Client (`qdrant-client>=1.7.0`) - Vector database client
- Embedding models via sentence-transformers - Text-to-vector conversion

**Database:**
- PostgreSQL (via `asyncpg>=0.30.0`) - Primary relational database
- asyncpg pool management - Async database connections
- Prisma Client - TypeScript ORM for queries

**External APIs:**
- SerpAPI (`google-search-results>=2.4.2`) - Web search, shopping, flights, hotels
- Firebase Admin (`firebase-admin>=6.2.0`) - Cloud Firestore integration (optional)
- Google Cloud Firestore (`google-cloud-firestore>=2.16.0`) - Document database
- Paid.ai SDK (`paid-python>=1.0.5`) - Cost tracking
- Playwright (`playwright>=1.40.0`) - Browser automation for web scraping
- BeautifulSoup4 (`beautifulsoup4>=4.12.0`) - HTML parsing

**Cryptography & Signing:**
- bcryptjs (`bcryptjs^2.4.3`) - Password hashing
- PyNaCl (`PyNaCl>=1.5.0`) - Asymmetric encryption (agent signing)
- cryptography (`cryptography>=42.0.0`) - AES-256 encryption, HMAC
- tweetnacl.js (`tweetnacl@1.0.3`) - Crypto operations (JavaScript)
- jsonwebtoken (`jsonwebtoken@9.0.3`) - JWT for session management

**Networking & Async:**
- httpx (`httpx>=0.27.0`) - Async HTTP client (Python)
- aiohttp (`aiohttp>=3.10.0`) - Async HTTP (Python)
- requests (`requests>=2.31.0`) - Sync HTTP (Python)
- WebSockets (`websockets>=10.0,<12.0`) - WebSocket client for hub connectivity
- Starlette (`starlette>=0.27.0`) - ASGI middleware utilities

**Utilities:**
- python-dotenv (`python-dotenv>=1.0.0`) - Environment variable loading
- Pino Pretty (`pino-pretty@13.1.3`) - Structured logging
- bn.js (`bn.js@5.2.3`) - Big number arithmetic
- bs58 (`bs58@6.0.0`) - Base58 encoding/decoding
- simplex-noise (`simplex-noise@4.0.3`) - Procedural noise generation
- jszip (`jszip@3.10.1`) - ZIP file handling
- tail-wave-merge (`tailwind-merge@3.4.0`) - Tailwind class merging

## Configuration

**Environment:**
- Single `.env` file per application root:
  - `/Users/macbook/Projects/SOTA_HackEurope/.env` - Main app config
  - `/Users/macbook/Projects/SOTA_HackEurope/mobile_frontend/.env` - Mobile frontend
  - `/Users/macbook/Projects/SOTA_HackEurope/agents/.env` - Agent backend
- Environment-based configuration via `process.env` (Node) and `os.getenv()` (Python)
- Key configs (non-secrets):
  - `DATABASE_URL` - PostgreSQL connection string
  - `SOLANA_CLUSTER` - Network (devnet/testnet/mainnet)
  - `RPC_URL` - Solana RPC endpoint
  - `PROGRAM_ID` - Deployed smart contract ID
  - `ELEVENLABS_AGENT_ID` - Voice agent configuration
  - `ANTHROPIC_API_KEY` - Claude API access
  - `OPENAI_API_KEY` - GPT-4o access

**Build:**
- `next.config.ts` - Next.js configuration (minimal, defaults used)
- `tsconfig.json` - TypeScript compiler options
- `eslint.config.mjs` - ESLint rules
- `Anchor.toml` - Solana program deployment config
- `Cargo.toml` (workspace) - Rust workspace configuration
- `pyproject.toml` - Python project metadata + tool configs
- PostCSS + Tailwind CSS config (implicit via Next.js)

**Specific Configs:**
- Prisma schema: `prisma/schema.prisma` - Database models + PostgreSQL provider
- Solana cluster: Anchor configured for `devnet` (deployable to localnet/mainnet)
- Python: Black (100 char line), Ruff (py312 target)
- CORS: Configurable via `CORS_ALLOWED_ORIGINS` env var

## Platform Requirements

**Development:**
- Node.js 18+
- Python 3.12+
- Rust 1.70+ (for smart contract compilation)
- Solana CLI (for deploying anchor programs)
- PostgreSQL 13+ (for development database)
- Git

**Production:**
- Deployment targets:
  - Frontend: Vercel (Next.js optimized)
  - Backend: Railway (Docker-based, Python/Node support)
  - Blockchain: Solana Devnet (fallback to custom RPC endpoints)
  - Database: Railway PostgreSQL or cloud-hosted Postgres
  - Vector DB: Qdrant (self-hosted or managed)

---

*Stack analysis: 2026-03-14*
