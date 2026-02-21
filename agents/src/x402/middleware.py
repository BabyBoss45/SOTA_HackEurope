"""
x402 Payment Middleware for FastAPI

Implements the x402 payment protocol:
- Returns 402 Payment Required with payment details when no payment header present
- Verifies on-chain MockUSDC transfers via X-PAYMENT header (base64-encoded JSON)
- Checks transaction receipt on Base Sepolia for validity
"""

import os
import json
import base64
import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from web3 import Web3

logger = logging.getLogger(__name__)

# ERC-20 Transfer event topic
TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# In-memory replay protection (hackathon scope — use Redis/DB in production)
_used_tx_hashes: set[str] = set()

# Cached config (loaded once at module level to avoid re-reading env vars per request)
_cached_config: tuple[str, str, str] | None = None


def _get_config():
    """Load chain config from environment or shared config (cached after first call)."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    try:
        from agents.src.shared.chain_config import get_network, get_contract_addresses
        network = get_network()
        contracts = get_contract_addresses()
        rpc_url = network.rpc_url
        usdc_address = contracts.usdc
    except Exception:
        rpc_url = os.getenv("RPC_URL", "https://sepolia.base.org")
        usdc_address = os.getenv("USDC_ADDRESS", "")

    platform_wallet = os.getenv(
        "PLATFORM_WALLET_ADDRESS",
        os.getenv("PLATFORM_PAY_TO_ADDRESS", ""),
    )

    _cached_config = (rpc_url, usdc_address, platform_wallet)
    return _cached_config


def _build_payment_request(price_usdc: float, resource: str) -> dict:
    """Build the 402 Payment Required response body per x402 spec."""
    _, usdc_address, platform_wallet = _get_config()

    # Convert to raw amount (6 decimals)
    max_amount = str(int(price_usdc * 1e6))

    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base-sepolia",
                "maxAmountRequired": max_amount,
                "resource": resource,
                "payTo": platform_wallet,
                "asset": usdc_address,
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
      { "txHash": "0x...", "chainId": 84532 }

    Verification checks:
    1. Transaction succeeded (status == 1)
    2. Contains a Transfer event to the platform wallet
    3. Transfer amount >= required price
    4. Token is MockUSDC
    5. Block is recent (within last 50 blocks)
    """
    rpc_url, usdc_address, platform_wallet = _get_config()

    try:
        decoded = base64.b64decode(payment_header)
        proof = json.loads(decoded)
    except Exception as e:
        logger.warning(f"Failed to decode X-PAYMENT header: {e}")
        return False

    tx_hash = proof.get("txHash")
    chain_id = proof.get("chainId", 84532)

    if not tx_hash:
        logger.warning("Missing txHash in payment proof")
        return False

    if chain_id != 84532:
        logger.warning(f"Wrong chain ID: {chain_id}, expected 84532")
        return False

    # Replay protection: reject reused transaction hashes
    tx_hash_lower = tx_hash.lower()
    if tx_hash_lower in _used_tx_hashes:
        logger.warning(f"Transaction {tx_hash} already used for a previous request")
        return False

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        receipt = w3.eth.get_transaction_receipt(tx_hash)

        # Check transaction succeeded
        if receipt["status"] != 1:
            logger.warning(f"Transaction {tx_hash} failed (status != 1)")
            return False

        # Check block recency (within last 50 blocks)
        current_block = w3.eth.block_number
        if current_block - receipt["blockNumber"] > 50:
            logger.warning(f"Transaction {tx_hash} is too old (block {receipt['blockNumber']}, current {current_block})")
            return False

        # Parse Transfer event logs
        required_amount = int(price_usdc * 1e6)
        usdc_addr_lower = usdc_address.lower()
        pay_to_lower = platform_wallet.lower()

        for log_entry in receipt["logs"]:
            # Check it's from the USDC contract
            if log_entry["address"].lower() != usdc_addr_lower:
                continue

            # Check it's a Transfer event
            if len(log_entry["topics"]) < 3:
                continue
            if log_entry["topics"][0].hex() != TRANSFER_TOPIC:
                continue

            # Decode recipient (topic[2] is the `to` address)
            recipient = "0x" + log_entry["topics"][2].hex()[-40:]
            if recipient.lower() != pay_to_lower:
                continue

            # Decode amount from data (handle both HexBytes and str)
            raw_data = log_entry["data"]
            data_hex = raw_data.hex() if hasattr(raw_data, "hex") else str(raw_data).replace("0x", "")
            amount = int(data_hex, 16)
            if amount >= required_amount:
                logger.info(
                    f"Payment verified: {tx_hash}, amount={amount}, required={required_amount}"
                )
                _used_tx_hashes.add(tx_hash_lower)
                return True

        logger.warning(f"No matching Transfer event found in {tx_hash}")
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
