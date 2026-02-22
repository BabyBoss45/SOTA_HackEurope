"""
Direct execution test for all 7 SOTA agents.
Each agent is instantiated and given a realistic job to execute.
Results are collected and displayed in a summary table.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Setup env
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
from dotenv import load_dotenv
load_dotenv(_here / "agents" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-5s | %(message)s",
)

# Initialize Paid.ai cost tracking so LLM costs are reported
try:
    from sota_sdk.cost import initialize_cost_tracking, flush_cost_tracking
    initialize_cost_tracking()
    print("Paid.ai cost tracking initialized")
except Exception as e:
    print(f"Paid.ai init skipped: {e}")
    flush_cost_tracking = None

from agents.src.shared.base_agent import ActiveJob


# ── Mock jobs for each agent ─────────────────────────────────────

JOBS = [
    {
        "agent_name": "Hackathon",
        "factory_module": "agents.src.hackathon.agent",
        "factory_fn": "create_hackathon_agent",
        "job": ActiveJob(
            job_id=1001,
            bid_id=0,
            job_type=2,
            description="hackathon_discovery: location=London, date_range=March 2026, theme_technology_focus=AI, online_or_in_person=both",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Gift Suggestion",
        "factory_module": "agents.src.gift_suggestion.agent",
        "factory_fn": "create_gift_suggestion_agent",
        "job": ActiveJob(
            job_id=1002,
            bid_id=0,
            job_type=4,
            description="gift_suggestion: recipient_name=Sarah, occasion=birthday, budget=50 GBP, interests=reading and cooking",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Restaurant Booker",
        "factory_module": "agents.src.restaurant_booker.agent",
        "factory_fn": "create_restaurant_booker_agent",
        "job": ActiveJob(
            job_id=1003,
            bid_id=0,
            job_type=10,
            description="restaurant_booking_smart: date=2026-03-15, time=19:30, cuisine=Italian, location=Soho London, party_size=4",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Refund Claim",
        "factory_module": "agents.src.refund_claim.agent",
        "factory_fn": "create_refund_claim_agent",
        "job": ActiveJob(
            job_id=1004,
            bid_id=0,
            job_type=9,
            description="refund_claim: service_type=train, booking_reference=GWR-8842917, delay_details=75 minutes delayed due to signal failure, operator=Great Western Railway",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Smart Shopper",
        "factory_module": "agents.src.smart_shopper.agent",
        "factory_fn": "create_smart_shopper_agent",
        "job": ActiveJob(
            job_id=1005,
            bid_id=0,
            job_type=11,
            description="smart_shopping: product_query=Sony WH-1000XM5 headphones, max_budget=300, currency=GBP, urgency=medium",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Trip Planner",
        "factory_module": "agents.src.trip_planner.agent",
        "factory_fn": "create_trip_planner_agent",
        "job": ActiveJob(
            job_id=1006,
            bid_id=0,
            job_type=12,
            description="trip_planning: destination=Barcelona, trip_duration=4, group_size=2, date_range=2026-04-10 to 2026-04-14, departure_city=London, budget_per_person=800",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={},
        ),
    },
    {
        "agent_name": "Caller (Hotel)",
        "factory_module": "agents.src.caller.agent",
        "factory_fn": "create_caller_agent",
        "job": ActiveJob(
            job_id=1007,
            bid_id=0,
            job_type=0,
            description="hotel_booking: Book a hotel room in central London for 2 nights",
            budget=1_000_000,
            deadline=int(time.time()) + 3600,
            params={
                "location": "London",
                "check_in": "2026-04-01",
                "check_out": "2026-04-03",
                "guests": 2,
                "user_name": "SOTA Test Guest",
                # No phone_number -> agent will skip call, test LLM path only
            },
        ),
    },
]


async def run_agent_test(entry: dict) -> dict:
    """Instantiate one agent and execute its job. Return result summary."""
    name = entry["agent_name"]
    start = time.time()
    result = {"agent": name, "status": "?", "detail": "", "time_s": 0}

    # Try to load paid_tracing for cost attribution
    _paid_tracing = None
    _send_outcome = None
    try:
        from sota_sdk.cost import is_tracking_enabled, send_outcome as _so
        if is_tracking_enabled():
            from paid.tracing import paid_tracing as _pt
            _paid_tracing = _pt
            _send_outcome = _so
    except ImportError:
        pass

    try:
        import importlib
        mod = importlib.import_module(entry["factory_module"])
        factory = getattr(mod, entry["factory_fn"])
        agent = await factory()

        elapsed_init = time.time() - start
        print(f"\n{'='*60}")
        print(f"  EXECUTING: {name} (init took {elapsed_init:.1f}s)")
        print(f"  Job: {entry['job'].description[:80]}...")
        print(f"{'='*60}")

        agent_type = getattr(agent, "agent_type", name.lower().replace(" ", "_"))

        if _paid_tracing:
            async with _paid_tracing(
                external_customer_id=f"test-user-{entry['job'].job_id}",
                external_product_id=agent_type,
            ):
                exec_result = await agent.execute_job(entry["job"])
                # Send outcome signal
                success = exec_result.get("success", True) if isinstance(exec_result, dict) else True
                try:
                    _send_outcome(
                        job_id=str(entry["job"].job_id),
                        agent_name=agent_type,
                        revenue_usdc=0.80,
                        success=success,
                    )
                    print(f"  >> Paid.ai outcome sent for {name}")
                except Exception as e:
                    print(f"  >> Paid.ai outcome failed: {e}")
            # Flush spans immediately
            if flush_cost_tracking:
                flush_cost_tracking()
                print(f"  >> Paid.ai spans flushed for {name}")
        else:
            exec_result = await agent.execute_job(entry["job"])
        elapsed = time.time() - start
        result["time_s"] = round(elapsed, 1)

        if isinstance(exec_result, dict):
            success = exec_result.get("success", True)
            result["status"] = "PASS" if success else "FAIL"

            # Extract a meaningful detail
            if exec_result.get("hackathons"):
                count = len(exec_result["hackathons"])
                result["detail"] = f"Found {count} hackathon(s)"
            elif exec_result.get("suggestions") or exec_result.get("gifts"):
                items = exec_result.get("suggestions") or exec_result.get("gifts", [])
                result["detail"] = f"Suggested {len(items) if isinstance(items, list) else 'N/A'} gift(s)"
            elif exec_result.get("restaurants"):
                count = len(exec_result["restaurants"])
                result["detail"] = f"Found {count} restaurant(s)"
            elif exec_result.get("claim_reference") or exec_result.get("claim"):
                result["detail"] = "Claim drafted"
            elif exec_result.get("products") or exec_result.get("recommendations"):
                items = exec_result.get("products") or exec_result.get("recommendations", [])
                result["detail"] = f"Found {len(items) if isinstance(items, list) else 'N/A'} product(s)"
            elif exec_result.get("itinerary") or exec_result.get("flights"):
                result["detail"] = "Itinerary built"
            elif exec_result.get("chat_summary"):
                result["detail"] = exec_result["chat_summary"][:60]
            elif exec_result.get("result"):
                r = exec_result["result"]
                if isinstance(r, str):
                    result["detail"] = r[:80]
                elif isinstance(r, dict):
                    result["detail"] = str(list(r.keys()))[:80]
                else:
                    result["detail"] = str(r)[:80]
            elif exec_result.get("error"):
                result["detail"] = str(exec_result["error"])[:80]
            else:
                result["detail"] = str(list(exec_result.keys()))[:80]
        else:
            result["status"] = "PASS"
            result["detail"] = str(exec_result)[:80]

    except Exception as e:
        elapsed = time.time() - start
        result["time_s"] = round(elapsed, 1)
        result["status"] = "ERR"
        result["detail"] = f"{type(e).__name__}: {str(e)[:60]}"

    return result


async def main():
    print("\n" + "=" * 70)
    print("  SOTA AGENT EXECUTION TEST — Direct execute_job calls")
    print("=" * 70)

    # Pre-warm embedding model
    try:
        from agents.src.shared.embedding import embed_text
        await embed_text("warmup")
        print("Embedding model ready.\n")
    except Exception:
        pass

    results = []
    for entry in JOBS:
        r = await run_agent_test(entry)
        results.append(r)
        print(f"\n  >> {r['agent']}: {r['status']} ({r['time_s']}s) — {r['detail']}\n")

    # ── Summary Table ─────────────────────────────────────────
    print("\n" + "=" * 90)
    print(f"  {'Agent':<22} {'Status':<8} {'Time':>7}  {'Detail'}")
    print("-" * 90)
    for r in results:
        status_icon = {"PASS": "+", "FAIL": "!", "ERR": "X"}.get(r["status"], "?")
        print(f"  [{status_icon}] {r['agent']:<19} {r['status']:<8} {r['time_s']:>5.1f}s  {r['detail'][:55]}")
    print("=" * 90)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERR")
    print(f"\n  Total: {passed} PASS, {failed} FAIL, {errors} ERR out of {len(results)}")

    # Final flush to ensure all Paid.ai spans are delivered
    if flush_cost_tracking:
        print("\n  Flushing Paid.ai cost data...")
        flush_cost_tracking(timeout_ms=15000)
        print("  Paid.ai data flushed successfully")
    print()


if __name__ == "__main__":
    asyncio.run(main())
