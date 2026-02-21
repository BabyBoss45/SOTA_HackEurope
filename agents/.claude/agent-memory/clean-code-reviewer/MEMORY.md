# SOTA SDK Clean Code Review Memory

## Project Structure
- SDK root: `D:\SOTA_HackEurope\agents\sota_sdk\`
- Modules: agent, config, models, server, preflight, cli, marketplace/, chain/, tools/, cost/
- Language: Python 3.12, async-first
- Blockchain: Solana (migrated from EVM), uses solders/solana-py/spl-token
- Dependencies: FastAPI, websockets, Pydantic v2, uvicorn, paid-python (optional)

## Architectural Pattern
- SOTAAgent is a monolithic base class (~600 lines) combining lifecycle, WS dispatch, execution, and delivery
- Strategy pattern for bidding (BidStrategy ABC)
- Singleton pattern for CostTracker
- MarketplaceClient uses event handler registration (observer-like)

## Key Patterns & Conventions
- Dataclasses for models (Job, Bid, BidResult, JobResult)
- Pydantic BaseModel for tools (BaseTool)
- `from __future__ import annotations` used consistently
- Module-level logger = logging.getLogger(__name__) everywhere
- Config loaded from env vars at module import time

## Known Issues (from 2026-02-21 review)
- See `D:\SOTA_HackEurope\agents\.claude\agent-memory\clean-code-reviewer\review-findings.md` for detailed findings
- Key: keypair parsing duplicated in config.py and wallet.py
- Key: _get_discriminator and _load_idl duplicated in contracts.py and registry.py
- Key: SOTAAgent violates SRP (lifecycle + WS dispatch + execution + delivery in one class)
- Key: Mutable class-level defaults (tags=[]) on SOTAAgent
