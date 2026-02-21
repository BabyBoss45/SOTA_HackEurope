"""
Config -- Re-exports from chain_config for backward compatibility.

All agent modules should import from here or from chain_config directly.
The chain layer has been migrated from EVM (Base Sepolia) to Solana Devnet.
"""

# Re-export everything from chain_config so existing
# `from ..shared.config import ...` imports keep working.
from .chain_config import *  # noqa: F401,F403
from .chain_config import (
    ClusterConfig,
    AgentEndpoints,
    SOLANA_DEVNET,
    SOLANA_MAINNET,
    SOLANA_LOCALNET,
    get_cluster,
    get_network,
    get_rpc_url,
    get_agent_endpoints,
    get_keypair,
    get_private_key,
    get_program_id,
    PROGRAM_ID,
    USDC_MINT,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    SYSVAR_RENT_PUBKEY,
    JobType,
    JOB_TYPE_LABELS,
    AGENT_CAPABILITIES,
)

# Backward-compatible aliases — do not use in new code
NetworkConfig = ClusterConfig
BASE_SEPOLIA = SOLANA_DEVNET   # deprecated: use SOLANA_DEVNET
BASE_MAINNET = SOLANA_MAINNET  # deprecated: use SOLANA_MAINNET
HARDHAT_LOCAL = SOLANA_LOCALNET  # deprecated: use SOLANA_LOCALNET


def get_contract_addresses():
    """
    Backward-compatible stub. Returns a namespace-like object
    so old code doing `get_contract_addresses().order_book` does not crash.

    On Solana, there is a single program ID. Contract addresses are PDAs.
    """
    class _SolanaAddresses:
        order_book = str(PROGRAM_ID)
        escrow = str(PROGRAM_ID)
        agent_registry = str(PROGRAM_ID)
        usdc = str(USDC_MINT)
        reputation_token = None
    return _SolanaAddresses()


# Legacy alias used by EVM code
ContractAddresses = type(get_contract_addresses())
