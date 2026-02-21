"""
Contracts — Re-exports from chain_contracts for backward compatibility.

All agent modules should import from here or from chain_contracts directly.
"""

from .chain_contracts import *  # noqa: F401,F403

# Explicit re-exports for commonly used names
from .chain_contracts import (
    Contracts,
    get_contracts,
    load_abi,
    create_job,
    assign_provider,
    fund_job,
    mark_completed,
    release_payment,
    confirm_delivery,
    is_delivery_confirmed,
    get_job,
    get_job_count,
    get_escrow_deposit,
    register_agent,
    is_agent_active,
)

# ─── Aliases for old code ────────────────────────────────────

ContractInstances = Contracts
"""Legacy alias — use :class:`Contracts` in new code."""


def post_job(
    contracts: Contracts,
    description: str = "",
    metadata_uri: str = "",
    tags: list[str] | None = None,
    deadline: int = 0,
    budget_usdc: float = 0.02,
) -> int:
    """Legacy wrapper — creates a job via :func:`create_job`."""
    uri = metadata_uri or f"ipfs://sota-job-{__import__('time').time():.0f}"
    deadline_s = deadline - __import__('time').time() if deadline > __import__('time').time() else 86400
    return create_job(contracts, uri, budget_usdc, int(deadline_s))


def get_bids_for_job(contracts: Contracts, job_id: int) -> list:
    """Placeholder — bid listing via OrderBook."""
    try:
        return contracts.order_book.functions.getBids(job_id).call()
    except Exception:
        return []


def accept_bid(
    contracts: Contracts,
    job_id: int,
    bid_id: int,
    response_uri: str = "",
) -> str:
    """Accept a bid on OrderBook."""
    from .chain_contracts import _send_tx, _wait

    fn = contracts.order_book.functions.acceptBid(job_id, bid_id)
    tx_hash = _send_tx(contracts, fn)
    _wait(contracts, tx_hash)
    return tx_hash


def place_bid(
    contracts: Contracts,
    job_id: int,
    amount: int,
    estimated_time: int,
    metadata_uri: str = "",
) -> int:
    """Place a bid on OrderBook. Returns bid_id."""
    from .chain_contracts import _send_tx, _wait

    fn = contracts.order_book.functions.placeBid(
        job_id, amount, estimated_time, metadata_uri
    )
    tx_hash = _send_tx(contracts, fn)
    receipt = _wait(contracts, tx_hash)

    logs = contracts.order_book.events.BidPlaced().process_receipt(receipt)
    if logs:
        return logs[0]["args"]["bidId"]
    return 0


def get_job_status(contracts: Contracts, job_id: int) -> int:
    """Get job status integer from OrderBook."""
    job = contracts.order_book.functions.getJob(job_id).call()
    return job[6] if len(job) > 6 else 0


def submit_delivery(
    contracts: Contracts,
    job_id: int,
    proof_bytes: bytes,
) -> str:
    """Submit delivery proof. Delegates to :func:`mark_completed`."""
    return mark_completed(contracts, job_id, proof_bytes)


def approve_delivery(contracts: Contracts, job_id: int) -> str:
    """Approve a delivery and release payment."""
    return release_payment(contracts, job_id)
