"""Unit tests for sota_sdk.cost — config, tracker, signals, wrappers."""

import threading
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ── Config ───────────────────────────────────────────────────────────────────

class TestCostConfig:
    def test_default_not_enabled(self):
        import sota_sdk.cost.config as cfg
        # Reset state
        cfg._initialized = False
        assert cfg.is_tracking_enabled() is False

    def test_no_key_noop(self, monkeypatch):
        import sota_sdk.cost.config as cfg
        cfg._initialized = False
        monkeypatch.delenv("SOTA_PAID_API_KEY", raising=False)
        cfg.initialize_cost_tracking()
        assert cfg.is_tracking_enabled() is False

    def test_disabled_env_noop(self, monkeypatch):
        import sota_sdk.cost.config as cfg
        cfg._initialized = False
        monkeypatch.setenv("SOTA_PAID_API_KEY", "test-key")
        monkeypatch.setenv("PAID_ENABLED", "false")
        cfg.initialize_cost_tracking()
        assert cfg.is_tracking_enabled() is False
        cfg._initialized = False  # cleanup

    def test_idempotent(self, monkeypatch):
        import sota_sdk.cost.config as cfg
        cfg._initialized = True
        cfg.initialize_cost_tracking()  # should be no-op
        assert cfg.is_tracking_enabled() is True
        cfg._initialized = False  # cleanup


# ── Signals ──────────────────────────────────────────────────────────────────

class TestSignals:
    def test_report_validates_vendor(self):
        from sota_sdk.cost.signals import report
        with pytest.raises(ValueError, match="vendor"):
            report(vendor="", amount=1.0)

    def test_report_rejects_negative_amount(self):
        from sota_sdk.cost.signals import report
        with pytest.raises(ValueError, match="non-negative"):
            report(vendor="test", amount=-1.0)

    def test_report_noop_without_paid(self):
        from sota_sdk.cost.signals import report
        # Should not raise even without paid-python installed
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None}):
            report(vendor="test", amount=1.0)

    def test_report_tokens_validates_inputs(self):
        from sota_sdk.cost.signals import report_tokens
        with pytest.raises(ValueError, match="vendor"):
            report_tokens(vendor="", model="m", input_tokens=0, output_tokens=0)
        with pytest.raises(ValueError, match="model"):
            report_tokens(vendor="v", model="", input_tokens=0, output_tokens=0)
        with pytest.raises(ValueError, match="non-negative"):
            report_tokens(vendor="v", model="m", input_tokens=-1, output_tokens=0)

    def test_send_outcome_validates(self):
        from sota_sdk.cost.signals import send_outcome
        with pytest.raises(ValueError, match="job_id"):
            send_outcome(job_id="", agent_name="a", revenue_usdc=1.0, success=True)
        with pytest.raises(ValueError, match="agent_name"):
            send_outcome(job_id="j1", agent_name="", revenue_usdc=1.0, success=True)


# ── Tracker ──────────────────────────────────────────────────────────────────

class TestCostTracker:
    def _fresh_tracker(self):
        from sota_sdk.cost.tracker import CostTracker
        # Create a fresh instance instead of singleton
        t = CostTracker.__new__(CostTracker)
        t.__init__()
        return t

    def test_singleton(self):
        from sota_sdk.cost.tracker import CostTracker
        CostTracker._instance = None  # reset
        t1 = CostTracker.get()
        t2 = CostTracker.get()
        assert t1 is t2
        CostTracker._instance = None  # cleanup

    def test_log_entries(self):
        t = self._fresh_tracker()
        t.log_llm_call("agent", "gpt-4", 100, 50, 0.01, "j1")
        t.log_external_cost("agent", "twilio", 0.05, "j1")
        total = t.get_job_total("j1")
        assert abs(total - 0.06) < 0.001

    def test_job_total_unknown(self):
        t = self._fresh_tracker()
        assert t.get_job_total("nonexistent") == 0.0

    def test_eviction(self):
        t = self._fresh_tracker()
        for i in range(510):
            t.log_external_cost("a", "v", 1.0, f"job_{i}")
        # Oldest jobs should be evicted
        assert t.get_job_total("job_0") == 0.0
        assert t.get_job_total("job_509") == 1.0

    def test_reset(self):
        t = self._fresh_tracker()
        t.log_external_cost("a", "v", 1.0, "j1")
        t.reset()
        assert t.get_job_total("j1") == 0.0

    def test_job_summary_log(self):
        t = self._fresh_tracker()
        t.log_llm_call("agent", "gpt-4", 100, 50, 0.01, "j1")
        # Should not raise
        t.log_job_summary("agent", "j1", revenue_usdc=10.0)


# ── Wrappers ─────────────────────────────────────────────────────────────────

class TestWrappers:
    def test_wrap_openai_returns_original_without_paid(self):
        from sota_sdk.cost.wrappers import wrap_openai
        mock_client = MagicMock()
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None, "paid.tracing.wrappers": None, "paid.tracing.wrappers.openai": None}):
            result = wrap_openai(mock_client)
        assert result is mock_client

    def test_wrap_anthropic_returns_original_without_paid(self):
        from sota_sdk.cost.wrappers import wrap_anthropic
        mock_client = MagicMock()
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None, "paid.tracing.wrappers": None, "paid.tracing.wrappers.anthropic": None}):
            result = wrap_anthropic(mock_client)
        assert result is mock_client

    def test_wrap_gemini_returns_original_without_paid(self):
        from sota_sdk.cost.wrappers import wrap_gemini
        mock_client = MagicMock()
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None, "paid.tracing.wrappers": None, "paid.tracing.wrappers.google_genai": None}):
            result = wrap_gemini(mock_client)
        assert result is mock_client

    def test_wrap_mistral_returns_original_without_paid(self):
        from sota_sdk.cost.wrappers import wrap_mistral
        mock_client = MagicMock()
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None, "paid.tracing.wrappers": None, "paid.tracing.wrappers.mistral": None}):
            result = wrap_mistral(mock_client)
        assert result is mock_client

    def test_auto_instrument_noop_without_paid(self):
        from sota_sdk.cost.wrappers import auto_instrument
        with patch.dict("sys.modules", {"paid": None, "paid.tracing": None}):
            # Should not raise
            auto_instrument()


# ── CostEntry ────────────────────────────────────────────────────────────────

class TestCostEntry:
    def test_is_llm_property(self):
        from sota_sdk.cost.tracker import CostEntry
        llm = CostEntry(vendor="llm", amount=0.01, input_tokens=100, output_tokens=50)
        assert llm.is_llm is True

        non_llm = CostEntry(vendor="twilio", amount=0.05)
        assert non_llm.is_llm is False
