"""Quick test: submit a job for each agent type and check bidding."""
import json
import subprocess
import sys

TESTS = [
    ("Gift Suggestion", {"task": "gift_suggestion", "budget_usd": 1.0, "deadline_hours": 1}),
    ("Restaurant Booker", {"task": "restaurant_booking", "city": "London", "date": "2026-03-01", "time": "19:00", "guests": 2, "cuisine": "Italian", "budget_usd": 1.0, "deadline_hours": 1}),
    ("Refund Claim", {"task": "refund_claim", "budget_usd": 1.0, "deadline_hours": 1}),
    ("Smart Shopper", {"task": "smart_shopping", "budget_usd": 1.0, "deadline_hours": 1}),
    ("Trip Planner", {"task": "trip_planning", "budget_usd": 1.0, "deadline_hours": 1}),
    ("Caller (Hotel)", {"task": "hotel_booking", "budget_usd": 1.0, "deadline_hours": 1}),
]

print("Agent Bidding Tests:")
print("=" * 60)

passed = 0
failed = 0

for name, data in TESTS:
    try:
        out = subprocess.run(
            ["curl", "-s", "-X", "POST", "http://localhost:3001/api/v1/marketplace/post",
             "-H", "Content-Type: application/json", "-d", json.dumps(data)],
            capture_output=True, text=True, timeout=60,
        )
        resp = json.loads(out.stdout)
        jp = resp.get("job_posted", {})
        wb = jp.get("winning_bid", {})
        winner = wb.get("bidder", "") if wb else ""
        job_id = jp.get("job_id", "?")
        reason = jp.get("reason", "")[:60]

        if winner:
            print(f"  [OK]   {name:20s} -> winner={winner}, job={job_id}")
            passed += 1
        else:
            print(f"  [FAIL] {name:20s} -> no winner, reason={reason}")
            failed += 1
    except Exception as e:
        print(f"  [ERR]  {name:20s} -> {e}")
        failed += 1

print("=" * 60)
print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)}")
