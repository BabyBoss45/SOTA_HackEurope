"""
On-chain agent registration for the SOTA SDK.

Adapted from agents/src/shared/chain_contracts.py (register_agent, is_agent_active).
"""

from __future__ import annotations

import logging
from typing import List

from web3 import Web3

from .wallet import AgentWallet
from .contracts import _get_contract
from ..config import get_contract_addresses

logger = logging.getLogger(__name__)


def _agent_registry(wallet: AgentWallet):
    addr = get_contract_addresses().agent_registry
    if not addr:
        raise ValueError("AGENT_REGISTRY_ADDRESS not configured")
    return _get_contract(wallet, "AgentRegistry", addr)


def register_agent(
    wallet: AgentWallet,
    name: str,
    metadata_uri: str,
    capabilities: List[str],
) -> str:
    """Register as an agent on-chain. Returns tx hash."""
    registry = _agent_registry(wallet)
    fn = registry.functions.registerAgent(name, metadata_uri, capabilities)
    tx_hash = wallet.build_and_send(fn)
    wallet.wait_for_receipt(tx_hash)
    logger.info("Agent registered on-chain | name=%s tx=%s", name, tx_hash)
    return tx_hash


def is_agent_active(wallet: AgentWallet, address: str) -> bool:
    """Check whether an address is a registered active agent."""
    registry = _agent_registry(wallet)
    return registry.functions.isAgentActive(
        Web3.to_checksum_address(address)
    ).call()
