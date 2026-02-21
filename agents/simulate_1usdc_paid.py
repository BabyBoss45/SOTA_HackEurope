"""
SOTA -- Real 1 USDC Job Simulation with Paid.ai Cost Tracking

Two-system architecture:
  - Paid.ai:   LLM cost tracking (auto-captured via paid_tracing)
  - On-chain:  Revenue flow (Escrow -> OrderBook -> ReputationToken)

This script:
1. Initializes paid_tracing to auto-capture LLM costs
2. Makes a REAL Claude Haiku call inside the tracing context
3. Sends a cost-linked signal so Paid.ai attributes the spend
4. Generates a delivery proof hash (SHA-256)
5. Prints the on-chain payment breakdown (mirrors smart contracts)

Revenue does NOT go through Paid.ai — it flows on-chain via Escrow.
See contracts/scripts/simulate-1usdc-job.ts for the on-chain lifecycle.

Run:
    cd agents && python simulate_1usdc_paid.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time

# Ensure we can import sota_sdk
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(_DIR), ".env"))

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import anthropic
except ImportError:
    sys.exit("ERROR: anthropic package required — pip install anthropic")

from sota_sdk.cost.config import initialize_cost_tracking
from sota_sdk.cost.signals import send_outcome

try:
    from paid.tracing import paid_tracing
except ImportError:
    sys.exit("ERROR: paid-python package required — pip install paid-python")


# ----------------------------------------------------------------
#  Constants
# ----------------------------------------------------------------
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
PLATFORM_FEE_BPS = 200  # 2%
BPS_DENOMINATOR = 10_000
RESULT_PREVIEW_LINES = 15
RESULT_PREVIEW_WIDTH = 70

JOB = {
    "id": "sim-001",
    "description": "Find upcoming AI/ML hackathons in Europe for March 2026",
    "tags": ["hackathon_registration"],
    "budget_usdc": 1.0,
    "bid_amount_usdc": 0.70,
    "poster": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "params": {
        "location": "Europe",
        "date_range": "2026-03-01 to 2026-03-31",
        "theme_technology_focus": "AI, machine learning, blockchain",
        "online_or_in_person": "both",
    },
}

AGENT_NAME = "hackathon-agent"


# ----------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------
def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_job_details() -> None:
    _section("Job details")
    print(f"  Job ID:      {JOB['id']}")
    print(f"  Description: {JOB['description']}")
    print(f"  Budget:      {JOB['budget_usdc']} USDC")
    print(f"  Bid price:   {JOB['bid_amount_usdc']} USDC")
    print(f"  Poster:      {JOB['poster']}")


async def _execute_llm_call() -> tuple[str, anthropic.types.Usage, float]:
    """Run the Claude Haiku call and return (result_text, usage, elapsed_secs)."""
    client = anthropic.AsyncAnthropic()
    prompt = (
        f"You are a hackathon search agent. A user paid 1 USDC for this job.\n\n"
        f"Job: {JOB['description']}\n"
        f"Location: {JOB['params']['location']}\n"
        f"Date range: {JOB['params']['date_range']}\n"
        f"Topics: {JOB['params']['theme_technology_focus']}\n"
        f"Mode: {JOB['params']['online_or_in_person']}\n\n"
        f"Return a JSON array of 3-5 real or realistic upcoming AI/ML hackathons "
        f"in Europe for March 2026. For each include: name, location, dates, "
        f"url, topics, prize_pool, registration_status. Be realistic and helpful."
    )

    start = time.time()
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start

    return response.content[0].text, response.usage, elapsed


def _print_result_preview(result_text: str, usage: anthropic.types.Usage, elapsed: float) -> None:
    print(f"  OK Claude Haiku responded ({elapsed:.1f}s)")
    print(f"     Input tokens:  {usage.input_tokens}")
    print(f"     Output tokens: {usage.output_tokens}")
    print()
    for line in result_text.split("\n")[:RESULT_PREVIEW_LINES]:
        print(f"     {line[:RESULT_PREVIEW_WIDTH]}")
    print("     ...")
    print()


def _delivery_proof_hash(result_data: dict) -> str:
    """SHA-256 hash of canonical JSON — matches SOTAAgent._hash_result."""
    raw = json.dumps(
        result_data, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _print_payment_breakdown() -> None:
    _section("On-chain payment breakdown")
    bid = JOB["bid_amount_usdc"]
    fee = bid * PLATFORM_FEE_BPS / BPS_DENOMINATOR
    payout = bid - fee
    remaining = JOB["budget_usdc"] - bid

    print(f"""
    User budget:           {JOB['budget_usdc']:.6f} USDC
    Agent bid (won):       {bid:.6f} USDC
    User kept (unspent):   {remaining:.6f} USDC

    Escrow held:           {bid:.6f} USDC
    Platform fee (2%):     {fee:.6f} USDC
    Agent payout:          {payout:.6f} USDC
    """)


def _print_delivery_proof(result_text: str) -> None:
    _section("Delivery proof")
    result_data = {"success": True, "result": result_text, "job_id": JOB["id"]}
    proof_hash = _delivery_proof_hash(result_data)

    print(f"  Result size:   {len(result_text)} bytes")
    print(f"  Proof hash:    {proof_hash}")
    print()


def _print_summary(usage: anthropic.types.Usage) -> None:
    bid = JOB["bid_amount_usdc"]
    fee = bid * PLATFORM_FEE_BPS / BPS_DENOMINATOR
    payout = bid - fee

    _section("DONE")
    print(f"""
    Paid.ai dashboard (LLM costs):
      - Claude Haiku call auto-captured via paid_tracing
      - {usage.input_tokens} input + {usage.output_tokens} output tokens
      - Cost attributed to customer={JOB['poster'][:16]}... product={AGENT_NAME}

    On-chain contracts (revenue):
      - Escrow holds {bid} USDC until delivery confirmed
      - Agent receives {payout} USDC payout
      - Platform collects {fee} USDC fee (2%)
      - Run: cd contracts && npx hardhat run scripts/simulate-1usdc-job.ts
    """)


# ----------------------------------------------------------------
#  Main
# ----------------------------------------------------------------
async def main() -> None:
    print("""
============================================================
  SOTA -- Live 1 USDC Job Simulation
  Paid.ai = LLM costs  |  On-chain = Revenue
============================================================
""")

    api_key = os.getenv("SOTA_PAID_API_KEY", "").strip()
    if not api_key:
        print("  ERROR: SOTA_PAID_API_KEY not set in .env")
        return

    _section("Initialize Paid.ai cost tracking")
    initialize_cost_tracking()
    print(f"  OK Tracing initialized (key: {api_key[:12]}...)")

    _print_job_details()

    _section("Execute job (paid_tracing + Claude Haiku)")

    async with paid_tracing(
        external_customer_id=JOB["poster"],
        external_product_id=AGENT_NAME,
    ):
        print(f"  OK paid_tracing context opened")
        print(f"     customer_id = {JOB['poster']}")
        print(f"     product_id  = {AGENT_NAME}")
        print()
        print("  Calling Claude Haiku...")

        result_text, usage, elapsed = await _execute_llm_call()
        _print_result_preview(result_text, usage, elapsed)

        send_outcome(
            job_id=JOB["id"],
            agent_name=AGENT_NAME,
            revenue_usdc=JOB["bid_amount_usdc"],
            success=True,
        )
        print("  OK Tracing signal sent (cost-linked)")

    _print_payment_breakdown()
    _print_delivery_proof(result_text)
    _print_summary(usage)


if __name__ == "__main__":
    asyncio.run(main())
