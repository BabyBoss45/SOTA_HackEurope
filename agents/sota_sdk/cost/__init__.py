"""SOTA SDK Cost Module — Paid.ai integration for LLM and external cost tracking.

Quick start::

    from sota_sdk import cost

    # Wrap LLM clients (one line each)
    client = cost.wrap_openai(AsyncOpenAI(...))
    client = cost.wrap_anthropic(AsyncAnthropic(...))
    client = cost.wrap_gemini(genai.Client(...))
    client = cost.wrap_mistral(Mistral(...))

    # Or auto-instrument all libraries globally
    cost.auto_instrument()

    # Report external API costs manually
    cost.report(vendor="twilio", amount=0.014, currency="USD")

    # Report token-based costs (self-hosted LLMs)
    cost.report_tokens(vendor="self-hosted", model="llama-3-70b",
                       input_tokens=500, output_tokens=200, amount=0.0)
"""

from .config import initialize_cost_tracking, is_tracking_enabled
from .signals import report, report_tokens, send_outcome
from .tracker import CostTracker
from .wrappers import auto_instrument, wrap_anthropic, wrap_gemini, wrap_mistral, wrap_openai

__all__ = [
    # Config
    "initialize_cost_tracking",
    "is_tracking_enabled",
    # Wrappers
    "wrap_openai",
    "wrap_anthropic",
    "wrap_gemini",
    "wrap_mistral",
    "auto_instrument",
    # Signals
    "report",
    "report_tokens",
    "send_outcome",
    # Tracker
    "CostTracker",
]
