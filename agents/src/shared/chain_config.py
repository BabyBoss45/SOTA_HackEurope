"""
Chain Configuration for SOTA Agents

Base Sepolia (testnet) and Base mainnet.
Loads contract addresses from deployment JSON or env vars.
"""

import os
import json
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load from project root .env (single source of truth)
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_root_env)


# ─── Network Definitions ─────────────────────────────────────

@dataclass
class NetworkConfig:
    """Blockchain network configuration"""
    rpc_url: str
    chain_id: int
    explorer_url: str
    native_currency: str = "ETH"


@dataclass
class ContractAddresses:
    """Deployed contract addresses"""
    order_book: str = ""
    escrow: str = ""
    agent_registry: str = ""
    usdc: str = ""
    reputation_token: str = ""


@dataclass
class AgentEndpoints:
    """A2A endpoint URLs for each agent"""
    manager: str = "http://localhost:3001"
    caller: str = "http://localhost:3003"
    hackathon: str = "http://localhost:3005"


# ─── Networks ────────────────────────────────────────────────

BASE_SEPOLIA = NetworkConfig(
    rpc_url=os.getenv("RPC_URL", "https://sepolia.base.org"),
    chain_id=84532,
    explorer_url="https://sepolia.basescan.org",
    native_currency="ETH",
)

BASE_MAINNET = NetworkConfig(
    rpc_url="https://mainnet.base.org",
    chain_id=8453,
    explorer_url="https://basescan.org",
    native_currency="ETH",
)

HARDHAT_LOCAL = NetworkConfig(
    rpc_url="http://127.0.0.1:8545",
    chain_id=31337,
    explorer_url="",
    native_currency="ETH",
)


def get_network() -> NetworkConfig:
    """Get the current network configuration based on CHAIN_ID env."""
    chain_id = int(os.getenv("CHAIN_ID", "84532"))
    if chain_id == 8453:
        return BASE_MAINNET
    elif chain_id == 31337:
        return HARDHAT_LOCAL
    return BASE_SEPOLIA


def get_contract_addresses() -> ContractAddresses:
    """
    Load contract addresses from env vars or the deployment JSON.
    Tries the latest deployment file matching the current chain ID.
    """
    # Try env vars first
    order_book = os.getenv("ORDERBOOK_ADDRESS")
    if order_book:
        return ContractAddresses(
            order_book=order_book,
            escrow=os.getenv("ESCROW_ADDRESS", ""),
            agent_registry=os.getenv("AGENT_REGISTRY_ADDRESS", ""),
            usdc=os.getenv("USDC_ADDRESS", ""),
            reputation_token=os.getenv("REPUTATION_TOKEN_ADDRESS", ""),
        )

    # Try deployment file
    network = get_network()
    deployment_names = [
        f"base-sepolia-{network.chain_id}.json",
        f"hardhat-local-{network.chain_id}.json",
        f"base-mainnet-{network.chain_id}.json",
    ]

    contracts_dir = Path(__file__).parent.parent.parent.parent / "contracts" / "deployments"
    for name in deployment_names:
        path = contracts_dir / name
        if path.exists():
            with open(path) as f:
                c = json.load(f).get("contracts", {})
                return ContractAddresses(
                    order_book=c.get("OrderBook", ""),
                    escrow=c.get("Escrow", ""),
                    agent_registry=c.get("AgentRegistry", ""),
                    usdc=c.get("USDC", ""),
                    reputation_token=c.get("ReputationToken", ""),
                )

    # Empty fallback
    return ContractAddresses()


def get_agent_endpoints() -> AgentEndpoints:
    """Get agent A2A endpoints from environment."""
    return AgentEndpoints(
        manager=os.getenv("MANAGER_ENDPOINT", "http://localhost:3001"),
        caller=os.getenv("CALLER_ENDPOINT", "http://localhost:3003"),
        hackathon=os.getenv("HACKATHON_ENDPOINT", "http://localhost:3005"),
    )


# ─── Job / Agent Types ───────────────────────────────────────

class JobType(IntEnum):
    """Job types supported by SOTA agents"""
    HOTEL_BOOKING = 0
    RESTAURANT_BOOKING = 1
    HACKATHON_REGISTRATION = 2
    COMPOSITE = 3
    CALL_VERIFICATION = 5
    GENERIC = 6
    JOB_SCOURING = 7


JOB_TYPE_LABELS = {
    JobType.HOTEL_BOOKING: "Hotel Booking",
    JobType.RESTAURANT_BOOKING: "Restaurant Booking",
    JobType.HACKATHON_REGISTRATION: "Hackathon Registration",
    JobType.COMPOSITE: "Composite Task",
    JobType.CALL_VERIFICATION: "Call Verification",
    JobType.GENERIC: "Generic Task",
    JobType.JOB_SCOURING: "Job Scouring",
}


AGENT_CAPABILITIES = {
    "BUTLER": ["job_planning", "agent_coordination", "user_interaction"],
    "CALLER": ["phone_call", "voice_verification", "reservation_booking"],
    "HACKATHON": ["hackathon_search", "web_scraping", "event_filtering"],
}


def get_private_key(agent_type: str = "butler") -> Optional[str]:
    """Get the private key for a specific agent type."""
    key_map = {
        "butler": "PRIVATE_KEY",
        "worker": "WORKER_PRIVATE_KEY",
        "caller": "CALLER_PRIVATE_KEY",
        "hackathon": "HACKATHON_PRIVATE_KEY",
    }
    env_var = key_map.get(agent_type.lower(), "PRIVATE_KEY")
    return os.getenv(env_var)
