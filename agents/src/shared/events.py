"""
Blockchain Event Listener for Archive Agents — Solana Edition

Watches for Anchor program events by polling recent transaction signatures
and parsing CPI log messages. Each Anchor event is emitted as a base64-encoded
blob prefixed with an 8-byte discriminator (SHA-256 of "event:<EventName>").

Uses AsyncClient for non-blocking RPC calls.
"""

import os
import json
import asyncio
import base64
import hashlib
import struct
import logging
from collections import OrderedDict
from typing import Callable, Awaitable, Optional, Any
from dataclasses import dataclass
from enum import Enum

from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

from .chain_config import get_rpc_url, PROGRAM_ID

logger = logging.getLogger(__name__)


# ── Anchor event discriminator helper ──────────────────────────

def _anchor_event_discriminator(event_name: str) -> bytes:
    """
    Compute the 8-byte Anchor event discriminator.
    Anchor uses SHA-256("event:<EventName>")[:8].
    """
    digest = hashlib.sha256(f"event:{event_name}".encode()).digest()
    return digest[:8]


# Pre-compute discriminators for all events we care about
_EVENT_DISCRIMINATORS = {
    "JobCreated": _anchor_event_discriminator("JobCreated"),
    "BidPlaced": _anchor_event_discriminator("BidPlaced"),
    "BidAccepted": _anchor_event_discriminator("BidAccepted"),
    "JobCompletedEvent": _anchor_event_discriminator("JobCompletedEvent"),
    "ProviderAssigned": _anchor_event_discriminator("ProviderAssigned"),
    "JobReleased": _anchor_event_discriminator("JobReleased"),
    "JobCancelled": _anchor_event_discriminator("JobCancelled"),
    "AgentRegistered": _anchor_event_discriminator("AgentRegistered"),
    "PaymentReleased": _anchor_event_discriminator("PaymentReleased"),
}


class EventType(str, Enum):
    """Contract event types we care about (Anchor program)"""
    JOB_POSTED = "JobCreated"
    BID_PLACED = "BidPlaced"
    BID_ACCEPTED = "BidAccepted"
    DELIVERY_SUBMITTED = "JobCompletedEvent"
    PROVIDER_ASSIGNED = "ProviderAssigned"
    JOB_RELEASED = "JobReleased"
    JOB_CANCELLED = "JobCancelled"
    AGENT_REGISTERED = "AgentRegistered"


@dataclass
class JobPostedEvent:
    """Parsed JobCreated event from Anchor program"""
    job_id: int
    client: str        # poster pubkey (base58)
    job_type: int      # not in event; default 0
    budget: int        # max_budget_usdc (raw u64)
    budget_usdc: int   # max_budget_usdc (raw u64, same)
    deadline: int      # not in event; default 0
    description: str   # not in event; default ''
    block_number: int  # slot number
    tx_hash: str       # transaction signature (base58)


@dataclass
class BidPlacedEvent:
    """Parsed BidPlaced event from Anchor program"""
    job_id: int
    bid_id: int
    bidder: str        # agent pubkey (base58)
    amount: int        # price_usdc (raw u64)
    amount_usdc: int   # price_usdc (raw u64, same)
    estimated_time: int  # not in event; default 0
    block_number: int
    tx_hash: str


@dataclass
class BidAcceptedEvent:
    """Parsed BidAccepted event from Anchor program"""
    job_id: int
    bid_id: int
    worker: str        # provider pubkey (base58)
    amount: int        # not in event; default 0
    block_number: int
    tx_hash: str


@dataclass
class DeliverySubmittedEvent:
    """Parsed JobCompletedEvent from Anchor program"""
    job_id: int
    worker: str        # not in event; default ''
    result_uri: str    # not in event; default ''
    delivery_proof: str  # 32-byte proof as hex
    timestamp: int     # not in event; default 0
    block_number: int
    tx_hash: str


# Aliases for convenience
BidSubmittedEvent = BidPlacedEvent


EventCallback = Callable[[Any], Awaitable[None]]


# ── Anchor log parsing ─────────────────────────────────────────

def _parse_anchor_events_from_logs(log_messages: list[str]) -> list[tuple[str, bytes]]:
    """
    Extract Anchor events from transaction log messages.

    Anchor emits events as:
        Program data: <base64-encoded data>

    The data is: 8-byte discriminator + borsh-serialized fields.

    Returns a list of (event_name, raw_data_after_discriminator) tuples.
    """
    events = []
    for msg in log_messages:
        if not msg.startswith("Program data: "):
            continue
        b64_data = msg[len("Program data: "):]
        try:
            raw = base64.b64decode(b64_data)
        except Exception:
            continue

        if len(raw) < 8:
            continue

        disc = raw[:8]
        payload = raw[8:]

        for event_name, expected_disc in _EVENT_DISCRIMINATORS.items():
            if disc == expected_disc:
                events.append((event_name, payload))
                break

    return events


def _parse_pubkey(data: bytes, offset: int) -> tuple[str, int]:
    """Read a 32-byte pubkey from borsh data, return (base58_str, new_offset)."""
    pk_bytes = data[offset:offset + 32]
    pk = Pubkey.from_bytes(pk_bytes)
    return str(pk), offset + 32


def _parse_u64(data: bytes, offset: int) -> tuple[int, int]:
    """Read a u64 from borsh data, return (value, new_offset)."""
    val = struct.unpack_from("<Q", data, offset)[0]
    return val, offset + 8


def _parse_u8_array_32(data: bytes, offset: int) -> tuple[str, int]:
    """Read a [u8; 32] from borsh data, return (hex_string, new_offset)."""
    arr = data[offset:offset + 32]
    return arr.hex(), offset + 32


def _parse_job_created(payload: bytes) -> dict:
    """Parse JobCreated event: { job_id: u64, poster: Pubkey, max_budget_usdc: u64 }"""
    offset = 0
    job_id, offset = _parse_u64(payload, offset)
    poster, offset = _parse_pubkey(payload, offset)
    max_budget_usdc, offset = _parse_u64(payload, offset)
    return {"job_id": job_id, "poster": poster, "max_budget_usdc": max_budget_usdc}


def _parse_bid_placed(payload: bytes) -> dict:
    """Parse BidPlaced event: { job_id: u64, bid_id: u64, agent: Pubkey, price_usdc: u64 }"""
    offset = 0
    job_id, offset = _parse_u64(payload, offset)
    bid_id, offset = _parse_u64(payload, offset)
    agent, offset = _parse_pubkey(payload, offset)
    price_usdc, offset = _parse_u64(payload, offset)
    return {"job_id": job_id, "bid_id": bid_id, "agent": agent, "price_usdc": price_usdc}


def _parse_bid_accepted(payload: bytes) -> dict:
    """Parse BidAccepted event: { job_id: u64, bid_id: u64, provider: Pubkey }"""
    offset = 0
    job_id, offset = _parse_u64(payload, offset)
    bid_id, offset = _parse_u64(payload, offset)
    provider, offset = _parse_pubkey(payload, offset)
    return {"job_id": job_id, "bid_id": bid_id, "provider": provider}


def _parse_job_completed(payload: bytes) -> dict:
    """Parse JobCompletedEvent: { job_id: u64, delivery_proof: [u8; 32] }"""
    offset = 0
    job_id, offset = _parse_u64(payload, offset)
    proof_hex, offset = _parse_u8_array_32(payload, offset)
    return {"job_id": job_id, "delivery_proof": proof_hex}


_EVENT_PARSERS = {
    "JobCreated": _parse_job_created,
    "BidPlaced": _parse_bid_placed,
    "BidAccepted": _parse_bid_accepted,
    "JobCompletedEvent": _parse_job_completed,
}


# ── Event Listener ─────────────────────────────────────────────

class EventListener:
    """
    Async event listener for the SOTA Anchor program.

    Polls recent transaction signatures for the program ID and parses
    Anchor events from transaction logs.
    """

    def __init__(
        self,
        poll_interval: int = 3,
        confirmations: int = 1,
    ):
        """
        Initialize event listener.

        Args:
            poll_interval: Seconds between polls
            confirmations: Not used on Solana (kept for API compat)
        """
        self.rpc_url = get_rpc_url()
        self.program_id = PROGRAM_ID
        self.poll_interval = poll_interval
        self.confirmations = confirmations

        # Callbacks per event type
        self._callbacks: dict[EventType, list[EventCallback]] = {
            et: [] for et in EventType
        }

        # State
        self._running = False
        self._last_signature: Optional[str] = None
        self._client: Optional[AsyncClient] = None
        self._seen_signatures: OrderedDict[str, bool] = OrderedDict()

    async def _ensure_client(self):
        """Lazily create the async RPC client."""
        if self._client is None:
            self._client = AsyncClient(self.rpc_url)

    def on_event(self, event_type: EventType, callback: EventCallback):
        """
        Register a callback for an event type.

        Args:
            event_type: Type of event to listen for
            callback: Async function to call when event occurs
        """
        self._callbacks[event_type].append(callback)
        logger.debug(f"Registered callback for {event_type.value}")

    def on_job_posted(self, callback: Callable[[JobPostedEvent], Awaitable[None]]):
        """Register callback for JobPosted events"""
        self.on_event(EventType.JOB_POSTED, callback)

    def on_bid_placed(self, callback: Callable[[BidPlacedEvent], Awaitable[None]]):
        """Register callback for BidPlaced events"""
        self.on_event(EventType.BID_PLACED, callback)

    # Alias for on_bid_placed
    on_bid_submitted = on_bid_placed

    def on_bid_accepted(self, callback: Callable[[BidAcceptedEvent], Awaitable[None]]):
        """Register callback for BidAccepted events"""
        self.on_event(EventType.BID_ACCEPTED, callback)

    def on_delivery_submitted(self, callback: Callable[[DeliverySubmittedEvent], Awaitable[None]]):
        """Register callback for DeliverySubmitted events"""
        self.on_event(EventType.DELIVERY_SUBMITTED, callback)

    async def _process_job_posted(self, args: dict, slot: int, sig: str):
        """Parse and dispatch JobCreated event"""
        parsed = JobPostedEvent(
            job_id=args.get("job_id", 0),
            client=args.get("poster", ""),
            job_type=0,
            budget=args.get("max_budget_usdc", 0),
            budget_usdc=args.get("max_budget_usdc", 0),
            deadline=0,
            description="",
            block_number=slot,
            tx_hash=sig,
        )
        logger.info(
            "JobCreated evt job_id=%s poster=%s budget_usdc=%s tx=%s",
            parsed.job_id, parsed.client, parsed.budget, parsed.tx_hash[:16],
        )
        for callback in self._callbacks[EventType.JOB_POSTED]:
            try:
                await callback(parsed)
            except Exception as e:
                logger.error(f"Error in JobCreated callback: {e}")

    async def _process_bid_placed(self, args: dict, slot: int, sig: str):
        """Parse and dispatch BidPlaced event"""
        parsed = BidPlacedEvent(
            job_id=args.get("job_id", 0),
            bid_id=args.get("bid_id", 0),
            bidder=args.get("agent", ""),
            amount=args.get("price_usdc", 0),
            amount_usdc=args.get("price_usdc", 0),
            estimated_time=0,
            block_number=slot,
            tx_hash=sig,
        )
        logger.info(
            "BidPlaced evt job_id=%s bid_id=%s agent=%s price_usdc=%s tx=%s",
            parsed.job_id, parsed.bid_id, parsed.bidder, parsed.amount, parsed.tx_hash[:16],
        )
        for callback in self._callbacks[EventType.BID_PLACED]:
            try:
                await callback(parsed)
            except Exception as e:
                logger.error(f"Error in BidPlaced callback: {e}")

    async def _process_bid_accepted(self, args: dict, slot: int, sig: str):
        """Parse and dispatch BidAccepted event"""
        parsed = BidAcceptedEvent(
            job_id=args.get("job_id", 0),
            bid_id=args.get("bid_id", 0),
            worker=args.get("provider", ""),
            amount=0,
            block_number=slot,
            tx_hash=sig,
        )
        logger.info(
            "BidAccepted evt job_id=%s bid_id=%s provider=%s tx=%s",
            parsed.job_id, parsed.bid_id, parsed.worker, parsed.tx_hash[:16],
        )
        for callback in self._callbacks[EventType.BID_ACCEPTED]:
            try:
                await callback(parsed)
            except Exception as e:
                logger.error(f"Error in BidAccepted callback: {e}")

    async def _process_delivery_submitted(self, args: dict, slot: int, sig: str):
        """Parse and dispatch JobCompletedEvent"""
        parsed = DeliverySubmittedEvent(
            job_id=args.get("job_id", 0),
            worker="",
            result_uri="",
            delivery_proof=args.get("delivery_proof", ""),
            timestamp=0,
            block_number=slot,
            tx_hash=sig,
        )
        proof_short = parsed.delivery_proof[:16] if parsed.delivery_proof else ""
        logger.info(
            "JobCompleted evt job_id=%s proof=%s tx=%s",
            parsed.job_id, proof_short, parsed.tx_hash[:16],
        )
        for callback in self._callbacks[EventType.DELIVERY_SUBMITTED]:
            try:
                await callback(parsed)
            except Exception as e:
                logger.error(f"Error in DeliverySubmitted callback: {e}")

    # Map event names to processor methods
    _EVENT_TYPE_MAP = {
        "JobCreated": EventType.JOB_POSTED,
        "BidPlaced": EventType.BID_PLACED,
        "BidAccepted": EventType.BID_ACCEPTED,
        "JobCompletedEvent": EventType.DELIVERY_SUBMITTED,
    }

    async def _process_event(self, event_name: str, payload: bytes, slot: int, sig: str):
        """Route a parsed event to the appropriate processor."""
        parser = _EVENT_PARSERS.get(event_name)
        if not parser:
            return

        try:
            args = parser(payload)
        except Exception as e:
            logger.warning("Failed to parse %s event: %s", event_name, e)
            return

        if event_name == "JobCreated":
            await self._process_job_posted(args, slot, sig)
        elif event_name == "BidPlaced":
            await self._process_bid_placed(args, slot, sig)
        elif event_name == "BidAccepted":
            await self._process_bid_accepted(args, slot, sig)
        elif event_name == "JobCompletedEvent":
            await self._process_delivery_submitted(args, slot, sig)

    async def _poll_events(self):
        """Poll for new events by fetching recent transaction signatures."""
        await self._ensure_client()

        try:
            # Fetch recent signatures for the program
            # Use "until" to get sigs newer than the last processed one
            opts = {
                "limit": 50,
                "commitment": "confirmed",
            }

            resp = await self._client.get_signatures_for_address(
                self.program_id,
                limit=50,
                commitment=Confirmed,
                until=Signature.from_string(self._last_signature) if self._last_signature else None,
            )

            if not resp.value:
                return

            # Signatures come in reverse chronological order (newest first)
            # Process oldest first for correct ordering
            sig_infos = list(reversed(resp.value))

            new_sigs = []
            for info in sig_infos:
                sig_str = str(info.signature)
                if sig_str in self._seen_signatures:
                    continue
                # Skip failed transactions
                if info.err is not None:
                    self._seen_signatures[sig_str] = True
                    continue
                new_sigs.append(info)

            if not new_sigs:
                return

            logger.debug(f"Processing {len(new_sigs)} new transactions")

            for info in new_sigs:
                sig_str = str(info.signature)
                self._seen_signatures[sig_str] = True
                slot = info.slot

                # Check which event types have callbacks registered
                has_callbacks = any(
                    self._callbacks.get(et) for et in EventType
                )
                if not has_callbacks:
                    continue

                # Fetch full transaction to get logs
                try:
                    tx_resp = await self._client.get_transaction(
                        info.signature,
                        encoding="json",
                        max_supported_transaction_version=0,
                    )

                    if not tx_resp.value:
                        continue

                    tx_data = tx_resp.value
                    meta = tx_data.transaction.meta
                    if meta is None:
                        continue

                    log_messages = meta.log_messages if meta.log_messages else []

                    # Parse Anchor events from logs
                    events = _parse_anchor_events_from_logs(log_messages)
                    for event_name, payload in events:
                        await self._process_event(event_name, payload, slot, sig_str)

                except Exception as e:
                    logger.debug(f"Error fetching tx {sig_str[:16]}: {e}")

            # Update last signature to the newest one processed
            self._last_signature = str(new_sigs[-1].signature)

            # Prune seen signatures to prevent unbounded growth
            while len(self._seen_signatures) > 5000:
                self._seen_signatures.popitem(last=False)

        except Exception as e:
            logger.error(f"Error polling events: {e}")

    async def start(self):
        """Start the event listener"""
        logger.info("Starting Solana event listener (program=%s)...", str(self.program_id)[:16])
        await self._ensure_client()
        self._running = True

        while self._running:
            await self._poll_events()
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        """Stop the event listener"""
        logger.info("Stopping event listener...")
        self._running = False

    async def close(self):
        """Close the async client."""
        if self._client:
            await self._client.close()
            self._client = None

    async def catch_up(self, lookback_count: int = 50):
        """
        Process recent events immediately (e.g., jobs posted before agent startup).

        Args:
            lookback_count: Number of recent signatures to scan.
        """
        await self._ensure_client()
        try:
            resp = await self._client.get_signatures_for_address(
                self.program_id,
                limit=lookback_count,
                commitment=Confirmed,
            )

            if not resp.value:
                logger.info("No recent transactions found for catch-up")
                return

            # Process oldest first
            sig_infos = list(reversed(resp.value))
            logger.info("Catching up on %d recent transactions", len(sig_infos))

            for info in sig_infos:
                sig_str = str(info.signature)
                if info.err is not None:
                    self._seen_signatures[sig_str] = True
                    continue
                if sig_str in self._seen_signatures:
                    continue

                self._seen_signatures[sig_str] = True
                slot = info.slot

                try:
                    tx_resp = await self._client.get_transaction(
                        info.signature,
                        encoding="json",
                        max_supported_transaction_version=0,
                    )
                    if not tx_resp.value:
                        continue

                    meta = tx_resp.value.transaction.meta
                    if meta is None:
                        continue

                    log_messages = meta.log_messages if meta.log_messages else []
                    events = _parse_anchor_events_from_logs(log_messages)
                    for event_name, payload in events:
                        await self._process_event(event_name, payload, slot, sig_str)

                except Exception as e:
                    logger.debug(f"Catch-up: error fetching tx {sig_str[:16]}: {e}")

            # Set last signature to newest
            if sig_infos:
                self._last_signature = str(sig_infos[-1].signature)

        except Exception as e:
            logger.error("Catch-up failed: %s", e)

    async def run_once(self):
        """Poll events once (for testing)"""
        await self._ensure_client()
        await self._poll_events()


def create_event_listener(poll_interval: int = 3) -> EventListener:
    """Create a new event listener instance"""
    return EventListener(poll_interval=poll_interval)
