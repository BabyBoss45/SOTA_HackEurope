"""
HMAC payload signing and verification for ClawBot external agent protocol.

Signature format (Stripe-style):
  t=<unix_timestamp>,v1=<hmac_sha256_hex>

The signed message is: "{timestamp}.{sorted_json_body}"
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


class HMACSigner:
    """
    Sign outgoing payloads and verify incoming HMAC signatures.

    Both the platform and the external ClawBot hold the same shared secret
    (stored AES-256 encrypted in ExternalAgent.publicKey).
    """

    TOLERANCE_SECONDS: int = 300  # ±5 minutes clock skew tolerance

    def sign(self, payload: dict[str, Any], key_hex: str) -> str:
        """
        Create a signature header value for the given payload.

        Returns: "t=<unix_ts>,v1=<hmac_sha256_hex>"
        """
        ts = int(time.time())
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        message = f"{ts}.{body}"
        key_bytes = bytes.fromhex(key_hex)
        sig = hmac.new(key_bytes, message.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    def verify(self, payload: dict[str, Any], signature_header: str, key_hex: str) -> bool:
        """
        Verify an incoming signature header.

        Returns False if the header is malformed, the timestamp is outside
        the tolerance window, or the HMAC does not match.
        """
        try:
            parts = dict(p.split('=', 1) for p in signature_header.split(','))
            ts = int(parts.get('t', 0))
            received_sig = parts.get('v1', '')
        except (ValueError, KeyError):
            return False

        if abs(time.time() - ts) > self.TOLERANCE_SECONDS:
            return False

        body = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        message = f"{ts}.{body}"
        key_bytes = bytes.fromhex(key_hex)
        expected = hmac.new(key_bytes, message.encode('utf-8'), hashlib.sha256).hexdigest()

        # Constant-time comparison prevents timing attacks
        return hmac.compare_digest(expected, received_sig)
