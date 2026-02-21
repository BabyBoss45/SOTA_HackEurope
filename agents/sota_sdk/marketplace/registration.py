"""
Auto-registration message builder.

Builds the ``register`` payload that the WS client sends immediately
after connecting to the marketplace hub.
"""

from __future__ import annotations

from typing import List, Optional


def build_register_message(
    name: str,
    tags: List[str],
    version: str,
    wallet_address: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
) -> dict:
    """
    Build a ``register`` message matching the hub's expected schema::

        {
            "type": "register",
            "agent": {
                "name": "...",
                "tags": [...],
                "version": "1.0.0",
                "wallet_address": "0x...",
                "capabilities": [...]
            }
        }
    """
    return {
        "type": "register",
        "agent": {
            "name": name,
            "tags": tags,
            "version": version,
            "wallet_address": wallet_address or "",
            "capabilities": capabilities or tags,
        },
    }
