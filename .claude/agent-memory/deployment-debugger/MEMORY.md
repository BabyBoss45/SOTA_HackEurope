# Deployment Debugger Memory

## Project Structure
- `agents/sota_sdk/` -- SDK package (Python 3.11+, asyncio-based)
- Core: agent.py, config.py, models.py, server.py, preflight.py, cli.py
- Chain: chain/wallet.py, chain/contracts.py, chain/registry.py
- Marketplace: marketplace/client.py, marketplace/bidding.py, marketplace/registration.py
- Tools: tools/base.py, tools/manager.py
- Cost: cost/config.py, cost/tracker.py, cost/wrappers.py, cost/signals.py
- UI: ui/app.py + static files
- **Frontend**: Next.js app in `app/` dir, API routes in `app/api/`
- **Validators**: `src/lib/validators.ts` (Zod schemas)
- **Prisma schema**: `prisma/schema.prisma`

## Key Dependencies (installed)
- websockets 15.0.1 (no `.open` attr, use `close_code is None`)
- web3 7.11.0
- Python 3.13
- Next.js (App Router), Prisma (PostgreSQL), Zod

## Audit Status

### Python SDK audit (2026-02-21)
- Full audit completed -- see `audit-findings.md`
- 3 CRITICAL, 6 HIGH, 6 MEDIUM, 3 LOW findings
- Major patterns: shared mutable bid_strategy, time.sleep blocking asyncio, private key in .env via UI

### Frontend/API audit (2026-02-21)
- Audited: validators.ts, agents/route.ts, agents/[id]/route.ts, developers/page.tsx, deploy/page.tsx
- 2 CRITICAL, 6 HIGH, 5 MEDIUM, 3 LOW
- Key issues: Zod rejects empty string for optional regex fields, PATCH has zero validation, parseFloat("") = NaN, JSON.parse without try/catch

### Butler API + Marketplace Hub audit (2026-02-21)
- Audited: butler_api.py, marketplace/hub.py, marketplace/bidding.py, marketplace/registry.py, marketplace/router.py, marketplace/models.py
- 0 CRITICAL, 7 HIGH, 8 MEDIUM, 3 LOW
- Major patterns: blocking Solana RPC in async handlers, UnboundLocalError on provider_pk, SSE endpoint hardcodes hackathon formatting, double CORS middleware

### Agent fleet audit (2026-02-21)
- Audited: run_all.py, hub_connector.py, base_agent.py, all 7 agent modules, auto_bidder.py
- 2 CRITICAL, 6 HIGH, 7 MEDIUM, 3 LOW
- **BLOCKER**: JobType enum in chain_config.py missing 5 members (GIFT_SUGGESTION, REFUND_CLAIM, RESTAURANT_BOOKING_SMART, SMART_SHOPPING, TRIP_PLANNING) -- 5/7 agents fail to boot
- Hardcoded phone number in caller agent (+447553293952)
- `or True` dead code in /agents endpoint status field
- hub_connector leaks exception details to hub, heartbeat swallows CancelledError
- base_agent.start() event_listener.start() called outside null-check if block

## Common Bug Patterns
- Zod `z.string().regex().optional()` rejects `""` -- use `.transform()` or coerce on frontend
- PATCH /api/agents/[id] has NO validation -- raw body to Prisma
- `parseFloat("")` returns NaN -- always add `|| 0` fallback
- `JSON.parse(agent.capabilities)` without try/catch crashes components
- Inconsistent null vs empty string between Register Modal and Deploy page
- `apiEndpoint` required in Zod but nullable (`String?`) in Prisma
- `time.sleep()` in build_and_send() acceptable (run_in_executor)
- Mutable class attributes on SOTAAgent subclasses (bid_strategy shared)
- UI endpoint writes private key into generated .env files
- `_ws_is_open()` correctly handles websockets v15 close_code check
- Blocking Solana RPC in async FastAPI handlers -- always wrap in run_in_executor
- Sub-app CORS middleware is independent from parent -- remove or unify
- SSE endpoint should dispatch formatting by worker type, not hardcode hackathon
- JobType IntEnum must contain ALL types agents reference (5 were missing)
- JOB_TYPE_TAGS dict must have entries for all JobType values or fallback produces wrong tags
- Agent description parsing (split on ", " and "=") breaks on values containing those chars
- hub_connector._job_cache grows unbounded if hub never responds to bids
- base_agent._execute_job_task sleeps 60s before cleanup, reducing effective capacity
