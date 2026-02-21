# SOTA SDK Review Findings (2026-02-21)

## Code Duplication
1. Keypair parsing: config.py `get_keypair()` and wallet.py `_parse_keypair()` duplicate identical logic
2. IDL loading: contracts.py and registry.py both have `_load_idl()` and `_get_discriminator()`
   - registry.py delegates to contracts, but _get_discriminator is fully duplicated
3. derive_reputation_pda: exists in both contracts.py and registry.py
4. wrap_* pattern in cost/wrappers.py: 4 functions with near-identical try/except/ImportError structure

## SOLID Violations
- SRP: SOTAAgent handles lifecycle, WS dispatch, job execution, delivery proof, cost signaling
- OCP: Job construction from dicts is hardcoded in _on_job_available and _resolve_job (2 places)
- DIP: agent.py directly imports concrete MarketplaceClient, AgentWallet; no abstraction layer
- ISP: BidStrategy.set_agent_tags() forces all strategies to implement tag injection

## Thread Safety
- CostTracker singleton uses double-checked locking (correct)
- _reserved_jobs set is safe in single-threaded asyncio but no protection if used from executor

## Error Handling Gaps
- _parse_keypair in wallet.py: bare `except Exception` hides real errors
- ToolManager.call: swallows all exceptions, returns JSON error string
- config.py get_keypair: same bare except pattern

## Potential Bugs
- SOTAAgent.tags class default is mutable list [] - defensive copy in __init__ mitigates but subclasses could still share if accessed before instantiation
- _check_rpc_connectivity uses blocking urllib in a function designed to run in executor - OK but could hang thread pool
- MarketplaceClient._heartbeat_loop: if send() raises unexpected exception, heartbeat silently dies
