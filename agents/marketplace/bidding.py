"""
Bidding Engine — Collect bids for a configurable window, then pick a winner.

Selection algorithm (mirrors job_board._select_best):
  1. Filter out bids above the job budget.
  2. Sort by lowest price.
  3. Break ties by earliest submission timestamp.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import JobData, JobStatus

logger = logging.getLogger(__name__)


@dataclass
class Bid:
    """A bid submitted by an agent."""
    bid_id: str
    job_id: str
    agent_id: str           # registry agent_id
    agent_name: str
    wallet_address: str
    amount_usdc: float
    estimated_seconds: int
    submitted_at: float = field(default_factory=time.time)


@dataclass
class BidResult:
    """Outcome after the bid window closes."""
    job_id: str
    winner: Optional[Bid]
    all_bids: List[Bid]
    reason: str


@dataclass
class ActiveJob:
    """A job currently in the bidding/execution pipeline."""
    job: JobData
    status: JobStatus = JobStatus.OPEN
    bid_window_seconds: int = 15
    bids: List[Bid] = field(default_factory=list)
    winner: Optional[Bid] = None
    result: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)


class BiddingEngine:
    """
    Manages bid collection windows and winner selection.

    For each job:
      1. Open a bid window (default 15s, configurable per job).
      2. Collect bids from agents via ``submit_bid()``.
      3. When the window closes, ``select_winner()`` picks the best bid.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, ActiveJob] = {}

    # ── Job Lifecycle ─────────────────────────────────────────

    def open_job(self, job: JobData, bid_window_seconds: int = 15) -> ActiveJob:
        """Register a new job and open its bid window."""
        active = ActiveJob(
            job=job,
            status=JobStatus.BIDDING,
            bid_window_seconds=bid_window_seconds,
        )
        self._jobs[job.id] = active
        logger.info(
            "Bid window opened: job=%s  budget=%.2f USDC  window=%ds",
            job.id, job.budget_usdc, bid_window_seconds,
        )
        return active

    def submit_bid(
        self,
        job_id: str,
        agent_id: str,
        agent_name: str,
        wallet_address: str,
        amount_usdc: float,
        estimated_seconds: int,
    ) -> Optional[Bid]:
        """
        Record a bid for a job.  Returns the Bid if accepted, None if
        the job isn't in bidding state.
        """
        active = self._jobs.get(job_id)
        if not active or active.status != JobStatus.BIDDING:
            logger.warning("Bid rejected: job %s not in bidding state", job_id)
            return None

        # Prevent duplicate bids from the same agent on the same job
        if any(b.agent_id == agent_id for b in active.bids):
            logger.warning("Bid rejected: agent %s already bid on job %s", agent_id, job_id)
            return None

        bid = Bid(
            bid_id=str(uuid.uuid4()),
            job_id=job_id,
            agent_id=agent_id,
            agent_name=agent_name,
            wallet_address=wallet_address,
            amount_usdc=amount_usdc,
            estimated_seconds=estimated_seconds,
        )
        active.bids.append(bid)
        logger.info(
            "Bid received: job=%s  agent=%s  price=%.2f USDC  eta=%ds",
            job_id, agent_name, amount_usdc, estimated_seconds,
        )
        return bid

    async def wait_and_select(self, job_id: str) -> BidResult:
        """Wait for the bid window to close, then select the winner."""
        active = self._jobs.get(job_id)
        if not active:
            return BidResult(
                job_id=job_id, winner=None, all_bids=[],
                reason="Job not found",
            )

        await asyncio.sleep(active.bid_window_seconds)
        return self.select_winner(job_id)

    def select_winner(self, job_id: str) -> BidResult:
        """
        Pick the best bid.

        Strategy (mirrors job_board._select_best):
          1. Filter out bids above the budget.
          2. Sort by lowest price first.
          3. Break ties by earliest submitted_at.
        """
        active = self._jobs.get(job_id)
        if not active:
            return BidResult(
                job_id=job_id, winner=None, all_bids=[],
                reason="Job not found",
            )

        bids = active.bids
        budget = active.job.budget_usdc

        if not bids:
            active.status = JobStatus.EXPIRED
            return BidResult(
                job_id=job_id, winner=None, all_bids=bids,
                reason="No bids received within the window",
            )

        eligible = [b for b in bids if b.amount_usdc <= budget]
        if not eligible:
            cheapest = min(bids, key=lambda b: b.amount_usdc)
            active.status = JobStatus.EXPIRED
            return BidResult(
                job_id=job_id, winner=None, all_bids=bids,
                reason=(
                    f"All {len(bids)} bid(s) exceeded the budget "
                    f"(cheapest: {cheapest.amount_usdc:.2f} USDC vs "
                    f"budget {budget:.2f} USDC)"
                ),
            )

        # Sort: lowest price -> earliest submission
        eligible.sort(key=lambda b: (b.amount_usdc, b.submitted_at))
        winner = eligible[0]

        active.winner = winner
        active.status = JobStatus.ASSIGNED
        logger.info(
            "Winner selected: job=%s  agent=%s  price=%.2f USDC  (of %d bids, %d eligible)",
            job_id, winner.agent_name, winner.amount_usdc, len(bids), len(eligible),
        )

        return BidResult(
            job_id=job_id, winner=winner, all_bids=bids,
            reason=(
                f"Lowest price: {winner.amount_usdc:.2f} USDC "
                f"from {winner.agent_name} "
                f"(out of {len(bids)} bid(s), {len(eligible)} under budget)"
            ),
        )

    # ── Job Completion ────────────────────────────────────────

    def mark_completed(self, job_id: str, result: Dict[str, Any]) -> None:
        active = self._jobs.get(job_id)
        if active:
            active.status = JobStatus.COMPLETED
            active.result = result

    def mark_failed(self, job_id: str, error: str) -> None:
        active = self._jobs.get(job_id)
        if active:
            active.status = JobStatus.FAILED
            active.result = {"error": error}

    # ── Queries ───────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[ActiveJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[ActiveJob]:
        return list(self._jobs.values())
