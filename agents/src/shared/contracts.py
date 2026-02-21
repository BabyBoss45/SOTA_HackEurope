"""
Contracts -- Re-exports from chain_contracts for backward compatibility.

All agent modules should import from here or from chain_contracts directly.
The chain layer has been migrated from EVM (Base Sepolia) to Solana Devnet.
"""

import time as _t
import logging

from .chain_contracts import *  # noqa: F401,F403

# Explicit re-exports for commonly used names
from .chain_contracts import (
    SolanaProgram,
    Contracts,
    get_program,
    get_contracts,
    load_idl,
    create_job,
    place_bid,
    accept_bid,
    assign_provider,
    fund_job,
    mark_completed,
    cancel_job,
    confirm_delivery,
    release_payment,
    refund_escrow,
    is_delivery_confirmed,
    get_job,
    get_job_count,
    get_bid,
    get_bids_for_job,
    get_escrow_deposit,
    register_agent,
    is_agent_active,
    get_agent,
    get_reputation,
    # PDA derivation utilities
    derive_config_pda,
    derive_job_pda,
    derive_bid_pda,
    derive_deposit_pda,
    derive_escrow_vault_pda,
    derive_agent_pda,
    derive_reputation_pda,
)

logger = logging.getLogger(__name__)

# ---- Legacy Aliases -------------------------------------------------------

ContractInstances = SolanaProgram
"""Legacy alias -- use :class:`SolanaProgram` in new code."""


def post_job(
    prog: SolanaProgram,
    description: str = "",
    metadata_uri: str = "",
    tags: list[str] | None = None,
    deadline: int = 0,
    budget_usdc: float = 0.02,
) -> int:
    """Legacy wrapper -- creates a job via :func:`create_job`.

    ``deadline`` can be:
      - 0          -> use default (86400 seconds from now)
      - > 1e9      -> treated as an absolute Unix timestamp
      - otherwise  -> treated as seconds from now
    """
    uri = metadata_uri or f"ipfs://sota-job-{_t.time():.0f}"
    if deadline <= 0:
        deadline_s = 86400
    elif deadline > 1_000_000_000:
        # Absolute Unix timestamp -> convert to seconds from now
        deadline_s = max(int(deadline - _t.time()), 60)
    else:
        # Already seconds from now
        deadline_s = deadline
    return create_job(prog, uri, budget_usdc, int(deadline_s))


def get_job_status(prog: SolanaProgram, job_id: int) -> int:
    """Get job status integer."""
    job = get_job(prog, job_id)
    return job["status"]


def submit_delivery(
    prog: SolanaProgram,
    job_id: int,
    proof_bytes: bytes,
) -> str:
    """Submit delivery proof. Delegates to :func:`mark_completed`."""
    return mark_completed(prog, job_id, proof_bytes)


def approve_delivery(prog: SolanaProgram, job_id: int) -> str:
    """Approve a delivery and release payment.

    Calls confirm_delivery first (required by the on-chain program
    before payment can be released), then release_payment.
    """
    confirm_delivery(prog, job_id)
    return release_payment(prog, job_id)
