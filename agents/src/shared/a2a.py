"""
Agent-to-Agent (A2A) Protocol Implementation

Signed message format for secure inter-agent communication.
"""

import time
import json
import hashlib
from typing import Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from nacl.signing import VerifyKey
from pydantic import BaseModel, Field


class A2AMethod(str, Enum):
    """Standard A2A methods"""
    # Task execution
    EXECUTE_TASK = "tasks/execute"
    GET_TASK_STATUS = "tasks/status"
    CANCEL_TASK = "tasks/cancel"
    
    # Agent discovery
    GET_CAPABILITIES = "agent/capabilities"
    GET_STATUS = "agent/status"
    PING = "agent/ping"
    
    # Results
    SUBMIT_RESULT = "results/submit"
    GET_RESULT = "results/get"


class A2AErrorCode(int, Enum):
    """Standard JSON-RPC and custom error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom error codes
    UNAUTHORIZED = -32000
    TASK_NOT_FOUND = -32001
    TASK_FAILED = -32002
    RATE_LIMITED = -32003
    SIGNATURE_INVALID = -32004
    MESSAGE_EXPIRED = -32005


class A2AMessage(BaseModel):
    """A2A Protocol Message"""
    jsonrpc: str = "2.0"
    id: int
    method: str
    params: dict = Field(default_factory=dict)
    sender: Optional[str] = None  # Agent wallet address
    timestamp: Optional[int] = None
    signature: Optional[str] = None


class A2AError(BaseModel):
    """A2A Error object"""
    code: int
    message: str
    data: Optional[Any] = None


class A2AResponse(BaseModel):
    """A2A Protocol Response"""
    jsonrpc: str = "2.0"
    id: int
    result: Optional[Any] = None
    error: Optional[A2AError] = None


def sign_message(message: A2AMessage, keypair: Keypair) -> A2AMessage:
    """
    Sign an A2A message with the agent's Solana keypair.

    Args:
        message: The A2A message to sign
        keypair: The Solana Keypair to sign with

    Returns:
        Signed A2A message
    """
    # Add sender (base58 public key) and timestamp
    message.sender = str(keypair.pubkey())
    message.timestamp = int(time.time() * 1000)

    # Create message hash (exclude signature field)
    message_data = message.model_dump(exclude={'signature'})
    message_json = json.dumps(message_data, sort_keys=True)
    message_hash = hashlib.sha256(message_json.encode()).hexdigest()

    # Sign the hash with ed25519
    sig = keypair.sign_message(message_hash.encode())
    message.signature = bytes(sig).hex()

    return message


def verify_message(
    message: A2AMessage,
    expected_signer: Optional[str] = None,
    check_freshness: bool = True,
) -> tuple[bool, Optional[str]]:
    """
    Verify an A2A message signature and optionally check freshness.

    Args:
        message: The signed A2A message
        expected_signer: Optional expected signer address
        check_freshness: Whether to reject stale messages (default True)

    Returns:
        Tuple of (is_valid, recovered_signer_address)
    """
    if not message.signature or not message.sender or not message.timestamp:
        return False, None

    # C7: Check message freshness before doing expensive crypto
    if check_freshness and not is_message_fresh(message):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Message from %s is stale (timestamp: %s)", message.sender, message.timestamp
        )
        return False, None

    try:
        # Recreate message hash (exclude signature field)
        message_data = message.model_dump(exclude={'signature'})
        message_json = json.dumps(message_data, sort_keys=True)
        message_hash = hashlib.sha256(message_json.encode()).hexdigest()

        # Decode sender public key and signature
        sender_pubkey = Pubkey.from_string(message.sender)
        sig_bytes = bytes.fromhex(message.signature)

        # Verify ed25519 signature using PyNaCl
        verify_key = VerifyKey(bytes(sender_pubkey))
        verify_key.verify(message_hash.encode(), sig_bytes)

        # If verification didn't raise, signature is valid
        recovered_address = message.sender
        if expected_signer:
            is_valid = recovered_address == expected_signer
        else:
            is_valid = True

        return is_valid, recovered_address

    except Exception as e:
        print(f"Signature verification failed: {e}")
        return False, None


def is_message_fresh(message: A2AMessage, max_age_ms: int = 5 * 60 * 1000) -> bool:
    """
    Check if message timestamp is within acceptable range.
    
    Args:
        message: The A2A message
        max_age_ms: Maximum message age in milliseconds (default 5 minutes)
        
    Returns:
        True if message is fresh
    """
    if not message.timestamp:
        return False
    current_time = int(time.time() * 1000)
    return (current_time - message.timestamp) < max_age_ms


def create_error_response(
    request_id: int,
    code: A2AErrorCode,
    message: str,
    data: Optional[Any] = None
) -> A2AResponse:
    """Create a standard A2A error response"""
    return A2AResponse(
        id=request_id,
        error=A2AError(code=code.value, message=message, data=data)
    )


def create_success_response(request_id: int, result: Any) -> A2AResponse:
    """Create a standard A2A success response"""
    return A2AResponse(id=request_id, result=result)


# Task-related models for A2A communication

class TaskRequest(BaseModel):
    """Task execution request parameters"""
    job_id: int
    task_type: str
    description: str
    parameters: dict = Field(default_factory=dict)
    deadline: Optional[int] = None


class TaskResult(BaseModel):
    """Task execution result"""
    job_id: int
    status: str  # "completed", "failed", "partial"
    result_uri: Optional[str] = None  # Storage URI
    proof_hash: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    error: Optional[str] = None
