"""
On-chain helpers for the SOTA SDK.

Adapted from agents/src/shared/chain_contracts.py.
Provides: submit_delivery_proof, claim_payment, get_job.

Migrated from EVM/Web3 to Solana/Anchor. Uses the shared chain_contracts
module for low-level instruction building where possible, and provides
simplified SDK-facing wrappers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from pathlib import Path
from typing import Optional

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta
from spl.token.instructions import get_associated_token_address

from ..config import (
    get_cluster,
    get_program_id,
    PROGRAM_ID,
    USDC_MINT,
    TOKEN_PROGRAM_ID,
)
from .wallet import AgentWallet

logger = logging.getLogger(__name__)


# -- IDL Loading ---------------------------------------------------------------

# Try multiple IDL locations: local agents copy first, then anchor build output
_AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent
_IDL_CANDIDATES = [
    _AGENTS_ROOT / "sota_marketplace_idl.json",                          # Docker / agents dir
    _AGENTS_ROOT.parent / "anchor" / "target" / "idl" / "sota_marketplace.json",  # Local dev
]
_IDL_PATH = next((p for p in _IDL_CANDIDATES if p.exists()), _IDL_CANDIDATES[0])

_idl_cache: Optional[dict] = None


def _load_idl() -> dict:
    """Load the Anchor IDL JSON for sota_marketplace."""
    global _idl_cache
    if _idl_cache is not None:
        return _idl_cache
    if not _IDL_PATH.exists():
        raise FileNotFoundError(
            f"IDL not found at {_IDL_PATH}. "
            "Run `anchor build` in the anchor/ directory first."
        )
    with open(_IDL_PATH) as f:
        _idl_cache = json.load(f)
    return _idl_cache


def _get_discriminator(idl: dict, ix_name: str) -> bytes:
    """Get the 8-byte instruction discriminator from the IDL."""
    for ix in idl["instructions"]:
        if ix["name"] == ix_name:
            return bytes(ix["discriminator"])
    raise ValueError(f"Instruction '{ix_name}' not found in IDL")


# -- PDA Derivation -----------------------------------------------------------

def derive_job_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Job PDA: seeds = [b"job", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"job", struct.pack("<Q", job_id)], program_id
    )


def derive_deposit_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Deposit PDA: seeds = [b"deposit", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"deposit", struct.pack("<Q", job_id)], program_id
    )


def derive_config_pda(program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive the MarketplaceConfig PDA: seeds = [b"config"]"""
    return Pubkey.find_program_address([b"config"], program_id)


def derive_escrow_vault_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive the EscrowVault PDA: seeds = [b"escrow_vault", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"escrow_vault", struct.pack("<Q", job_id)], program_id
    )


def derive_reputation_pda(wallet: Pubkey, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Reputation PDA: seeds = [b"reputation", wallet.as_ref()]"""
    return Pubkey.find_program_address(
        [b"reputation", bytes(wallet)], program_id
    )


# -- Account Deserialization ---------------------------------------------------

def _deserialize_string(data: bytes, offset: int) -> tuple[str, int]:
    """Deserialize an Anchor string (4-byte LE len + UTF-8)."""
    length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    s = data[offset:offset+length].decode("utf-8")
    offset += length
    return s, offset


def _deserialize_job(data: bytes) -> dict:
    """Deserialize a Job account from raw bytes (after 8-byte discriminator)."""
    offset = 8
    job_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    poster = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    provider = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    metadata_uri, offset = _deserialize_string(data, offset)
    max_budget_usdc = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    deadline = struct.unpack_from("<q", data, offset)[0]; offset += 8
    status = data[offset]; offset += 1
    delivery_proof = data[offset:offset+32]; offset += 32
    created_at = struct.unpack_from("<q", data, offset)[0]; offset += 8
    accepted_bid_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "id": job_id,
        "poster": str(poster),
        "provider": str(provider),
        "metadata_uri": metadata_uri,
        "budget_usdc": max_budget_usdc / 1e6,
        "max_budget_usdc_raw": max_budget_usdc,
        "deadline": deadline,
        "status": status,
        "delivery_proof": delivery_proof.hex(),
        "created_at": created_at,
        "accepted_bid_id": accepted_bid_id,
        "bump": bump,
    }


def _deserialize_deposit(data: bytes) -> dict:
    """Deserialize a Deposit account from raw bytes."""
    offset = 8
    job_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    poster = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    provider = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    amount = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    funded = bool(data[offset]); offset += 1
    released = bool(data[offset]); offset += 1
    refunded = bool(data[offset]); offset += 1
    delivery_confirmed = bool(data[offset]); offset += 1
    delivery_confirmed_at = struct.unpack_from("<q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "job_id": job_id,
        "poster": str(poster),
        "provider": str(provider),
        "amount_usdc": amount / 1e6,
        "amount_raw": amount,
        "funded": funded,
        "released": released,
        "refunded": refunded,
        "delivery_confirmed": delivery_confirmed,
        "delivery_confirmed_at": delivery_confirmed_at,
        "bump": bump,
    }


# -- Transaction Helpers -------------------------------------------------------

def _send_tx(wallet: AgentWallet, ix: Instruction, retries: int = 3) -> str:
    """Build, sign, and send a transaction. Returns tx signature string."""
    return wallet.build_and_send(ix, retries=retries)


# -- Job Queries ---------------------------------------------------------------

def get_job(wallet: AgentWallet, job_id: int) -> dict:
    """Fetch and deserialize a Job account by job_id."""
    job_pda, _ = derive_job_pda(job_id)
    resp = wallet.client.get_account_info(job_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Job account not found for job_id={job_id}")
    return _deserialize_job(bytes(resp.value.data))


def get_escrow_deposit(wallet: AgentWallet, job_id: int) -> dict:
    """Fetch and deserialize a Deposit account by job_id."""
    deposit_pda, _ = derive_deposit_pda(job_id)
    resp = wallet.client.get_account_info(deposit_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Deposit account not found for job_id={job_id}")
    return _deserialize_deposit(bytes(resp.value.data))


def is_delivery_confirmed(wallet: AgentWallet, job_id: int) -> bool:
    """Check if delivery has been confirmed for a job."""
    try:
        deposit = get_escrow_deposit(wallet, job_id)
        return deposit["delivery_confirmed"]
    except ValueError:
        return False


# -- Delivery Proof -------------------------------------------------------------

def submit_delivery_proof(
    wallet: AgentWallet, job_id: int, proof_hash: bytes
) -> str:
    """
    Mark a job as completed on-chain with a delivery proof hash.

    Args:
        wallet: Agent's wallet (must be the assigned provider).
        job_id: On-chain job ID.
        proof_hash: 32-byte SHA-256 hash of the result data.

    Returns:
        Transaction signature string.
    """
    if len(proof_hash) < 32:
        proof_hash = proof_hash.ljust(32, b"\x00")
    elif len(proof_hash) > 32:
        proof_hash = proof_hash[:32]

    job_pda, _ = derive_job_pda(job_id)
    signer = wallet.pubkey

    idl = _load_idl()
    disc = _get_discriminator(idl, "mark_completed")
    ix_data = disc + proof_hash

    accounts = [
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=signer, is_signer=True, is_writable=False),
    ]

    ix = Instruction(PROGRAM_ID, ix_data, accounts)
    sig = _send_tx(wallet, ix)
    wallet.confirm_transaction(sig)
    logger.info("Delivery proof submitted | job_id=%s sig=%s", job_id, sig)
    return sig


# -- Payment Claim --------------------------------------------------------------

def claim_payment(wallet: AgentWallet, job_id: int) -> str:
    """
    Release escrow payment to the provider.
    Requires delivery to have been confirmed first.

    Derives all required PDAs + ATAs for the provider and fee collector.

    Returns:
        Transaction signature string.
    """
    config_pda, _ = derive_config_pda()

    # Fetch config for fee collector
    resp = wallet.client.get_account_info(config_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError("MarketplaceConfig not found")
    config_data = bytes(resp.value.data)
    # Parse fee_collector (offset: 8 + 32 + 32 = 72, length 32)
    fee_collector = Pubkey.from_bytes(config_data[72:104])

    job_pda, _ = derive_job_pda(job_id)
    deposit_pda, _ = derive_deposit_pda(job_id)
    escrow_vault_pda, _ = derive_escrow_vault_pda(job_id)

    deposit = get_escrow_deposit(wallet, job_id)
    provider_pubkey = Pubkey.from_string(deposit["provider"])
    provider_ata = get_associated_token_address(provider_pubkey, USDC_MINT)
    fee_collector_ata = get_associated_token_address(fee_collector, USDC_MINT)
    reputation_pda, _ = derive_reputation_pda(provider_pubkey)
    signer = wallet.pubkey

    idl = _load_idl()
    disc = _get_discriminator(idl, "release_to_provider")

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=deposit_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=escrow_vault_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=provider_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=fee_collector_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=reputation_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=signer, is_signer=True, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(PROGRAM_ID, disc, accounts)
    sig = _send_tx(wallet, ix)
    wallet.confirm_transaction(sig)
    logger.info("Payment claimed | job_id=%s sig=%s", job_id, sig)
    return sig
