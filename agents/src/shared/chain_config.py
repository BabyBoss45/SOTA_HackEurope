"""
Chain Configuration for SOTA Agents

Solana Devnet and Mainnet-Beta.
Loads program ID and keypair from env vars.
"""

import os
import json
import base64
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from solders.pubkey import Pubkey
from solders.keypair import Keypair

# Load from project root .env (single source of truth)
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_root_env)


# ---- Network Definitions ------------------------------------------------

@dataclass
class ClusterConfig:
    """Solana cluster configuration"""
    rpc_url: str
    ws_url: str
    cluster_name: str  # "devnet", "mainnet-beta", "localnet"
    explorer_url: str
    native_currency: str = "SOL"


@dataclass
class AgentEndpoints:
    """A2A endpoint URLs for each agent"""
    manager: str = "http://localhost:3001"
    caller: str = "http://localhost:3003"
    hackathon: str = "http://localhost:3005"


# ---- Clusters ------------------------------------------------------------

SOLANA_DEVNET = ClusterConfig(
    rpc_url=os.getenv("RPC_URL", "https://api.devnet.solana.com"),
    ws_url=os.getenv("WS_URL", "wss://api.devnet.solana.com"),
    cluster_name="devnet",
    explorer_url="https://explorer.solana.com/?cluster=devnet",
)

SOLANA_MAINNET = ClusterConfig(
    rpc_url="https://api.mainnet-beta.solana.com",
    ws_url="wss://api.mainnet-beta.solana.com",
    cluster_name="mainnet-beta",
    explorer_url="https://explorer.solana.com",
)

SOLANA_LOCALNET = ClusterConfig(
    rpc_url="http://127.0.0.1:8899",
    ws_url="ws://127.0.0.1:8900",
    cluster_name="localnet",
    explorer_url="",
)


def get_cluster() -> ClusterConfig:
    """Get the current cluster configuration based on SOLANA_CLUSTER env."""
    cluster = os.getenv("SOLANA_CLUSTER", "devnet").lower()
    if cluster == "mainnet-beta" or cluster == "mainnet":
        return SOLANA_MAINNET
    elif cluster == "localnet" or cluster == "localhost":
        return SOLANA_LOCALNET
    return SOLANA_DEVNET


# Backward-compatible alias
get_network = get_cluster


def get_rpc_url() -> str:
    """Get the RPC URL for the current cluster."""
    return get_cluster().rpc_url


# ---- Program ID ----------------------------------------------------------

PROGRAM_ID = Pubkey.from_string(
    os.getenv("PROGRAM_ID", "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY")
)


def get_program_id() -> Pubkey:
    """Get the marketplace program ID."""
    return PROGRAM_ID


# ---- USDC Mint -----------------------------------------------------------

# Devnet USDC mint (Circle devnet faucet) -- override via env
USDC_MINT = Pubkey.from_string(
    os.getenv("USDC_MINT", "9yry7vqkhZGaynE37qX3FYpUqBx8z9n9MFNF8f1FP6Hm")
)

# SPL Token Program ID (constant)
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Associated Token Account Program ID (constant)
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)

# System Program ID (constant)
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")

# Sysvar Rent
SYSVAR_RENT_PUBKEY = Pubkey.from_string("SysvarRent111111111111111111111111111111111")


# ---- Keypair Loading -----------------------------------------------------

def get_keypair(agent_type: str = "butler") -> Optional[Keypair]:
    """
    Load a Solana Keypair from env var.

    Supports two formats:
      - base58-encoded secret key string
      - JSON array of bytes (e.g. from solana-keygen)

    Args:
        agent_type: One of 'butler', 'worker', 'caller', 'hackathon'.

    Returns:
        Keypair or None if the env var is not set.
    """
    key_map = {
        "butler": "PRIVATE_KEY",
        "worker": "WORKER_PRIVATE_KEY",
        "caller": "CALLER_PRIVATE_KEY",
        "hackathon": "HACKATHON_PRIVATE_KEY",
    }
    env_var = key_map.get(agent_type.lower(), "PRIVATE_KEY")
    raw = os.getenv(env_var)
    if not raw:
        return None

    raw = raw.strip()

    # Try JSON array first: [12, 34, 56, ...]
    if raw.startswith("["):
        try:
            byte_list = json.loads(raw)
            return Keypair.from_bytes(bytes(byte_list))
        except (json.JSONDecodeError, ValueError, OverflowError):
            pass

    # Try base58
    try:
        return Keypair.from_base58_string(raw)
    except Exception:
        pass

    # Try base64
    try:
        decoded = base64.b64decode(raw)
        return Keypair.from_bytes(decoded)
    except Exception:
        pass

    raise ValueError(
        f"Cannot parse keypair from env var {env_var}. "
        "Provide a base58 string, base64 string, or JSON byte array."
    )


# Backward-compatible alias
def get_private_key(agent_type: str = "butler") -> Optional[str]:
    """Get the raw private key string from env (for backward compat)."""
    key_map = {
        "butler": "PRIVATE_KEY",
        "worker": "WORKER_PRIVATE_KEY",
        "caller": "CALLER_PRIVATE_KEY",
        "hackathon": "HACKATHON_PRIVATE_KEY",
    }
    env_var = key_map.get(agent_type.lower(), "PRIVATE_KEY")
    return os.getenv(env_var)


def get_agent_endpoints() -> AgentEndpoints:
    """Get agent A2A endpoints from environment."""
    return AgentEndpoints(
        manager=os.getenv("MANAGER_ENDPOINT", "http://localhost:3001"),
        caller=os.getenv("CALLER_ENDPOINT", "http://localhost:3003"),
        hackathon=os.getenv("HACKATHON_ENDPOINT", "http://localhost:3005"),
    )


# ---- Job / Agent Types ---------------------------------------------------

class JobType(IntEnum):
    """Job types supported by SOTA agents"""
    HOTEL_BOOKING = 0
    RESTAURANT_BOOKING = 1
    HACKATHON_REGISTRATION = 2
    COMPOSITE = 3
    CALL_VERIFICATION = 5
    GENERIC = 6
    JOB_SCOURING = 7
    FUN_ACTIVITY = 8


JOB_TYPE_LABELS = {
    JobType.HOTEL_BOOKING: "Hotel Booking",
    JobType.RESTAURANT_BOOKING: "Restaurant Booking",
    JobType.HACKATHON_REGISTRATION: "Hackathon Registration",
    JobType.COMPOSITE: "Composite Task",
    JobType.CALL_VERIFICATION: "Call Verification",
    JobType.GENERIC: "Generic Task",
    JobType.JOB_SCOURING: "Job Scouring",
    JobType.FUN_ACTIVITY: "Fun Activity",
}


AGENT_CAPABILITIES = {
    "BUTLER": ["job_planning", "agent_coordination", "user_interaction"],
    "CALLER": ["phone_call", "voice_verification", "reservation_booking"],
    "HACKATHON": ["hackathon_search", "web_scraping", "event_filtering"],
    "FUN_ACTIVITY": ["event_search", "preference_learning", "weather_adaptation", "confidence_inference"],
    "COMPETITOR_FUN": ["nightlife_search", "vibe_analysis", "adventure_profiling", "spontaneous_discovery"],
}
