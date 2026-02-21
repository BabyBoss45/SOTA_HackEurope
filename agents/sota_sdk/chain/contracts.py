"""
On-chain helpers for the SOTA SDK.

Adapted from agents/src/shared/chain_contracts.py.
Provides: submit_delivery_proof, claim_payment, get_job.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.contract import Contract

from ..config import get_contract_addresses, get_network
from .wallet import AgentWallet

logger = logging.getLogger(__name__)


# -- ABI Loading ---------------------------------------------------------------

def _artifacts_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "contracts" / "artifacts" / "contracts"


def _load_abi(contract_name: str) -> list:
    for parent in [_artifacts_dir(), _artifacts_dir() / "mocks"]:
        path = parent / f"{contract_name}.sol" / f"{contract_name}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                return data.get("abi", data)
    raise FileNotFoundError(f"ABI not found for {contract_name}")


# -- Contract Accessors --------------------------------------------------------

def _get_contract(wallet: AgentWallet, name: str, address: str) -> Contract:
    return wallet.w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=_load_abi(name),
    )


def _order_book(wallet: AgentWallet) -> Contract:
    addr = get_contract_addresses().order_book
    if not addr:
        raise ValueError("ORDERBOOK_ADDRESS not configured")
    return _get_contract(wallet, "OrderBook", addr)


def _escrow(wallet: AgentWallet) -> Contract:
    addr = get_contract_addresses().escrow
    if not addr:
        raise ValueError("ESCROW_ADDRESS not configured")
    return _get_contract(wallet, "Escrow", addr)


# -- Job Queries ---------------------------------------------------------------

def get_job(wallet: AgentWallet, job_id: int) -> dict:
    """Fetch job details from OrderBook."""
    ob = _order_book(wallet)
    job = ob.functions.getJob(job_id).call()
    return {
        "id": job[0],
        "poster": job[1],
        "provider": job[2],
        "metadata_uri": job[3],
        "budget_usdc": int(job[4]) / 10**6,  # int division avoids float drift
        "deadline": job[5],
        "status": job[6],
        "delivery_proof": job[7].hex() if isinstance(job[7], bytes) else job[7],
        "created_at": job[8],
    }


# -- Delivery Proof -------------------------------------------------------------

def submit_delivery_proof(
    wallet: AgentWallet, job_id: int, proof_hash: bytes
) -> str:
    """
    Mark a job as completed on-chain with a delivery proof hash.

    Args:
        wallet: Agent's wallet (must be the assigned provider).
        job_id: On-chain job ID.
        proof_hash: 32-byte keccak hash of the result data.

    Returns:
        Transaction hash hex string.
    """
    ob = _order_book(wallet)
    fn = ob.functions.markCompleted(job_id, proof_hash)
    tx_hash = wallet.build_and_send(fn)
    wallet.wait_for_receipt(tx_hash)
    logger.info("Delivery proof submitted | job_id=%s tx=%s", job_id, tx_hash)
    return tx_hash


# -- Payment Claim --------------------------------------------------------------

def claim_payment(wallet: AgentWallet, job_id: int) -> str:
    """
    Release escrow payment to the provider.
    Requires delivery to have been confirmed first.

    Returns:
        Transaction hash hex string.
    """
    escrow = _escrow(wallet)
    fn = escrow.functions.releaseToProvider(job_id)
    tx_hash = wallet.build_and_send(fn)
    wallet.wait_for_receipt(tx_hash)
    logger.info("Payment claimed | job_id=%s tx=%s", job_id, tx_hash)
    return tx_hash
