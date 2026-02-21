# Backend Architect Memory - SOTA Marketplace

## Project Structure
- **Anchor program**: `/anchor/programs/sota_marketplace/src/` (program ID: `F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY`)
- **IDL (JSON)**: `/anchor/target/idl/sota_marketplace.json`
- **IDL (TS types)**: `/anchor/target/types/sota_marketplace.ts`
- **Next.js frontend**: `/mobile_frontend/` (Next.js 15, React 19)
- **Stripe API routes**: `/mobile_frontend/app/api/stripe/{webhook,refund,create-payment-intent}/route.ts`
- **Prisma client**: `/mobile_frontend/src/lib/prisma.ts`

## Key PDA Seeds
- Config: `[b"config"]`
- Job: `[b"job", job_id.to_le_bytes()]`
- Deposit: `[b"deposit", job_id.to_le_bytes()]`
- Escrow vault: `[b"escrow_vault", job_id.to_le_bytes()]`
- Reputation: `[b"reputation", wallet.as_ref()]`
- Agent: `[b"agent", wallet.as_ref()]`
- Bid: `[b"bid", bid_id.to_le_bytes()]`

## Anchor IDL Import Pattern
- Import IDL JSON with `import idl from "../path/to/sota_marketplace.json"` (resolveJsonModule enabled)
- Cast as `idl as any` when passing to `new Program(idl as any, provider)` for generic Idl typing
- Account fetches need `(program.account as any).deposit.fetch(pda)` with explicit type assertion

## Environment Variables (Solana)
- `PLATFORM_PRIVATE_KEY` - base58 or JSON array keypair
- `RPC_URL` / `NEXT_PUBLIC_RPC_URL` - Solana RPC endpoint
- `NEXT_PUBLIC_USDC_MINT` - USDC mint address
- `NEXT_PUBLIC_PROGRAM_ID` - Anchor program ID

## Completed Migrations
- [x] EVM->Solana: Stripe webhook (fund_job), refund, create-payment-intent routes (Feb 2026)
- [x] EVM->Solana: Python backend chain layer (`agents/src/shared/`) - chain_config, chain_contracts, wallet, contracts, config (Feb 2026)

## Python Chain Layer (agents/src/shared/)
- `chain_config.py`: Solana cluster configs, PROGRAM_ID, USDC_MINT, get_keypair(), get_cluster()
- `chain_contracts.py`: Raw solders instruction building (NOT anchorpy Program class), manual Borsh serialization/deserialization, PDA derivation helpers
- `wallet.py`: AgentWallet accepts str|Keypair, uses solders Transaction/Message for SOL/USDC transfers, ed25519 signing
- `contracts.py` / `config.py`: backward-compat re-export wrappers (Contracts=SolanaProgram, NetworkConfig=ClusterConfig)
- Requirements: solana>=0.34.0, solders>=0.21.0, anchorpy>=0.20.0 (removed web3, eth-account)
- get_bids_for_job() scans all bid IDs sequentially -- use getProgramAccounts memcmp filter for production

## EVM->Solana Migration Patterns (Python)
- `Web3.keccak()` -> `hashlib.sha256().digest()`
- Hex addresses (0x...) -> base58 addresses (case-sensitive comparison)
- `chain_id` -> `cluster_name` (devnet/mainnet-beta/localnet)
- `contracts.addresses.escrow` -> `str(PROGRAM_ID)` (single program, PDAs)
- `contracts.account.address` -> `str(contracts.keypair.pubkey())`
- `get_network()` -> `get_cluster()` (alias kept for backward compat)
- Bid data format: tuples `bid[0], bid[2]` -> dicts `bid["id"], bid["agent"]`
- Empty/null address: `"0x0"` -> `"11111111111111111111111111111111"` (system program)
- Provider assignment: `assign_provider(c, id, addr_str)` -> `assign_provider(c, id, Pubkey.from_string(addr))`
- Anchor events: SHA-256("event:<Name>")[:8] discriminator + borsh data in CPI logs ("Program data: " prefix)

## Butler API + Tools Migration (Feb 2026)
- `butler_api.py`: Uses `get_cluster()` not `get_network()`, `hashlib.sha256` not `Web3.keccak`, Solana escrow info returns `program_id`/`usdc_mint`/`cluster` instead of EVM addresses/chain_id
- `butler/tools.py`: PostJobTool uses base58 poster address, program_id instead of escrow_address, system program address as empty sentinel
- AcceptBidTool/GetBidsTool: Bids are dicts (Solana deserialized) not tuples (EVM ABI decoded)

## SDK Migration (Feb 2026)
- `sota_sdk/config.py`: Self-contained ClusterConfig (not NetworkConfig), get_cluster()/get_keypair()
- `sota_sdk/chain/wallet.py`: AgentWallet uses solders Keypair, solana Client, ed25519 signing
- `sota_sdk/chain/contracts.py`: submit_delivery_proof/claim_payment/get_job via raw Anchor instructions
- `sota_sdk/chain/registry.py`: register_agent/is_agent_active via PDA-based agent accounts

## Notes
- Prisma `payment` model types need `npx prisma generate` to resolve - pre-existing issue
- `wagmi`/`viem` imports in frontend components are pre-existing EVM code not yet migrated
- The `refund` instruction requires `authority` = `config.authority` (platform admin signer)
- The `fund_job` instruction inits both `deposit` and `escrow_vault` PDAs (payer = poster)
- Remaining EVM refs outside migration scope: `src/caller/tools.py`, `src/shared/a2a.py`, `src/manager/tools.py`, `src/x402/middleware.py`
