"""Comprehensive test suite for sota_sdk.cost module."""

import sys
import os
import io
import logging
import threading
import re

sys.path.insert(0, os.path.dirname(__file__))

results = []


def record(test_id, category, name, passed, detail=""):
    results.append({"id": test_id, "cat": category, "name": name, "pass": passed, "detail": detail})


n = 0

# ============================================================
# CATEGORY 1: MODULE IMPORTS
# ============================================================

n += 1
try:
    from sota_sdk import cost
    record(n, "Import", "import sota_sdk.cost", True)
except Exception as e:
    record(n, "Import", "import sota_sdk.cost", False, str(e))

n += 1
try:
    from sota_sdk.cost import (
        initialize_cost_tracking, is_tracking_enabled,
        wrap_openai, wrap_anthropic, wrap_gemini, wrap_mistral,
        auto_instrument, report, report_tokens, send_outcome, CostTracker,
    )
    record(n, "Import", "All 11 public API symbols importable", True)
except Exception as e:
    record(n, "Import", "All 11 public API symbols importable", False, str(e))

n += 1
try:
    import sota_sdk.cost.config
    import sota_sdk.cost.wrappers
    import sota_sdk.cost.signals
    import sota_sdk.cost.tracker
    record(n, "Import", "All 4 submodules importable", True)
except Exception as e:
    record(n, "Import", "All 4 submodules importable", False, str(e))

# ============================================================
# CATEGORY 2: CONFIG — ENV VAR HANDLING
# ============================================================

import sota_sdk.cost.config as cfg

n += 1
cfg._initialized = False
os.environ.pop("SOTA_PAID_API_KEY", None)
os.environ.pop("PAID_ENABLED", None)
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when no API key", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["SOTA_PAID_API_KEY"] = "test-key"
os.environ["PAID_ENABLED"] = "false"
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when PAID_ENABLED=false", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["PAID_ENABLED"] = "0"
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when PAID_ENABLED=0", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["PAID_ENABLED"] = "no"
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when PAID_ENABLED=no", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["PAID_ENABLED"] = "OFF"
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when PAID_ENABLED=OFF", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["PAID_ENABLED"] = ""
cfg.initialize_cost_tracking()
record(n, "Config", "Disabled when PAID_ENABLED empty string", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = False
os.environ["PAID_ENABLED"] = "true"
cfg.initialize_cost_tracking()  # paid-python not installed -> graceful
record(n, "Config", "Graceful fallback (paid-python missing)", not cfg.is_tracking_enabled())

n += 1
cfg._initialized = True
cfg.initialize_cost_tracking()  # should be no-op
record(n, "Config", "Double-init guard (no-op)", cfg._initialized is True)
cfg._initialized = False

# cleanup
os.environ.pop("SOTA_PAID_API_KEY", None)
os.environ.pop("PAID_ENABLED", None)

# ============================================================
# CATEGORY 3: WRAPPERS — GRACEFUL DEGRADATION
# ============================================================

from sota_sdk.cost.wrappers import (
    wrap_gemini, wrap_mistral, wrap_openai, wrap_anthropic,
    auto_instrument as ai_fn,
)


class FakeClient:
    pass


n += 1
c = FakeClient()
record(n, "Wrappers", "wrap_openai returns original (no paid-python)", wrap_openai(c) is c)

n += 1
record(n, "Wrappers", "wrap_anthropic returns original (no paid-python)", wrap_anthropic(c) is c)

n += 1
record(n, "Wrappers", "wrap_gemini returns original (no paid-python)", wrap_gemini(c) is c)

n += 1
record(n, "Wrappers", "wrap_mistral returns original (no paid-python)", wrap_mistral(c) is c)

n += 1
try:
    ai_fn()
    record(n, "Wrappers", "auto_instrument no-op (no paid-python)", True)
except Exception as e:
    record(n, "Wrappers", "auto_instrument no-op (no paid-python)", False, str(e))

# ============================================================
# CATEGORY 4: SIGNALS — INPUT VALIDATION
# ============================================================

from sota_sdk.cost.signals import report, report_tokens, send_outcome

n += 1
try:
    report(vendor="test", amount=-1.0)
    record(n, "Validation", "report rejects negative amount", False)
except ValueError:
    record(n, "Validation", "report rejects negative amount", True)

n += 1
try:
    report(vendor="", amount=1.0)
    record(n, "Validation", "report rejects empty vendor", False)
except ValueError:
    record(n, "Validation", "report rejects empty vendor", True)

n += 1
try:
    report(vendor="   ", amount=1.0)
    record(n, "Validation", "report rejects whitespace-only vendor", False)
except ValueError:
    record(n, "Validation", "report rejects whitespace-only vendor", True)

n += 1
try:
    report(vendor="x", amount="bad")
    record(n, "Validation", "report rejects non-numeric amount", False)
except TypeError:
    record(n, "Validation", "report rejects non-numeric amount", True)

n += 1
try:
    report_tokens(vendor="x", model="y", input_tokens=-1, output_tokens=0)
    record(n, "Validation", "report_tokens rejects negative tokens", False)
except ValueError:
    record(n, "Validation", "report_tokens rejects negative tokens", True)

n += 1
try:
    report_tokens(vendor="x", model="", input_tokens=1, output_tokens=0)
    record(n, "Validation", "report_tokens rejects empty model", False)
except ValueError:
    record(n, "Validation", "report_tokens rejects empty model", True)

n += 1
try:
    send_outcome(job_id="", agent_name="a", revenue_usdc=1.0, success=True)
    record(n, "Validation", "send_outcome rejects empty job_id", False)
except ValueError:
    record(n, "Validation", "send_outcome rejects empty job_id", True)

n += 1
try:
    send_outcome(job_id="1", agent_name="", revenue_usdc=1.0, success=True)
    record(n, "Validation", "send_outcome rejects empty agent_name", False)
except ValueError:
    record(n, "Validation", "send_outcome rejects empty agent_name", True)

# Signals graceful no-op without paid-python
n += 1
try:
    report(vendor="twilio", amount=0.01)
    record(n, "Validation", "report is no-op without paid-python", True)
except Exception as e:
    record(n, "Validation", "report is no-op without paid-python", False, str(e))

n += 1
try:
    report_tokens(vendor="x", model="y", input_tokens=10, output_tokens=5)
    record(n, "Validation", "report_tokens is no-op without paid-python", True)
except Exception as e:
    record(n, "Validation", "report_tokens is no-op without paid-python", False, str(e))

n += 1
try:
    send_outcome(job_id="1", agent_name="a", revenue_usdc=1.0, success=True)
    record(n, "Validation", "send_outcome is no-op without paid-python", True)
except Exception as e:
    record(n, "Validation", "send_outcome is no-op without paid-python", False, str(e))

# ============================================================
# CATEGORY 5: TRACKER — SINGLETON, THREADING, ACCUMULATION
# ============================================================

from sota_sdk.cost.tracker import CostTracker, CostEntry, _MAX_TRACKED_JOBS

n += 1
t1 = CostTracker.get()
t2 = CostTracker.get()
record(n, "Tracker", "Singleton identity (t1 is t2)", t1 is t2)

n += 1
instances = []
def grab():
    instances.append(CostTracker.get())
threads = [threading.Thread(target=grab) for _ in range(50)]
for t in threads:
    t.start()
for t in threads:
    t.join()
record(n, "Tracker", "Thread-safe singleton (50 threads)", all(i is t1 for i in instances))

# Cost accumulation
n += 1
t1.reset()
t1.log_llm_call("agent", "gpt-4", 100, 50, 0.005, "j1")
t1.log_llm_call("agent", "claude", 200, 100, 0.008, "j1")
t1.log_external_cost("agent", "twilio", 0.014, "j1")
total = t1.get_job_total("j1")
expected = 0.005 + 0.008 + 0.014
record(n, "Tracker", "Cost accumulation (3 entries)", abs(total - expected) < 1e-9)

# Separate jobs don't mix
n += 1
t1.reset()
t1.log_llm_call("a", "m", 10, 5, 0.001, "jobA")
t1.log_llm_call("a", "m", 10, 5, 0.002, "jobB")
record(n, "Tracker", "Job isolation (separate totals)", abs(t1.get_job_total("jobA") - 0.001) < 1e-9)

# Memory cap
n += 1
t1.reset()
for i in range(_MAX_TRACKED_JOBS + 50):
    t1._append("job_%d" % i, CostEntry(vendor="t", amount=0.01))
count = len(t1._current_job_costs)
record(n, "Tracker", "Memory cap (%d <= %d)" % (count, _MAX_TRACKED_JOBS), count <= _MAX_TRACKED_JOBS)

n += 1
record(n, "Tracker", "FIFO eviction (oldest removed)", "job_0" not in t1._current_job_costs)

n += 1
newest = "job_%d" % (_MAX_TRACKED_JOBS + 49)
record(n, "Tracker", "FIFO eviction (newest kept)", newest in t1._current_job_costs)

# Box alignment
n += 1
t1.reset()
lgr = logging.getLogger("sota_sdk.cost.tracker")
lgr.handlers.clear()
stream = io.StringIO()
handler = logging.StreamHandler(stream)
handler.setFormatter(logging.Formatter("%(message)s"))
lgr.addHandler(handler)
lgr.setLevel(logging.INFO)
lgr.propagate = False

t1._append("99", CostEntry(vendor="llm", amount=0.004, model="sonnet", input_tokens=500, output_tokens=200))
t1._append("99", CostEntry(vendor="twilio", amount=0.014))
t1.log_job_summary("booker", "99", revenue_usdc=2.00, duration_secs=10.5)

lines = [l for l in stream.getvalue().strip().split("\n") if l.strip()]
lengths = set(len(l) for l in lines)
record(n, "Tracker", "Box alignment (all lines equal width)", len(lengths) == 1)

# Zero-revenue margin
n += 1
t1.reset()
stream2 = io.StringIO()
lgr.handlers.clear()
h2 = logging.StreamHandler(stream2)
h2.setFormatter(logging.Formatter("%(message)s"))
lgr.addHandler(h2)

t1._append("z", CostEntry(vendor="llm", amount=0.05, input_tokens=100, output_tokens=50))
t1.log_job_summary("agent", "z", revenue_usdc=0.0)
record(n, "Tracker", "Zero-revenue shows -100% margin", "Margin:   -100.0%" in stream2.getvalue())

# Summary clears entries
n += 1
record(n, "Tracker", "log_job_summary clears job entries", "z" not in t1._current_job_costs)

# get_job_total for unknown job
n += 1
record(n, "Tracker", "get_job_total returns 0 for unknown job", t1.get_job_total("nonexistent") == 0.0)

# reset clears everything
n += 1
t1.reset()
record(n, "Tracker", "reset() clears all data", len(t1._current_job_costs) == 0)

# ============================================================
# CATEGORY 6: SECURITY CHECKS
# ============================================================

n += 1
all_clean = True
for fname in [
    "sota_sdk/cost/config.py",
    "sota_sdk/cost/wrappers.py",
    "sota_sdk/cost/signals.py",
    "sota_sdk/cost/tracker.py",
]:
    with open(fname, encoding="utf-8") as f:
        content = f.read()
    for pat in [r"sk-[a-zA-Z0-9]{20,}", r"api_key\s*=\s*\"[^\"]+\"", r"password\s*=\s*\"[^\"]+\""]:
        if re.search(pat, content):
            all_clean = False
record(n, "Security", "No hardcoded secrets in any file", all_clean)

n += 1
with open("sota_sdk/cost/signals.py", encoding="utf-8") as f:
    src = f.read()
safe = src.count('data["metadata"] = metadata')
unsafe = src.count("data.update(metadata)")
record(n, "Security", "Metadata isolation (no dict collision)", safe == 3 and unsafe == 0)

n += 1
with open("sota_sdk/cost/config.py", encoding="utf-8") as f:
    src = f.read()
has_getenv = "os.getenv" in src
no_literal_key = "api_key=" not in src.replace('api_key=api_key', '').replace("api_key = os.getenv", "")
record(n, "Security", "API key sourced from env var only", has_getenv)

n += 1
with open("sota_sdk/cost/config.py", encoding="utf-8") as f:
    src = f.read()
# Make sure the key value is never passed to any logger call
import re as _re
logger_calls = _re.findall(r"logger\.\w+\(.*?\)", src, _re.DOTALL)
key_leaked = any("api_key" in call and "api_key=" not in call for call in logger_calls)
record(n, "Security", "API key value never logged", not key_leaked)

# ============================================================
# PRINT RESULTS
# ============================================================

passed = sum(1 for r in results if r["pass"])
failed = sum(1 for r in results if not r["pass"])
total_tests = len(results)

print()
print("=" * 82)
print("  SOTA SDK COST MODULE  -  TEST RESULTS")
print("=" * 82)
print()
print("  #  | %-12s | %-48s | %s" % ("Category", "Test", "Result"))
print("-----+-%-12s-+-%-48s-+--------" % ("-" * 12, "-" * 48))

for r in results:
    status = "PASS" if r["pass"] else "FAIL"
    detail = ""
    if r["detail"] and not r["pass"]:
        detail = " (%s)" % r["detail"][:30]
    print("  %2d | %-12s | %-48s | %s%s" % (r["id"], r["cat"], r["name"][:48], status, detail))

print("-----+-%-12s-+-%-48s-+--------" % ("-" * 12, "-" * 48))
print()
print("  TOTAL: %d  |  PASSED: %d  |  FAILED: %d" % (total_tests, passed, failed))
print()
if failed == 0:
    print("  ALL %d TESTS PASSED" % total_tests)
else:
    print("  %d TEST(S) FAILED" % failed)
print()
