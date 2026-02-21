# Deployment Debugger Memory

## Project Structure
- `agents/sota_sdk/` -- SDK package (Python 3.11+, asyncio-based)
- Core: agent.py, config.py, models.py, server.py, preflight.py, cli.py
- Chain: chain/wallet.py, chain/contracts.py, chain/registry.py
- Marketplace: marketplace/client.py, marketplace/bidding.py, marketplace/registration.py
- Tools: tools/base.py, tools/manager.py
- Cost: cost/config.py, cost/tracker.py, cost/wrappers.py, cost/signals.py
- UI: ui/app.py + static files

## Key Dependencies (installed)
- websockets 15.0.1 (no `.open` attr, use `close_code is None`)
- web3 7.11.0
- Python 3.13

## Audit Status (2026-02-21)
- Full audit completed -- see `audit-findings.md`
- 3 CRITICAL, 6 HIGH, 6 MEDIUM, 3 LOW findings
- Major patterns: shared mutable bid_strategy, time.sleep blocking asyncio, private key in .env via UI, missing ws:// ws_is_open compat edge case

## Common Bug Patterns
- `time.sleep()` inside `build_and_send()` blocks the thread (acceptable since called via run_in_executor)
- Mutable class attributes on SOTAAgent subclasses (bid_strategy shared between instances)
- UI endpoint writes private key into generated .env files
- `_ws_is_open()` correctly handles websockets v15 close_code check
