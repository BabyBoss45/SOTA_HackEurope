"""Cost tracking configuration — reads env vars and initializes paid-python tracing."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized: bool = False

_FALSY_VALUES = frozenset({"false", "0", "no", "off", ""})


def is_tracking_enabled() -> bool:
    """Return True when Paid.ai cost tracking is active."""
    return _initialized


def initialize_cost_tracking() -> None:
    """Called once at agent startup to wire up Paid.ai tracing.

    Reads:
        SOTA_PAID_API_KEY  – Paid.ai API key (required to enable tracking)
        PAID_ENABLED       – set to "false"/"0"/"no"/"off" to force-disable
                             (default "true")

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _initialized

    if _initialized:
        return

    api_key = os.getenv("SOTA_PAID_API_KEY", "").strip()
    paid_enabled = os.getenv("PAID_ENABLED", "true").strip().lower()

    if not api_key or paid_enabled in _FALSY_VALUES:
        logger.info("Cost tracking disabled (key=%s, enabled=%s)",
                     "set" if api_key else "missing", paid_enabled)
        return

    try:
        from paid.tracing import initialize_tracing
    except ImportError:
        logger.warning(
            "paid-python is not installed — cost tracking unavailable. "
            "Install with: pip install paid-python>=1.0.5"
        )
        return

    initialize_tracing(api_key=api_key)

    from .wrappers import auto_instrument
    auto_instrument()

    _initialized = True
    logger.info("Paid.ai cost tracking initialized")
