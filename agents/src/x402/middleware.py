"""
x402 Payment Middleware for FastAPI

Implements the x402 payment protocol:
- Returns 402 Payment Required with payment details when no payment header present
- Verifies on-chain USDC (SPL Token) transfers via X-PAYMENT header (base64-encoded JSON)
- Checks transaction on Solana Devnet for validity
"""

import os
import json
import asyncio
import base64
import logging
import sqlite3
import threading
from typing import Optional

from fastapi import Request, HTTPException, Depends
from solana.rpc.api import Client
from solders.signature import Signature

logger = logging.getLogger(__name__)

# Persistent replay protection using SQLite (survives restarts)
_replay_db_path = os.getenv("X402_REPLAY_DB", "x402_used_tx.db")
_replay_db_lock = threading.Lock()


def _init_replay_db():
    """Initialize the replay protection database."""
    conn = sqlite3.connect(_replay_db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS used_tx (tx_signature TEXT PRIMARY KEY, used_at REAL)"
    )
    conn.commit()
    conn.close()


_init_replay_db()


def _is_tx_used(tx_signature: str) -> bool:
    with _replay_db_lock:
        conn = sqlite3.connect(_replay_db_path)
        row = conn.execute(
            "SELECT 1 FROM used_tx WHERE tx_signature = ?", (tx_signature,)
        ).fetchone()
        conn.close()
        return row is not None


def _mark_tx_used(tx_signature: str) -> None:
    import time
    with _replay_db_lock:
        conn = sqlite3.connect(_replay_db_path)
        conn.execute(
            "INSERT OR IGNORE INTO used_tx (tx_signature, used_at) VALUES (?, ?)",
            (tx_signature, time.time()),
        )
        conn.commit()
        conn.close()


# Cached config (loaded once at module level to avoid re-reading env vars per request)
_cached_config: tuple[str, str, str] | None = None

# Singleton Solana RPC client
_solana_client: Client | None = None


def _get_config():
    """Load chain config from environment or shared config (cached after first call)."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    try:
        from agents.src.shared.chain_config import get_cluster, USDC_MINT
        cluster = get_cluster()
        rpc_url = cluster.rpc_url
        usdc_mint = str(USDC_MINT)
    except Exception:
        rpc_url = os.getenv("RPC_URL", "https://api.devnet.solana.com")
        usdc_mint = os.getenv("USDC_MINT", "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU")

    platform_wallet = os.getenv(
        "PLATFORM_WALLET_ADDRESS",
        os.getenv("PLATFORM_PAY_TO_ADDRESS", ""),
    )

    _cached_config = (rpc_url, usdc_mint, platform_wallet)
    return _cached_config


def _get_client() -> Client:
    """Return a singleton Solana RPC client."""
    global _solana_client
    if _solana_client is None:
        rpc_url, _, _ = _get_config()
        _solana_client = Client(rpc_url)
    return _solana_client


def _build_payment_request(price_usdc: float, resource: str) -> dict:
    """Build the 402 Payment Required response body per x402 spec."""
    _, usdc_mint, platform_wallet = _get_config()

    # Convert to raw amount (6 decimals)
    max_amount = str(int(price_usdc * 1e6))

    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "solana-devnet",
                "maxAmountRequired": max_amount,
                "resource": resource,
                "payTo": platform_wallet,
                "asset": usdc_mint,
                "extra": {
                    "name": "USDC",
                    "decimals": 6,
                },
            }
        ],
    }


async def _verify_payment(payment_header: str, price_usdc: float) -> bool:
    """
    Verify an on-chain payment from the X-PAYMENT header.

    Expected header value: base64-encoded JSON with:
      { "txSignature": "...", "cluster": "devnet" }

    Verification checks:
    1. Transaction succeeded (meta.err is None)
    2. Contains an SPL Token transfer to the platform wallet
    3. Transfer amount >= required price
    4. Slot is recent (within last 150 slots)
    """
    rpc_url, usdc_mint, platform_wallet = _get_config()

    try:
        decoded = base64.b64decode(payment_header)
        proof = json.loads(decoded)
    except Exception as e:
        logger.warning(f"Failed to decode X-PAYMENT header: {e}")
        return False

    tx_sig = proof.get("txSignature")
    if not tx_sig:
        logger.warning("Missing txSignature in payment proof")
        return False

    # Replay protection: reject reused transaction signatures (persistent across restarts)
    if await asyncio.to_thread(_is_tx_used, tx_sig):
        logger.warning(f"Transaction {tx_sig} already used for a previous request")
        return False

    try:
        client = _get_client()

        sig = Signature.from_string(tx_sig)
        resp = client.get_transaction(sig, max_supported_transaction_version=0)

        if resp.value is None:
            logger.warning(f"Transaction {tx_sig} not found")
            return False

        tx_data = resp.value

        # Check transaction succeeded
        meta = tx_data.transaction.meta
        if meta is None or meta.err is not None:
            logger.warning(f"Transaction {tx_sig} failed (meta.err={meta.err if meta else 'no meta'})")
            return False

        # Check slot recency (within last 150 slots, ~1 minute on devnet)
        current_slot = client.get_slot().value
        if current_slot - tx_data.slot > 150:
            logger.warning(f"Transaction {tx_sig} is too old (slot {tx_data.slot}, current {current_slot})")
            return False

        # Verify SPL Token transfer to platform wallet for >= required amount
        required_amount = int(price_usdc * 1e6)

        # Check pre/post token balances for USDC transfers
        if meta.pre_token_balances and meta.post_token_balances:
            for post_bal in meta.post_token_balances:
                post_mint = str(post_bal.mint)
                if post_mint != usdc_mint:
                    continue

                post_owner = str(post_bal.owner) if post_bal.owner else ""
                if post_owner != platform_wallet:
                    continue

                # Find the matching pre-balance
                pre_amount = 0
                for pre_bal in meta.pre_token_balances:
                    pre_owner = str(pre_bal.owner) if pre_bal.owner else ""
                    if str(pre_bal.mint) == usdc_mint and pre_owner == platform_wallet:
                        pre_amount = int(pre_bal.ui_token_amount.amount)
                        break

                post_amount = int(post_bal.ui_token_amount.amount)
                transfer_amount = post_amount - pre_amount

                if transfer_amount >= required_amount:
                    logger.info(
                        f"Payment verified: {tx_sig}, amount={transfer_amount}, required={required_amount}"
                    )
                    await asyncio.to_thread(_mark_tx_used, tx_sig)
                    return True

        logger.warning(f"No matching USDC transfer found in {tx_sig}")
        return False

    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return False


def x402_required(price_usdc: float):
    """
    FastAPI dependency that enforces x402 payment.

    Usage:
        @app.get("/data", dependencies=[x402_required(0.01)])
        async def get_data(): ...
    """

    async def verify(request: Request):
        payment_header = request.headers.get("X-PAYMENT")

        if not payment_header:
            payment_request = _build_payment_request(
                price_usdc, str(request.url)
            )
            raise HTTPException(
                status_code=402,
                detail=payment_request,
            )

        is_valid = await _verify_payment(payment_header, price_usdc)
        if not is_valid:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment verification failed",
                    **_build_payment_request(price_usdc, str(request.url)),
                },
            )

    return Depends(verify)
