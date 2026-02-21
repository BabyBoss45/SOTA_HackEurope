"""
SOTA Agent SDK Configuration

Loads settings from environment variables with sensible defaults.
Chain config mirrors agents/src/shared/chain_config.py but is self-contained
for the Solana Devnet deployment.
"""

import json
import logging
import os
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from solders.pubkey import Pubkey
from solders.keypair import Keypair

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


# -- Cluster Configuration ----------------------------------------------------

@dataclass
class ClusterConfig:
    """Solana cluster configuration."""
    rpc_url: str
    ws_url: str
    cluster_name: str  # "devnet", "mainnet-beta", "localnet"
    explorer_url: str
    native_currency: str = "SOL"


# Backward-compatible alias
NetworkConfig = ClusterConfig


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
    if cluster in ("mainnet-beta", "mainnet"):
        return SOLANA_MAINNET
    elif cluster in ("localnet", "localhost"):
        return SOLANA_LOCALNET
    return SOLANA_DEVNET


# Backward-compatible alias
get_network = get_cluster


# -- Program / Token Constants ------------------------------------------------

PROGRAM_ID = Pubkey.from_string(
    os.getenv("PROGRAM_ID", "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY")
)

USDC_MINT = Pubkey.from_string(
    os.getenv("USDC_MINT", "9yry7vqkhZGaynE37qX3FYpUqBx8z9n9MFNF8f1FP6Hm")
)

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)

SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")


def get_program_id() -> Pubkey:
    """Get the marketplace program ID."""
    return PROGRAM_ID


# -- Keypair Loading ----------------------------------------------------------

def get_keypair(key_string: Optional[str] = None) -> Optional[Keypair]:
    """
    Parse a Solana Keypair from a string.

    Supports:
      - base58-encoded secret key
      - JSON array of bytes (e.g. from solana-keygen)
      - base64-encoded secret key

    Args:
        key_string: Raw key material. If None, reads SOTA_AGENT_PRIVATE_KEY.

    Returns:
        Keypair or None if no key provided.
    """
    raw = key_string or SOTA_AGENT_PRIVATE_KEY
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
        "Cannot parse keypair. "
        "Provide a base58 string, base64 string, or JSON byte array."
    )


# -- Backward-compatible stubs ------------------------------------------------

@dataclass
class ContractAddresses:
    """Backward-compatible stub. On Solana, addresses are PDAs."""
    order_book: str = ""
    escrow: str = ""
    agent_registry: str = ""
    usdc: str = ""
    reputation_token: str = ""


def get_contract_addresses() -> ContractAddresses:
    """Return a namespace with Solana program/mint addresses for backward compat."""
    return ContractAddresses(
        order_book=str(PROGRAM_ID),
        escrow=str(PROGRAM_ID),
        agent_registry=str(PROGRAM_ID),
        usdc=str(USDC_MINT),
        reputation_token="",
    )
