"""
SOTA Agent SDK Data Models

Dataclasses shared across the SDK: Job, Bid, BidResult, JobResult.
Field names match the WebSocket protocol defined in marketplace/models.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Job:
    """A job broadcast by the marketplace hub."""
    id: str
    description: str
    tags: List[str]
    budget_usdc: float
    deadline_ts: int
    poster: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Bid:
    """A bid submitted (or to be submitted) for a job."""
    job_id: str
    amount_usdc: float
    estimated_seconds: int = 300
    bid_id: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BidResult:
    """Outcome after the hub selects (or rejects) a bid."""
    job_id: str
    accepted: bool
    bid_id: str = ""
    reason: str = ""


@dataclass
class JobResult:
    """Result returned by SOTAAgent.execute()."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    proof_hash: Optional[str] = None  # populated automatically after delivery
