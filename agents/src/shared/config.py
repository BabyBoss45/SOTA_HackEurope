"""
Config — Re-exports from chain_config for backward compatibility.

All agent modules should import from here or from chain_config directly.
"""

# Re-export everything from chain_config so existing
# `from ..shared.config import ...` imports keep working.
from .chain_config import *  # noqa: F401,F403
from .chain_config import (
    NetworkConfig,
    ContractAddresses,
    AgentEndpoints,
    BASE_SEPOLIA,
    BASE_MAINNET,
    HARDHAT_LOCAL,
    get_network,
    get_contract_addresses,
    get_agent_endpoints,
    JobType,
    JOB_TYPE_LABELS,
    AGENT_CAPABILITIES,
    get_private_key,
)
