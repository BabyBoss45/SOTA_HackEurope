"""
Contract Bridge for SOTA Agents

Web3.py wrapper for interacting with OrderBook, Escrow, and AgentRegistry
on Base Sepolia. All payments are USDC-only (6 decimals).
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .chain_config import get_network, get_contract_addresses, ContractAddresses


# ─── ABI Loading ──────────────────────────────────────────────

def _artifacts_dir() -> Path:
    """Path to compiled Hardhat artifacts"""
    return Path(__file__).parent.parent.parent.parent / "contracts" / "artifacts" / "contracts"


def load_abi(contract_name: str) -> list:
    """Load ABI from Hardhat artifacts (artifacts/contracts/<name>.sol/<name>.json)"""
    # Try artifacts directory first
    artifact_path = _artifacts_dir() / f"{contract_name}.sol" / f"{contract_name}.json"
    if artifact_path.exists():
        with open(artifact_path) as f:
            data = json.load(f)
            return data.get("abi", data)

    # Try mocks subdirectory
    mock_path = _artifacts_dir() / "mocks" / f"{contract_name}.sol" / f"{contract_name}.json"
    if mock_path.exists():
        with open(mock_path) as f:
            data = json.load(f)
            return data.get("abi", data)

    raise FileNotFoundError(f"ABI not found for {contract_name}")


# ─── Contract Container ──────────────────────────────────────

@dataclass
class Contracts:
    """Container for all contract instances"""
    w3: Web3
    account: Optional[LocalAccount]
    order_book: Contract
    escrow: Contract
    agent_registry: Contract
    usdc: Contract           # IERC20 for approve/transfer
    addresses: ContractAddresses


def get_contracts(private_key: Optional[str] = None) -> Contracts:
    """
    Initialise Web3 + all contract instances.

    Args:
        private_key: Optional private key for signing transactions.

    Returns:
        Contracts with all connections ready.
    """
    network = get_network()
    addresses = get_contract_addresses()

    if not addresses.order_book:
        raise ValueError(
            "Contract addresses not configured. "
            "Deploy contracts first and set ORDERBOOK_ADDRESS or "
            "ensure deployments/base-sepolia-84532.json exists."
        )

    w3 = Web3(Web3.HTTPProvider(network.rpc_url))

    account = None
    if private_key:
        account = Account.from_key(private_key)
        w3.eth.default_account = account.address

    def _contract(name: str, addr: str) -> Contract:
        return w3.eth.contract(
            address=Web3.to_checksum_address(addr),
            abi=load_abi(name),
        )

    return Contracts(
        w3=w3,
        account=account,
        order_book=_contract("OrderBook", addresses.order_book),
        escrow=_contract("Escrow", addresses.escrow),
        agent_registry=_contract("AgentRegistry", addresses.agent_registry),
        usdc=_contract("MockUSDC", addresses.usdc),
        addresses=addresses,
    )


# ─── Transaction Helpers ─────────────────────────────────────

# Global nonce lock — serialises transactions from the same account
_nonce_lock = threading.Lock()


def _send_tx(contracts: Contracts, fn: Any, value: int = 0, retries: int = 3) -> str:
    """Build, sign, send a contract call. Returns tx hash hex.

    Uses "pending" nonce to include unconfirmed transactions and
    retries on nonce collisions.
    """
    if not contracts.account:
        raise ValueError("No account configured for signing")

    last_err = None
    for attempt in range(retries):
        try:
            with _nonce_lock:
                nonce = contracts.w3.eth.get_transaction_count(
                    contracts.account.address, "pending"
                )
                tx = fn.build_transaction({
                    "from": contracts.account.address,
                    "nonce": nonce,
                    "gas": 600_000,
                    "gasPrice": contracts.w3.eth.gas_price,
                    "value": value,
                })
                signed = contracts.w3.eth.account.sign_transaction(tx, contracts.account.key)
                tx_hash = contracts.w3.eth.send_raw_transaction(signed.raw_transaction)
            return tx_hash.hex()
        except Exception as e:
            last_err = e
            err_msg = str(e).lower()
            if "nonce" in err_msg and attempt < retries - 1:
                time.sleep(1)  # brief delay before retry
                continue
            raise


def _wait(contracts: Contracts, tx_hash: str, timeout: int = 120):
    """Wait for transaction receipt."""
    return contracts.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)


# ─── Job Lifecycle ────────────────────────────────────────────

def create_job(
    contracts: Contracts,
    metadata_uri: str,
    budget_usdc: float,
    deadline_seconds: int = 86400,
) -> int:
    """
    Create a new job on OrderBook.
    Budget is in USDC (6 decimals).

    Returns: job ID
    """
    usdc_amount = int(budget_usdc * 1e6)  # USDC has 6 decimals
    deadline = int(time.time()) + deadline_seconds

    fn = contracts.order_book.functions.createJob(metadata_uri, usdc_amount, deadline)
    tx_hash = _send_tx(contracts, fn)
    receipt = _wait(contracts, tx_hash)

    logs = contracts.order_book.events.JobCreated().process_receipt(receipt)
    if logs:
        return logs[0]["args"]["jobId"]
    raise ValueError("JobCreated event not found")


def assign_provider(
    contracts: Contracts,
    job_id: int,
    provider_address: str,
) -> str:
    """Assign an agent to a job. Returns tx hash."""
    fn = contracts.order_book.functions.assignProvider(
        job_id,
        Web3.to_checksum_address(provider_address),
    )
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


def fund_job(
    contracts: Contracts,
    job_id: int,
    provider_address: str,
    usdc_amount: float,
) -> str:
    """
    Fund the escrow for a job with USDC.
    Does approve + fundJob in two transactions.

    Returns: tx hash of the fundJob call
    """
    amount_raw = int(usdc_amount * 1e6)  # 6 decimals
    escrow_addr = contracts.addresses.escrow

    # Step 1: Approve USDC spend
    fn_approve = contracts.usdc.functions.approve(
        Web3.to_checksum_address(escrow_addr), amount_raw
    )
    _send_tx(contracts, fn_approve)

    # Step 2: Fund escrow
    fn_fund = contracts.escrow.functions.fundJob(
        job_id,
        Web3.to_checksum_address(provider_address),
        amount_raw,
    )
    tx_hash = _send_tx(contracts, fn_fund)
    _wait(contracts, tx_hash)
    return tx_hash


def mark_completed(
    contracts: Contracts,
    job_id: int,
    proof_hash: bytes,
) -> str:
    """Agent marks job as completed with delivery proof. Returns tx hash."""
    fn = contracts.order_book.functions.markCompleted(job_id, proof_hash)
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


def release_payment(contracts: Contracts, job_id: int) -> str:
    """
    Release escrow payment (requires delivery confirmation).
    Will revert if delivery has not been confirmed.
    Returns tx hash.
    """
    fn = contracts.escrow.functions.releaseToProvider(job_id)
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


# ─── Delivery Confirmation ───────────────────────────────────

def confirm_delivery(contracts: Contracts, job_id: int) -> str:
    """Owner confirms delivery."""
    fn = contracts.escrow.functions.confirmDelivery(job_id)
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


def is_delivery_confirmed(contracts: Contracts, job_id: int) -> bool:
    """Check if delivery has been confirmed."""
    return contracts.escrow.functions.isDeliveryConfirmed(job_id).call()


# ─── Job Queries ──────────────────────────────────────────────

def get_job(contracts: Contracts, job_id: int) -> dict:
    """Get job details from OrderBook."""
    job = contracts.order_book.functions.getJob(job_id).call()
    # Returns: (id, poster, provider, metadataURI, maxBudgetUsdc,
    #           deadline, status, deliveryProof, createdAt, acceptedBidId)
    return {
        "id": job[0],
        "poster": job[1],
        "provider": job[2],
        "metadata_uri": job[3],
        "budget_usdc": job[4] / 1e6,  # 6 decimals → float
        "deadline": job[5],
        "status": job[6],  # 0=OPEN, 1=ASSIGNED, 2=COMPLETED, 3=RELEASED, 4=CANCELLED
        "delivery_proof": job[7].hex() if isinstance(job[7], bytes) else job[7],
        "created_at": job[8],
    }


def get_job_count(contracts: Contracts) -> int:
    """Get total number of jobs."""
    return contracts.order_book.functions.totalJobs().call()


def get_escrow_deposit(contracts: Contracts, job_id: int) -> dict:
    """Get escrow deposit details.

    Deposit struct: poster, provider, amount, funded, released, refunded
    """
    dep = contracts.escrow.functions.getDeposit(job_id).call()
    return {
        "poster": dep[0],
        "provider": dep[1],
        "amount_usdc": dep[2] / 1e6,
        "funded": dep[3],
        "released": dep[4],
        "refunded": dep[5],
    }


# ─── Agent Registry ──────────────────────────────────────────

def register_agent(
    contracts: Contracts,
    name: str,
    metadata_uri: str,
    capabilities: list[str],
) -> str:
    """Register as an agent on AgentRegistry. Returns tx hash."""
    fn = contracts.agent_registry.functions.registerAgent(
        name, metadata_uri, capabilities
    )
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


def is_agent_active(contracts: Contracts, address: str) -> bool:
    """Check if an address is a registered active agent."""
    return contracts.agent_registry.functions.isAgentActive(
        Web3.to_checksum_address(address)
    ).call()
