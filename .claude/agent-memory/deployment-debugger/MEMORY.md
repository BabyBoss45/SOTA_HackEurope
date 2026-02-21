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
