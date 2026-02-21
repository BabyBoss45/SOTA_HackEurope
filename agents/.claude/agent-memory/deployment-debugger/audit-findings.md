# Audit Findings — 2026-02-21

## CRITICAL
1. websockets v15 .open AttributeError (marketplace/client.py) — 4 call sites
2. .env committed with real API keys (ANTHROPIC_API_KEY, SOTA_PAID_API_KEY)

## HIGH
3. cli.py cmd_check() calls async setup() synchronously — returns coroutine, never awaits
4. str(e) exception leak in _send_job_failed (agent.py:465)

## MEDIUM
5. preflight _check_rpc_connectivity() blocks event loop (urllib.request.urlopen)
6. time.sleep(1) in wallet.py build_and_send — blocks event loop when called from run_in_executor (acceptable since it IS in executor, but worth noting)
7. websockets.WebSocketClientProtocol type annotation deprecated in v15

## LOW
8. custom_bid_agent.py shared mutable class attr bid_strategy (shared HighValueOnlyStrategy instance)
9. No CORS headers on UI API endpoints
