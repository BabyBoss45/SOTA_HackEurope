"""
On-chain agent registration for the SOTA SDK.

Adapted from agents/src/shared/chain_contracts.py (register_agent, is_agent_active).
Migrated from EVM/Web3 to Solana/Anchor.
"""

from __future__ import annotations

import json
import logging
import struct
from typing import List

from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta

from .wallet import AgentWallet
from ..config import PROGRAM_ID

logger = logging.getLogger(__name__)


# -- PDA Derivation -----------------------------------------------------------

def _derive_agent_pda(wallet: Pubkey, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive an Agent PDA: seeds = [b"agent", wallet.as_ref()]"""
    return Pubkey.find_program_address(
        [b"agent", bytes(wallet)], program_id
    )


def _derive_reputation_pda(wallet: Pubkey, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Reputation PDA: seeds = [b"reputation", wallet.as_ref()]"""
    return Pubkey.find_program_address(
        [b"reputation", bytes(wallet)], program_id
    )


# -- Encoding helpers ----------------------------------------------------------

def _encode_string(s: str) -> bytes:
    """Anchor-compatible string encoding: 4-byte LE length prefix + UTF-8 bytes."""
    encoded = s.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def _encode_vec_string(strings: list[str]) -> bytes:
    """Anchor-compatible Vec<String> encoding."""
    data = struct.pack("<I", len(strings))
    for s in strings:
        data += _encode_string(s)
    return data


# -- IDL helpers ---------------------------------------------------------------

def _load_idl() -> dict:
    """Load IDL (reuses the contracts module cache)."""
    from .contracts import _load_idl as _contracts_load_idl
    return _contracts_load_idl()


def _get_discriminator(idl: dict, ix_name: str) -> bytes:
    """Get the 8-byte instruction discriminator."""
    for ix in idl["instructions"]:
        if ix["name"] == ix_name:
            return bytes(ix["discriminator"])
    raise ValueError(f"Instruction '{ix_name}' not found in IDL")


# -- Registration --------------------------------------------------------------

def register_agent(
    wallet: AgentWallet,
    name: str,
    metadata_uri: str,
    capabilities: List[str],
) -> str:
    """
    Register as an agent on-chain.

    Args:
        wallet: Agent's wallet (signer and payer).
        name: Agent display name.
        metadata_uri: URI to agent metadata.
        capabilities: List of capability strings.

    Returns: transaction signature string.
    """
    if not wallet.address:
        raise ValueError("Wallet has no address -- private key required for registration")

    agent_wallet_pk = wallet.pubkey
    agent_pda, _ = _derive_agent_pda(agent_wallet_pk)
    reputation_pda, _ = _derive_reputation_pda(agent_wallet_pk)

    idl = _load_idl()
    disc = _get_discriminator(idl, "register_agent")
    ix_data = disc + _encode_string(name) + _encode_string(metadata_uri) + _encode_vec_string(capabilities)

    accounts = [
        AccountMeta(pubkey=agent_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=reputation_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=agent_wallet_pk, is_signer=False, is_writable=False),
        AccountMeta(pubkey=agent_wallet_pk, is_signer=True, is_writable=True),  # developer = wallet
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(PROGRAM_ID, ix_data, accounts)
    sig = wallet.build_and_send(ix)
    wallet.confirm_transaction(sig)
    logger.info("Agent registered on-chain | name=%s sig=%s", name, sig)
    return sig


def is_agent_active(wallet: AgentWallet, address: str) -> bool:
    """
    Check whether an address is a registered active agent.

    Args:
        wallet: Any wallet (used only for RPC access).
        address: Base58 public key string of the agent to check.

    Returns: True if the agent is registered and active.
    """
    agent_pk = Pubkey.from_string(address)
    agent_pda, _ = _derive_agent_pda(agent_pk)

    resp = wallet.client.get_account_info(agent_pda, commitment=Confirmed)
    if resp.value is None:
        return False

    data = bytes(resp.value.data)
    # Parse to find the status byte.
    # Layout after 8-byte discriminator:
    #   wallet(32) + developer(32) + name(4+N) + metadata_uri(4+N) + capabilities(4+N*var) + reputation(8) + status(1)
    offset = 8  # skip discriminator
    offset += 32  # wallet
    offset += 32  # developer
    # skip name string
    name_len = struct.unpack_from("<I", data, offset)[0]; offset += 4 + name_len
    # skip metadata_uri string
    uri_len = struct.unpack_from("<I", data, offset)[0]; offset += 4 + uri_len
    # skip capabilities vec
    cap_count = struct.unpack_from("<I", data, offset)[0]; offset += 4
    for _ in range(cap_count):
        s_len = struct.unpack_from("<I", data, offset)[0]; offset += 4 + s_len
    # skip reputation u64
    offset += 8
    # status byte
    status = data[offset]
    return status == 1  # AgentStatus::Active = 1
