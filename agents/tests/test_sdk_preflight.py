"""Unit tests for sota_sdk.preflight — PreflightResult, _check_agent_class, _check_environment."""

from unittest.mock import patch

import pytest

from sota_sdk.preflight import (
    PreflightResult,
    _check_agent_class,
    _check_environment,
    run_preflight,
)
from sota_sdk.agent import SOTAAgent

pytestmark = pytest.mark.unit


# ── PreflightResult ──────────────────────────────────────────────────────────

class TestPreflightResult:
    def test_ok_when_empty(self):
        r = PreflightResult()
        assert r.ok is True

    def test_not_ok_with_errors(self):
        r = PreflightResult(errors=["bad"])
        assert r.ok is False

    def test_merge_combines(self):
        r1 = PreflightResult(errors=["e1"], warnings=["w1"])
        r2 = PreflightResult(errors=["e2"], warnings=["w2"])
        r1.merge(r2)
        assert r1.errors == ["e1", "e2"]
        assert r1.warnings == ["w1", "w2"]


# ── _check_agent_class ──────────────────────────────────────────────────────

class TestCheckAgentClass:
    def test_unnamed_agent_error(self):
        agent = SOTAAgent()  # name = "unnamed-agent"
        r = _check_agent_class(agent)
        assert any("name" in e.lower() for e in r.errors)

    def test_empty_tags_error(self, make_agent_class):
        cls = make_agent_class(name="good-agent", tags=[])
        agent = cls()
        r = _check_agent_class(agent)
        assert any("tags" in e.lower() for e in r.errors)

    def test_no_execute_override_error(self):
        """SOTAAgent base class without execute override → error."""
        class BareAgent(SOTAAgent):
            name = "bare"
            tags = ["test"]
        agent = BareAgent()
        r = _check_agent_class(agent)
        assert any("execute" in e.lower() for e in r.errors)

    def test_no_description_warning(self, make_agent_class):
        cls = make_agent_class(name="nodesc", tags=["t"], description="")
        agent = cls()
        r = _check_agent_class(agent)
        assert any("description" in w.lower() for w in r.warnings)

    def test_valid_agent_passes(self, make_agent_class):
        cls = make_agent_class(name="good", tags=["t"], description="Does stuff")
        agent = cls()
        r = _check_agent_class(agent)
        assert r.ok


# ── _check_environment ──────────────────────────────────────────────────────

class TestCheckEnvironment:
    def test_invalid_url_error(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "http://bad"):
            r = _check_environment()
        assert any("ws://" in e for e in r.errors)

    def test_empty_url_error(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", ""):
            r = _check_environment()
        assert any("empty" in e.lower() for e in r.errors)

    def test_ws_non_localhost_warning(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://remote.host:3002/ws/agent"):
            r = _check_environment()
        assert any("unencrypted" in w.lower() or "wss://" in w for w in r.warnings)

    def test_malformed_key_error(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", "not-a-hex-key"):
                r = _check_environment()
        assert any("malformed" in e.lower() for e in r.errors)

    def test_no_key_warning(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                r = _check_environment()
        assert any("private_key" in w.lower() or "off-chain" in w.lower() for w in r.warnings)

    def test_no_contracts_warning(self):
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                with patch("sota_sdk.config.get_contract_addresses") as mock_ca:
                    from sota_sdk.config import ContractAddresses
                    mock_ca.return_value = ContractAddresses()
                    r = _check_environment()
        assert any("contract" in w.lower() for w in r.warnings)


# ── run_preflight ────────────────────────────────────────────────────────────

class TestRunPreflight:
    def test_aggregates_checks(self, make_agent_class):
        cls = make_agent_class(name="good", tags=["t"], description="Good agent")
        agent = cls()
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                r = run_preflight(agent, check_rpc=False)
        # Should have warnings (no key, no contracts) but no errors
        assert r.ok
        assert len(r.warnings) > 0

    def test_skips_rpc_when_false(self, make_agent_class):
        cls = make_agent_class(name="good", tags=["t"], description="Good agent")
        agent = cls()
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                with patch("sota_sdk.preflight._check_rpc_connectivity") as mock_rpc:
                    r = run_preflight(agent, check_rpc=False)
                    mock_rpc.assert_not_called()

    def test_calls_rpc_when_true(self, make_agent_class):
        cls = make_agent_class(name="good", tags=["t"], description="Good agent")
        agent = cls()
        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                with patch("sota_sdk.preflight._check_rpc_connectivity", return_value=PreflightResult()):
                    r = run_preflight(agent, check_rpc=True)
        assert r.ok
