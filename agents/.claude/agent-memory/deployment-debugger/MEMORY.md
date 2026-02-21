# Deployment Debugger Memory

## Project Structure
- SDK package: `D:/Euro_SOTA/agents/sota_sdk/`
- Core: agent.py, config.py, server.py, models.py, preflight.py, cli.py
- Submodules: chain/ (wallet, contracts, registry), marketplace/ (client, bidding, registration), cost/ (config, wrappers, signals, tracker), tools/ (base, manager), ui/ (app + static)
- Tests: `agents/test_sota_sdk.py` (73 tests), `agents/test_cost_module.py` (43 tests)

## Critical Bug Patterns Found (2026-02-21 audit)
- See `audit-findings.md` for full report
- **websockets v15 breaking change**: `.open` property removed from new ClientConnection class. Code uses `.open` in 4 places in marketplace/client.py. Causes AttributeError at runtime.
- **.env contains real API keys**: ANTHROPIC_API_KEY and SOTA_PAID_API_KEY are hardcoded in committed .env
- **Unhandled coroutine in cli.py cmd_check()**: calls `agent.setup()` synchronously but setup() is async def
- **str(e) leaks exception internals** to hub in _send_job_failed path

## Dependency Versions
- websockets: 15.0.1 installed (pyproject.toml says >=12.0)
- paid-python: 1.0.6 installed
- Python: 3.13
- Chain: Solana Devnet, USDC 6 decimals

## Key Security Notes
- Wallet private key handling in chain/wallet.py is solid (validates format, catches errors, clears reference)
- Wallet address masking in server.py /status endpoint is correct
- WS unencrypted warning implemented
- Agent memory in MEMORY.md should never store real keys
