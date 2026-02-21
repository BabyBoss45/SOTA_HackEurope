"""Manual cost reporting and outcome signals sent to Paid.ai."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _validate_amount(amount: float) -> None:
    if not isinstance(amount, (int, float)):
        raise TypeError(f"amount must be a number, got {type(amount).__name__}")
    if amount < 0:
        raise ValueError(f"amount must be non-negative, got {amount}")


def _validate_non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")


def report(
    vendor: str,
    amount: float,
    currency: str = "USD",
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Report an external (non-LLM) cost to Paid.ai.

    Example::

        cost.report(vendor="twilio", amount=0.014, currency="USD")
        cost.report(
            vendor="elevenlabs", amount=0.85, currency="USD",
            metadata={"conversation_id": "conv_abc", "duration_secs": 47},
        )
    """
    _validate_non_empty(vendor, "vendor")
    _validate_amount(amount)

    try:
        from paid.tracing import signal
    except ImportError:
        logger.warning("paid-python not installed — cost.report() is a no-op")
        return

    data: dict[str, Any] = {
        "costData": {
            "vendor": vendor,
            "cost": {"amount": amount, "currency": currency},
            "gen_ai.response.model": model if model is not None else vendor,
        },
    }
    if metadata:
        data["metadata"] = metadata

    signal(event_name="external_cost", data=data)
    logger.debug("Reported external cost: %s $%.4f", vendor, amount)


def report_tokens(
    vendor: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    amount: float = 0.0,
    currency: str = "USD",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Report token-based costs (e.g. self-hosted LLMs).

    Example::

        cost.report_tokens(
            vendor="self-hosted", model="llama-3-70b",
            input_tokens=500, output_tokens=200, amount=0.0,
        )
    """
    _validate_non_empty(vendor, "vendor")
    _validate_non_empty(model, "model")
    _validate_amount(amount)

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError(
            f"token counts must be non-negative, got input={input_tokens}, output={output_tokens}"
        )

    try:
        from paid.tracing import signal
    except ImportError:
        logger.warning("paid-python not installed — cost.report_tokens() is a no-op")
        return

    data: dict[str, Any] = {
        "costData": {
            "vendor": vendor,
            "cost": {"amount": amount, "currency": currency},
            "attributes": {
                "gen_ai.response.model": model,
                "gen_ai.usage.input_tokens": input_tokens,
                "gen_ai.usage.output_tokens": output_tokens,
            },
        },
    }
    if metadata:
        data["metadata"] = metadata

    signal(event_name="external_cost", data=data)
    logger.debug(
        "Reported token cost: %s/%s %d+%d tokens $%.4f",
        vendor, model, input_tokens, output_tokens, amount,
    )


def send_outcome(
    job_id: str,
    agent_name: str,
    revenue_usdc: float,
    success: bool,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Signal that a job completed — links all auto-captured LLM costs.

    Called at the end of ``SOTAAgent._run_job`` inside the
    ``paid_tracing`` context manager so that costs are correctly
    attributed to this customer/product pair.
    """
    _validate_non_empty(job_id, "job_id")
    _validate_non_empty(agent_name, "agent_name")

    try:
        from paid.tracing import signal
    except ImportError:
        logger.warning("paid-python not installed — cost.send_outcome() is a no-op")
        return

    data: dict[str, Any] = {
        "job_id": job_id,
        "agent": agent_name,
        "revenue_usdc": revenue_usdc,
        "success": success,
    }
    if metadata:
        data["metadata"] = metadata

    try:
        signal(
            event_name="job_completed",
            data=data,
            enable_cost_tracing=True,
        )
    except TypeError:
        signal(event_name="job_completed", data=data)
    logger.info(
        "Outcome signal sent: job=%s agent=%s revenue=$%.2f success=%s",
        job_id, agent_name, revenue_usdc, success,
    )
