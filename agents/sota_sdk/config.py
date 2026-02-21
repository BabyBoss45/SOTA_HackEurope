"""
SOTA Agent SDK Configuration

Loads settings from environment variables with sensible defaults.
Chain config mirrors agents/src/shared/chain_config.py but is self-contained.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

# Load .env -- search up from cwd so it works both in-tree and when pip-installed
load_dotenv(find_dotenv(usecwd=True))


# -- SDK Settings -------------------------------------------------------------

SOTA_MARKETPLACE_URL: str = os.getenv(
    "SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"
)
SOTA_AGENT_PRIVATE_KEY: Optional[str] = os.getenv("SOTA_AGENT_PRIVATE_KEY")

# Heartbeat interval (seconds) for the WS connection
WS_HEARTBEAT_INTERVAL: int = int(os.getenv("SOTA_WS_HEARTBEAT", "30"))

# Reconnect delay bounds (seconds)
WS_RECONNECT_MIN: float = float(os.getenv("SOTA_WS_RECONNECT_MIN", "1"))
WS_RECONNECT_MAX: float = float(os.getenv("SOTA_WS_RECONNECT_MAX", "60"))


# -- Network -------------------------------------------------------------------

@dataclass
class NetworkConfig:
    rpc_url: str
    chain_id: int
    explorer_url: str
    native_currency: str = "ETH"


@dataclass
class ContractAddresses:
    order_book: str = ""
    escrow: str = ""
    agent_registry: str = ""
    usdc: str = ""


BASE_SEPOLIA = NetworkConfig(
    rpc_url=os.getenv("RPC_URL", "https://sepolia.base.org"),
    chain_id=84532,
    explorer_url="https://sepolia.basescan.org",
)

BASE_MAINNET = NetworkConfig(
    rpc_url=os.getenv("RPC_URL_MAINNET", "https://mainnet.base.org"),
    chain_id=8453,
    explorer_url="https://basescan.org",
)

HARDHAT_LOCAL = NetworkConfig(
    rpc_url=os.getenv("RPC_URL_LOCAL", "http://127.0.0.1:8545"),
    chain_id=31337,
    explorer_url="",
)


def get_network() -> NetworkConfig:
    """Current network based on CHAIN_ID env."""
    chain_id = int(os.getenv("CHAIN_ID", "84532"))
    if chain_id == 8453:
        return BASE_MAINNET
    if chain_id == 31337:
        return HARDHAT_LOCAL
    return BASE_SEPOLIA


def get_contract_addresses() -> ContractAddresses:
    """Load contract addresses from env vars or deployment JSON."""
    order_book = os.getenv("ORDERBOOK_ADDRESS")
    if order_book:
        return ContractAddresses(
            order_book=order_book,
            escrow=os.getenv("ESCROW_ADDRESS", ""),
            agent_registry=os.getenv("AGENT_REGISTRY_ADDRESS", ""),
            usdc=os.getenv("USDC_ADDRESS", ""),
        )

    # Allow explicit override of the contracts directory
    contracts_dir = Path(
        os.getenv(
            "SOTA_CONTRACTS_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "contracts" / "deployments"),
        )
    )

    network = get_network()
    for name in [
        f"base-sepolia-{network.chain_id}.json",
        f"hardhat-local-{network.chain_id}.json",
        f"base-mainnet-{network.chain_id}.json",
    ]:
        path = contracts_dir / name
        if path.exists():
            try:
                with open(path) as f:
                    c = json.load(f).get("contracts", {})
                    return ContractAddresses(
                        order_book=c.get("OrderBook", ""),
                        escrow=c.get("Escrow", ""),
                        agent_registry=c.get("AgentRegistry", ""),
                        usdc=c.get("USDC", ""),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse deployment file %s: %s", path, e)
                continue

    return ContractAddresses()
