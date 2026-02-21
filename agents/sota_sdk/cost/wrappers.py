"""Thin wrappers around paid-python's provider integrations.

Each ``wrap_*`` helper accepts a raw provider client and returns
the Paid-instrumented version so every LLM call is automatically
cost-tracked.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_INSTALL_HINT = (
    "paid-python is not installed. Install with: pip install paid-python>=1.0.5"
)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def wrap_openai(client: Any) -> Any:
    """Wrap an OpenAI or AsyncOpenAI client with Paid.ai cost tracking.

    Returns the original client unchanged if paid-python is not installed.
    """
    try:
        from openai import AsyncOpenAI
        from paid.tracing.wrappers.openai import PaidAsyncOpenAI, PaidOpenAI
    except ImportError:
        logger.warning(_INSTALL_HINT)
        return client

    if isinstance(client, AsyncOpenAI):
        return PaidAsyncOpenAI(client)
    return PaidOpenAI(client)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def wrap_anthropic(client: Any) -> Any:
    """Wrap an Anthropic or AsyncAnthropic client with Paid.ai cost tracking.

    Returns the original client unchanged if paid-python is not installed.
    """
    try:
        from anthropic import AsyncAnthropic
        from paid.tracing.wrappers.anthropic import PaidAnthropic, PaidAsyncAnthropic
    except ImportError:
        logger.warning(_INSTALL_HINT)
        return client

    if isinstance(client, AsyncAnthropic):
        return PaidAsyncAnthropic(client)
    return PaidAnthropic(client)


# ---------------------------------------------------------------------------
# Google GenAI (Gemini)
# ---------------------------------------------------------------------------

def wrap_gemini(client: Any) -> Any:
    """Wrap a Google GenAI client with Paid.ai cost tracking.

    Returns the original client unchanged if paid-python is not installed.
    """
    try:
        from paid.tracing.wrappers.google_genai import PaidGoogleGenAI
    except ImportError:
        logger.warning(_INSTALL_HINT)
        return client

    return PaidGoogleGenAI(client)


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

def wrap_mistral(client: Any) -> Any:
    """Wrap a Mistral client with Paid.ai cost tracking.

    Returns the original client unchanged if paid-python is not installed.
    """
    try:
        from paid.tracing.wrappers.mistral import PaidMistral
    except ImportError:
        logger.warning(_INSTALL_HINT)
        return client

    return PaidMistral(client)


# ---------------------------------------------------------------------------
# Auto-instrument (monkey-patches all supported libraries globally)
# ---------------------------------------------------------------------------

_DEFAULT_LIBRARIES = ["openai", "anthropic", "google_genai", "mistral"]


def auto_instrument(libraries: list[str] | None = None) -> None:
    """Globally instrument LLM libraries so *every* call is cost-tracked.

    Args:
        libraries: Subset of libraries to instrument.  Defaults to all
                   supported providers: openai, anthropic, google_genai,
                   mistral.

    No-op if paid-python is not installed.
    """
    try:
        from paid.tracing import paid_autoinstrument
    except ImportError:
        logger.warning(_INSTALL_HINT)
        return

    targets = libraries or _DEFAULT_LIBRARIES
    paid_autoinstrument(libraries=targets)
    logger.info("Auto-instrumented LLM libraries: %s", targets)
