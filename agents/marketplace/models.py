"""
Pydantic models for the Marketplace Hub WebSocket protocol.

Hub -> Agent messages:
  job_available, bid_accepted, bid_rejected, job_cancelled

Agent -> Hub messages:
  register, bid, job_completed, job_failed, heartbeat
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────

class MessageType(str, Enum):
    # Hub -> Agent
    JOB_AVAILABLE = "job_available"
    BID_ACCEPTED = "bid_accepted"
    BID_REJECTED = "bid_rejected"
    JOB_CANCELLED = "job_cancelled"

    # Agent -> Hub
    REGISTER = "register"
    BID = "bid"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    HEARTBEAT = "heartbeat"


class JobStatus(str, Enum):
    OPEN = "open"
    BIDDING = "bidding"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ─── Shared Data Objects ──────────────────────────────────────

class JobData(BaseModel):
    """Job payload shared between Hub and agents."""
    id: str
    description: str
    tags: List[str]
    budget_usdc: float
    deadline_ts: int
    poster: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentInfo(BaseModel):
    """Agent registration payload."""
    name: str
    tags: List[str]
    version: str = "1.0.0"
    wallet_address: str
    capabilities: List[str] = Field(default_factory=list)


# ─── Hub -> Agent Messages ────────────────────────────────────

class JobAvailableMsg(BaseModel):
    type: str = MessageType.JOB_AVAILABLE
    job: JobData


class BidAcceptedMsg(BaseModel):
    type: str = MessageType.BID_ACCEPTED
    job_id: str
    bid_id: str


class BidRejectedMsg(BaseModel):
    type: str = MessageType.BID_REJECTED
    job_id: str
    reason: str


class JobCancelledMsg(BaseModel):
    type: str = MessageType.JOB_CANCELLED
    job_id: str


# ─── Agent -> Hub Messages ────────────────────────────────────

class RegisterMsg(BaseModel):
    type: str = MessageType.REGISTER
    agent: AgentInfo


class BidMsg(BaseModel):
    type: str = MessageType.BID
    job_id: str
    amount_usdc: float
    estimated_seconds: int = 300

    @field_validator("amount_usdc")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount_usdc must be positive")
        return v


class JobCompletedMsg(BaseModel):
    type: str = MessageType.JOB_COMPLETED
    job_id: str
    success: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


class JobFailedMsg(BaseModel):
    type: str = MessageType.JOB_FAILED
    job_id: str
    error: str


class HeartbeatMsg(BaseModel):
    type: str = MessageType.HEARTBEAT


# ─── REST API Models ──────────────────────────────────────────

class PostJobRequest(BaseModel):
    """REST request body for POST /jobs."""
    description: str
    tags: List[str]
    budget_usdc: float
    deadline_ts: int
    poster: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bid_window_seconds: int = 15

    @field_validator("budget_usdc")
    @classmethod
    def budget_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("budget_usdc must be positive")
        return v

    @field_validator("bid_window_seconds")
    @classmethod
    def bid_window_in_range(cls, v: int) -> int:
        if v < 1 or v > 300:
            raise ValueError("bid_window_seconds must be between 1 and 300")
        return v

    @field_validator("tags")
    @classmethod
    def tags_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("tags must not be empty")
        return v


class PostJobResponse(BaseModel):
    """REST response for POST /jobs."""
    job_id: str
    status: str
    matched_agents: int
    message: str


class JobResultCallback(BaseModel):
    """Payload forwarded to Butler when a job completes."""
    job_id: str
    success: bool
    result: Dict[str, Any] = Field(default_factory=dict)
    agent_name: str
    error: Optional[str] = None
