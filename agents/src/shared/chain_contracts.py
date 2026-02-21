"""
Contract Bridge for SOTA Agents

Solana/Anchor wrapper for interacting with the sota_marketplace program
on Solana Devnet. All payments are USDC-only (6 decimals).

Uses raw solana-py + solders for transaction building rather than anchorpy's
higher-level Program object, because the IDL-driven approach gives us full
control over PDA derivation and account ordering.
"""

import json
import struct
import logging
import time as _time
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed, Finalized
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash
from spl.token.instructions import (
    get_associated_token_address,
)

from .chain_config import (
    get_cluster,
    get_program_id,
    get_keypair,
    PROGRAM_ID,
    USDC_MINT,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSVAR_RENT_PUBKEY,
)

logger = logging.getLogger(__name__)


# ---- IDL Loading ---------------------------------------------------------

import os as _os

# Try multiple IDL locations: local agents copy first, then anchor build output
_AGENTS_ROOT = Path(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
_IDL_CANDIDATES = [
    _AGENTS_ROOT / "sota_marketplace_idl.json",                          # Docker / agents dir
    _AGENTS_ROOT.parent / "anchor" / "target" / "idl" / "sota_marketplace.json",  # Local dev
]
_IDL_PATH = next((p for p in _IDL_CANDIDATES if p.exists()), _IDL_CANDIDATES[0])

_idl_cache: Optional[dict] = None


def load_idl() -> dict:
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


# ---- PDA Derivation -----------------------------------------------------

def derive_config_pda(program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive the MarketplaceConfig PDA: seeds = [b"config"]"""
    return Pubkey.find_program_address([b"config"], program_id)


def derive_job_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Job PDA: seeds = [b"job", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"job", struct.pack("<Q", job_id)], program_id
    )


def derive_bid_pda(bid_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Bid PDA: seeds = [b"bid", bid_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"bid", struct.pack("<Q", bid_id)], program_id
    )


def derive_deposit_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Deposit PDA: seeds = [b"deposit", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"deposit", struct.pack("<Q", job_id)], program_id
    )


def derive_escrow_vault_pda(job_id: int, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive the EscrowVault PDA (token account): seeds = [b"escrow_vault", job_id.to_le_bytes()]"""
    return Pubkey.find_program_address(
        [b"escrow_vault", struct.pack("<Q", job_id)], program_id
    )


def derive_agent_pda(wallet: Pubkey, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive an Agent PDA: seeds = [b"agent", wallet.as_ref()]"""
    return Pubkey.find_program_address(
        [b"agent", bytes(wallet)], program_id
    )


def derive_reputation_pda(wallet: Pubkey, program_id: Pubkey = PROGRAM_ID) -> tuple[Pubkey, int]:
    """Derive a Reputation PDA: seeds = [b"reputation", wallet.as_ref()]"""
    return Pubkey.find_program_address(
        [b"reputation", bytes(wallet)], program_id
    )


# ---- Anchor Data Serialization ------------------------------------------

def _encode_string(s: str) -> bytes:
    """Anchor-compatible string encoding: 4-byte LE length prefix + UTF-8 bytes."""
    encoded = s.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def _encode_vec_string(strings: list[str]) -> bytes:
    """Anchor-compatible Vec<String> encoding: 4-byte LE vec length + each string."""
    data = struct.pack("<I", len(strings))
    for s in strings:
        data += _encode_string(s)
    return data


# ---- Program Container ---------------------------------------------------

@dataclass
class SolanaProgram:
    """Container for Solana RPC client, keypair, and program metadata."""
    client: Client
    keypair: Optional[Keypair]
    program_id: Pubkey
    idl: dict


def get_program(keypair: Optional[Keypair] = None) -> SolanaProgram:
    """
    Initialise Solana client + load IDL.

    Args:
        keypair: Optional Keypair for signing transactions.

    Returns:
        SolanaProgram with all connections ready.
    """
    cluster = get_cluster()
    client = Client(cluster.rpc_url)
    idl = load_idl()
    program_id = get_program_id()

    return SolanaProgram(
        client=client,
        keypair=keypair,
        program_id=program_id,
        idl=idl,
    )


# Backward-compat alias
Contracts = SolanaProgram


def get_contracts(private_key: Optional[str] = None) -> SolanaProgram:
    """Backward-compatible: loads keypair from raw string, returns SolanaProgram."""
    kp = None
    if private_key:
        private_key = private_key.strip()
        if private_key.startswith("["):
            byte_list = json.loads(private_key)
            kp = Keypair.from_bytes(bytes(byte_list))
        else:
            try:
                kp = Keypair.from_base58_string(private_key)
            except Exception:
                import base64
                kp = Keypair.from_bytes(base64.b64decode(private_key))
    return get_program(kp)


# ---- Transaction Helpers -------------------------------------------------

def _send_tx(
    prog: SolanaProgram,
    ix: Instruction,
    extra_signers: list[Keypair] | None = None,
    retries: int = 3,
) -> str:
    """
    Build, sign, and send a transaction with a single instruction.
    Returns the transaction signature string.
    """
    if not prog.keypair:
        raise ValueError("No keypair configured for signing")

    signers = [prog.keypair]
    if extra_signers:
        signers.extend(extra_signers)

    last_err = None
    for attempt in range(retries):
        try:
            recent_blockhash = prog.client.get_latest_blockhash(Confirmed).value.blockhash
            tx = Transaction()
            tx.recent_blockhash = recent_blockhash
            tx.fee_payer = prog.keypair.pubkey()
            tx.add(ix)

            result = prog.client.send_transaction(
                tx,
                *signers,
                opts=TxOpts(
                    skip_preflight=False,
                    preflight_commitment=Confirmed,
                ),
            )

            sig = str(result.value)
            logger.info("Transaction sent: %s", sig)
            return sig

        except Exception as e:
            last_err = e
            err_msg = str(e).lower()
            # Retry on blockhash-related errors
            if ("blockhash" in err_msg or "expired" in err_msg) and attempt < retries - 1:
                _time.sleep(1)
                continue
            raise

    raise last_err  # type: ignore[misc]


def _confirm_tx(prog: SolanaProgram, sig: str, timeout: int = 60) -> dict:
    """Wait for transaction confirmation and return the result."""
    from solana.rpc.commitment import Confirmed as _Confirmed

    resp = prog.client.confirm_transaction(sig, commitment=_Confirmed)
    return resp


# ---- Account Deserialization Helpers -------------------------------------

def _fetch_config(prog: SolanaProgram) -> dict:
    """Fetch and deserialize the MarketplaceConfig account."""
    config_pda, _ = derive_config_pda(prog.program_id)
    resp = prog.client.get_account_info(config_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError("MarketplaceConfig account not found. Is the program initialized?")

    data = bytes(resp.value.data)
    # Skip 8-byte discriminator
    offset = 8
    authority = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    usdc_mint = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    fee_collector = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    platform_fee_bps = struct.unpack_from("<H", data, offset)[0]; offset += 2
    next_job_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    next_bid_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "authority": authority,
        "usdc_mint": usdc_mint,
        "fee_collector": fee_collector,
        "platform_fee_bps": platform_fee_bps,
        "next_job_id": next_job_id,
        "next_bid_id": next_bid_id,
        "bump": bump,
    }


def _deserialize_string(data: bytes, offset: int) -> tuple[str, int]:
    """Deserialize an Anchor string (4-byte LE len + UTF-8)."""
    length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    s = data[offset:offset+length].decode("utf-8")
    offset += length
    return s, offset


def _deserialize_vec_string(data: bytes, offset: int) -> tuple[list[str], int]:
    """Deserialize an Anchor Vec<String>."""
    count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    strings = []
    for _ in range(count):
        s, offset = _deserialize_string(data, offset)
        strings.append(s)
    return strings, offset


def _deserialize_job(data: bytes) -> dict:
    """Deserialize a Job account from raw bytes (after 8-byte discriminator)."""
    offset = 8
    job_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    poster = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    provider = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    metadata_uri, offset = _deserialize_string(data, offset)
    max_budget_usdc = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    deadline = struct.unpack_from("<q", data, offset)[0]; offset += 8
    # JobStatus is a 1-byte enum variant index
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
        "status": status,  # 0=Open, 1=Assigned, 2=Completed, 3=Released, 4=Cancelled, 5=Disputed
        "delivery_proof": delivery_proof.hex(),
        "created_at": created_at,
        "accepted_bid_id": accepted_bid_id,
        "bump": bump,
    }


def _deserialize_bid(data: bytes) -> dict:
    """Deserialize a Bid account from raw bytes."""
    offset = 8
    bid_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    job_id = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    agent = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    price_usdc = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    estimated_time = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    proposal, offset = _deserialize_string(data, offset)
    accepted = bool(data[offset]); offset += 1
    created_at = struct.unpack_from("<q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "id": bid_id,
        "job_id": job_id,
        "agent": str(agent),
        "price_usdc": price_usdc / 1e6,
        "price_usdc_raw": price_usdc,
        "estimated_time": estimated_time,
        "proposal": proposal,
        "accepted": accepted,
        "created_at": created_at,
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


# ---- Job Lifecycle -------------------------------------------------------

def create_job(
    prog: SolanaProgram,
    metadata_uri: str,
    budget_usdc: float,
    deadline_seconds: int = 86400,
) -> int:
    """
    Create a new job on the marketplace.
    Budget is in USDC (6 decimals).

    Returns: job ID (u64)
    """
    usdc_amount = int(budget_usdc * 1e6)
    deadline = int(_time.time()) + deadline_seconds

    # Fetch config to get next_job_id for PDA derivation
    config = _fetch_config(prog)
    next_job_id = config["next_job_id"]

    config_pda, _ = derive_config_pda(prog.program_id)
    job_pda, _ = derive_job_pda(next_job_id, prog.program_id)
    poster = prog.keypair.pubkey()

    # Build instruction data: discriminator + metadata_uri + max_budget_usdc + deadline
    idl = load_idl()
    disc = _get_discriminator(idl, "create_job")
    ix_data = disc + _encode_string(metadata_uri) + struct.pack("<Q", usdc_amount) + struct.pack("<q", deadline)

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, ix_data, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Job created: id=%d, sig=%s", next_job_id, sig)
    return next_job_id


def place_bid(
    prog: SolanaProgram,
    job_id: int,
    amount: int,
    estimated_time: int,
    metadata_uri: str = "",
) -> int:
    """
    Place a bid on an existing job.

    Args:
        prog: SolanaProgram instance.
        job_id: The job ID to bid on.
        amount: Bid price in USDC raw units (6 decimals). Pass int, not float.
        estimated_time: Estimated completion time in seconds.
        metadata_uri: Proposal text / metadata URI.

    Returns: bid ID (u64)
    """
    config = _fetch_config(prog)
    next_bid_id = config["next_bid_id"]

    config_pda, _ = derive_config_pda(prog.program_id)
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    bid_pda, _ = derive_bid_pda(next_bid_id, prog.program_id)
    agent_pubkey = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "place_bid")
    ix_data = (
        disc
        + struct.pack("<Q", amount)
        + struct.pack("<Q", estimated_time)
        + _encode_string(metadata_uri)
    )

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=bid_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=agent_pubkey, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, ix_data, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Bid placed: bid_id=%d on job_id=%d, sig=%s", next_bid_id, job_id, sig)
    return next_bid_id


def accept_bid(
    prog: SolanaProgram,
    job_id: int,
    bid_id: int,
) -> str:
    """
    Accept a bid on a job. Caller must be the job poster.

    Returns: transaction signature
    """
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    bid_pda, _ = derive_bid_pda(bid_id, prog.program_id)
    poster = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "accept_bid")

    accounts = [
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=bid_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster, is_signer=True, is_writable=False),
    ]

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Bid accepted: bid_id=%d for job_id=%d, sig=%s", bid_id, job_id, sig)
    return sig


def assign_provider(
    prog: SolanaProgram,
    job_id: int,
    provider_pubkey: Pubkey,
) -> str:
    """
    Directly assign a provider to a job (poster-only).

    Returns: transaction signature
    """
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    poster = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "assign_provider")

    accounts = [
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster, is_signer=True, is_writable=False),
        AccountMeta(pubkey=provider_pubkey, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Provider assigned: job_id=%d, provider=%s, sig=%s", job_id, provider_pubkey, sig)
    return sig


def fund_job(
    prog: SolanaProgram,
    job_id: int,
    provider_pubkey: Pubkey,
    usdc_amount: float,
) -> str:
    """
    Fund the escrow for a job with USDC via SPL token transfer.

    Args:
        prog: SolanaProgram instance.
        job_id: The job to fund.
        provider_pubkey: The provider's wallet pubkey.
        usdc_amount: Amount in USDC (float, 6-decimal conversion done internally).

    Returns: transaction signature
    """
    amount_raw = int(usdc_amount * 1e6)

    config_pda, _ = derive_config_pda(prog.program_id)
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    deposit_pda, _ = derive_deposit_pda(job_id, prog.program_id)
    escrow_vault_pda, _ = derive_escrow_vault_pda(job_id, prog.program_id)
    poster = prog.keypair.pubkey()
    poster_ata = get_associated_token_address(poster, USDC_MINT)

    idl = load_idl()
    disc = _get_discriminator(idl, "fund_job")
    ix_data = disc + struct.pack("<Q", amount_raw)

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=deposit_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=escrow_vault_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=USDC_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=poster, is_signer=True, is_writable=True),
        AccountMeta(pubkey=provider_pubkey, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSVAR_RENT_PUBKEY, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, ix_data, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Job funded: job_id=%d, amount=%.6f USDC, sig=%s", job_id, usdc_amount, sig)
    return sig


def mark_completed(
    prog: SolanaProgram,
    job_id: int,
    proof_hash: bytes,
) -> str:
    """
    Agent marks job as completed with a 32-byte delivery proof hash.

    Returns: transaction signature
    """
    if len(proof_hash) < 32:
        proof_hash = proof_hash.ljust(32, b"\x00")
    elif len(proof_hash) > 32:
        proof_hash = proof_hash[:32]

    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    signer = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "mark_completed")
    ix_data = disc + proof_hash

    accounts = [
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=signer, is_signer=True, is_writable=False),
    ]

    ix = Instruction(prog.program_id, ix_data, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Job marked completed: job_id=%d, sig=%s", job_id, sig)
    return sig


def cancel_job(prog: SolanaProgram, job_id: int) -> str:
    """Cancel a job (poster-only). Returns tx signature."""
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    poster = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "cancel_job")

    accounts = [
        AccountMeta(pubkey=job_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster, is_signer=True, is_writable=False),
    ]

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)
    return sig


def confirm_delivery(prog: SolanaProgram, job_id: int) -> str:
    """Confirm delivery for a funded job (authority-only). Returns tx sig."""
    config_pda, _ = derive_config_pda(prog.program_id)
    deposit_pda, _ = derive_deposit_pda(job_id, prog.program_id)
    authority = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "confirm_delivery")

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=deposit_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=authority, is_signer=True, is_writable=False),
    ]

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)
    return sig


def release_payment(prog: SolanaProgram, job_id: int) -> str:
    """
    Release escrow payment to provider after delivery confirmation.

    Derives all required PDAs + ATAs for the provider and fee collector.

    Returns: transaction signature
    """
    config_pda, _ = derive_config_pda(prog.program_id)
    config = _fetch_config(prog)
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    deposit_pda, _ = derive_deposit_pda(job_id, prog.program_id)
    escrow_vault_pda, _ = derive_escrow_vault_pda(job_id, prog.program_id)

    # Need to read the deposit to get provider pubkey
    deposit = get_escrow_deposit(prog, job_id)
    provider_pubkey = Pubkey.from_string(deposit["provider"])
    provider_ata = get_associated_token_address(provider_pubkey, USDC_MINT)

    fee_collector_ata = get_associated_token_address(config["fee_collector"], USDC_MINT)

    reputation_pda, _ = derive_reputation_pda(provider_pubkey, prog.program_id)
    signer = prog.keypair.pubkey()

    idl = load_idl()
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

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Payment released: job_id=%d, sig=%s", job_id, sig)
    return sig


def refund_escrow(prog: SolanaProgram, job_id: int) -> str:
    """
    Refund escrow deposit back to poster.

    Returns: transaction signature
    """
    config_pda, _ = derive_config_pda(prog.program_id)
    deposit_pda, _ = derive_deposit_pda(job_id, prog.program_id)
    escrow_vault_pda, _ = derive_escrow_vault_pda(job_id, prog.program_id)

    deposit = get_escrow_deposit(prog, job_id)
    poster_pubkey = Pubkey.from_string(deposit["poster"])
    poster_ata = get_associated_token_address(poster_pubkey, USDC_MINT)

    provider_pubkey = Pubkey.from_string(deposit["provider"])
    reputation_pda, _ = derive_reputation_pda(provider_pubkey, prog.program_id)

    authority = prog.keypair.pubkey()

    idl = load_idl()
    disc = _get_discriminator(idl, "refund")

    accounts = [
        AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=deposit_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=escrow_vault_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=poster_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=reputation_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=authority, is_signer=True, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, disc, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Escrow refunded: job_id=%d, sig=%s", job_id, sig)
    return sig


# ---- Job Queries ---------------------------------------------------------

def get_job(prog: SolanaProgram, job_id: int) -> dict:
    """Fetch and deserialize a Job account by job_id."""
    job_pda, _ = derive_job_pda(job_id, prog.program_id)
    resp = prog.client.get_account_info(job_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Job account not found for job_id={job_id}")
    return _deserialize_job(bytes(resp.value.data))


def get_job_count(prog: SolanaProgram) -> int:
    """Get total number of jobs created (next_job_id from config)."""
    config = _fetch_config(prog)
    return config["next_job_id"]


def get_escrow_deposit(prog: SolanaProgram, job_id: int) -> dict:
    """Fetch and deserialize a Deposit account by job_id."""
    deposit_pda, _ = derive_deposit_pda(job_id, prog.program_id)
    resp = prog.client.get_account_info(deposit_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Deposit account not found for job_id={job_id}")
    return _deserialize_deposit(bytes(resp.value.data))


def is_delivery_confirmed(prog: SolanaProgram, job_id: int) -> bool:
    """Check if delivery has been confirmed for a job."""
    try:
        deposit = get_escrow_deposit(prog, job_id)
        return deposit["delivery_confirmed"]
    except ValueError:
        return False


def get_bid(prog: SolanaProgram, bid_id: int) -> dict:
    """Fetch and deserialize a Bid account by bid_id."""
    bid_pda, _ = derive_bid_pda(bid_id, prog.program_id)
    resp = prog.client.get_account_info(bid_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Bid account not found for bid_id={bid_id}")
    return _deserialize_bid(bytes(resp.value.data))


def get_bids_for_job(prog: SolanaProgram, job_id: int) -> list[dict]:
    """
    Fetch all bids for a given job.

    Since Solana does not have on-chain enumeration by job_id,
    we scan bid IDs from 0..next_bid_id and filter by job_id.

    For production, use getProgramAccounts with a memcmp filter
    on the job_id field offset. This is the simple approach.
    """
    config = _fetch_config(prog)
    total_bids = config["next_bid_id"]
    bids = []

    for bid_id in range(total_bids):
        try:
            bid = get_bid(prog, bid_id)
            if bid["job_id"] == job_id:
                bids.append(bid)
        except ValueError:
            continue

    return bids


# ---- Agent Registry ------------------------------------------------------

def register_agent(
    prog: SolanaProgram,
    name: str,
    metadata_uri: str,
    capabilities: list[str],
    wallet_pubkey: Pubkey | None = None,
) -> str:
    """
    Register an agent on-chain.

    The 'wallet' is the agent's operational wallet (can differ from developer).
    The 'developer' (signer) pays for the account and owns the registration.

    Args:
        prog: SolanaProgram instance with developer keypair.
        name: Agent display name.
        metadata_uri: URI to agent metadata.
        capabilities: List of capability strings.
        wallet_pubkey: Agent wallet pubkey. Defaults to developer's own pubkey.

    Returns: transaction signature
    """
    developer = prog.keypair.pubkey()
    wallet = wallet_pubkey or developer

    agent_pda, _ = derive_agent_pda(wallet, prog.program_id)
    reputation_pda, _ = derive_reputation_pda(wallet, prog.program_id)

    idl = load_idl()
    disc = _get_discriminator(idl, "register_agent")
    ix_data = disc + _encode_string(name) + _encode_string(metadata_uri) + _encode_vec_string(capabilities)

    accounts = [
        AccountMeta(pubkey=agent_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=reputation_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=wallet, is_signer=False, is_writable=False),
        AccountMeta(pubkey=developer, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(prog.program_id, ix_data, accounts)
    sig = _send_tx(prog, ix)
    _confirm_tx(prog, sig)

    logger.info("Agent registered: name=%s, wallet=%s, sig=%s", name, wallet, sig)
    return sig


def is_agent_active(prog: SolanaProgram, wallet_pubkey: Pubkey) -> bool:
    """Check if an agent is registered and active."""
    agent_pda, _ = derive_agent_pda(wallet_pubkey, prog.program_id)
    resp = prog.client.get_account_info(agent_pda, commitment=Confirmed)
    if resp.value is None:
        return False

    data = bytes(resp.value.data)
    # Agent.status is after: wallet(32) + developer(32) + name(4+N) + metadata_uri(4+N) + capabilities(4+N) + reputation(8)
    # Since status offset is variable due to strings, do a minimal parse.
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
    # Now we're at status (1-byte enum)
    status = data[offset]
    return status == 1  # AgentStatus::Active = 1


def get_agent(prog: SolanaProgram, wallet_pubkey: Pubkey) -> dict:
    """Fetch and deserialize an Agent account."""
    agent_pda, _ = derive_agent_pda(wallet_pubkey, prog.program_id)
    resp = prog.client.get_account_info(agent_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Agent account not found for wallet={wallet_pubkey}")

    data = bytes(resp.value.data)
    offset = 8
    wallet = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    developer = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    name, offset = _deserialize_string(data, offset)
    metadata_uri, offset = _deserialize_string(data, offset)
    capabilities, offset = _deserialize_vec_string(data, offset)
    reputation = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    status = data[offset]; offset += 1
    created_at = struct.unpack_from("<q", data, offset)[0]; offset += 8
    updated_at = struct.unpack_from("<q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "wallet": str(wallet),
        "developer": str(developer),
        "name": name,
        "metadata_uri": metadata_uri,
        "capabilities": capabilities,
        "reputation": reputation,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "bump": bump,
    }


def get_reputation(prog: SolanaProgram, wallet_pubkey: Pubkey) -> dict:
    """Fetch and deserialize a Reputation account."""
    rep_pda, _ = derive_reputation_pda(wallet_pubkey, prog.program_id)
    resp = prog.client.get_account_info(rep_pda, commitment=Confirmed)
    if resp.value is None:
        raise ValueError(f"Reputation account not found for wallet={wallet_pubkey}")

    data = bytes(resp.value.data)
    offset = 8
    wallet = Pubkey.from_bytes(data[offset:offset+32]); offset += 32
    score = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    jobs_completed = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    jobs_failed = struct.unpack_from("<Q", data, offset)[0]; offset += 8
    total_earned = struct.unpack_from("<QQ", data, offset)  # u128 as two u64s
    total_earned_val = total_earned[0] | (total_earned[1] << 64)
    offset += 16
    last_updated = struct.unpack_from("<q", data, offset)[0]; offset += 8
    bump = data[offset]; offset += 1

    return {
        "wallet": str(wallet),
        "score": score,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "total_earned": total_earned_val,
        "last_updated": last_updated,
        "bump": bump,
    }
