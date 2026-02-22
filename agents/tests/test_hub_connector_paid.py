"""Tests for hub_connector Paid.ai cost tracking integration.

Verifies that _execute_hub_job wraps execution in a paid_tracing context,
sends outcome signals, and flushes spans — matching the auto_bidder path.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agents.src.shared.hub_connector import HubConnector

pytestmark = pytest.mark.unit


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_mock_agent(execute_result=None):
    """Build a mock agent with an async execute_job method."""
    agent = MagicMock()
    agent.agent_type = "hackathon"
    agent.agent_name = "Hackathon Agent"
    agent.supported_job_types = []
    agent.active_jobs = {}
    agent.max_concurrent_jobs = 5
    agent.wallet = MagicMock()
    agent.wallet.address = "11111111111111111111111111111111"

    if execute_result is None:
        execute_result = {"success": True, "result": "done"}
    agent.execute_job = AsyncMock(return_value=execute_result)
    return agent


def _make_job_data(job_id="test-job-42", budget=5.0, poster="poster-wallet-abc"):
    return {
        "id": job_id,
        "description": "Test job",
        "tags": ["hackathon_registration"],
        "budget_usdc": budget,
        "bid_amount_usdc": budget * 0.8,
        "deadline_ts": 9999999999,
        "poster": poster,
        "metadata": {},
    }


# Patch targets — hub_connector does lazy `from sota_sdk.cost import ...`
# so we patch on the sota_sdk.cost namespace (re-exports from __init__.py).
_PATCH_IS_ENABLED = "sota_sdk.cost.is_tracking_enabled"
_PATCH_SEND_OUTCOME = "sota_sdk.cost.send_outcome"
_PATCH_FLUSH = "sota_sdk.cost.flush_cost_tracking"
_PATCH_PAID_TRACING = "paid.tracing.paid_tracing"


# ── Tests ────────────────────────────────────────────────────────────────────

class TestHubConnectorPaidTracking:
    """Verify that _execute_hub_job properly integrates with Paid.ai."""

    @pytest.mark.asyncio
    async def test_execute_hub_job_opens_paid_tracing_context(self):
        """When cost tracking is enabled, execution MUST happen inside paid_tracing()."""
        agent = _make_mock_agent()
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_completed", new_callable=AsyncMock):
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME):
                        with patch(_PATCH_FLUSH):
                            await connector._execute_hub_job("job-1", _make_job_data("job-1"))

        # paid_tracing was called with correct customer/product IDs
        mock_tracing_fn.assert_called_once_with(
            external_customer_id="poster-wallet-abc",
            external_product_id="hackathon",
        )
        # Context manager was entered and exited
        mock_tracing_ctx.__aenter__.assert_awaited_once()
        mock_tracing_ctx.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_hub_job_sends_outcome_signal(self):
        """send_outcome() must be called with job_id, agent_name, revenue, and success."""
        agent = _make_mock_agent({"success": True, "result": "ok"})
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_completed", new_callable=AsyncMock):
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME) as mock_outcome:
                        with patch(_PATCH_FLUSH):
                            await connector._execute_hub_job("job-2", _make_job_data("job-2", budget=10.0))

        mock_outcome.assert_called_once()
        kw = mock_outcome.call_args[1]
        assert kw["job_id"] == "job-2"
        assert kw["agent_name"] == "hackathon"
        assert kw["success"] is True
        assert kw["revenue_usdc"] == 8.0  # bid_amount_usdc = 10.0 * 0.8

    @pytest.mark.asyncio
    async def test_execute_hub_job_flushes_spans(self):
        """flush_cost_tracking() must be called after the tracing context exits."""
        agent = _make_mock_agent()
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_completed", new_callable=AsyncMock):
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME):
                        with patch(_PATCH_FLUSH) as mock_flush:
                            await connector._execute_hub_job("job-3", _make_job_data("job-3"))

        mock_flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_hub_job_no_tracing_when_disabled(self):
        """When cost tracking is disabled, jobs still execute normally (no tracing)."""
        agent = _make_mock_agent({"success": True, "result": "no-tracking"})
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_completed", new_callable=AsyncMock) as mock_send:
            with patch(_PATCH_IS_ENABLED, return_value=False):
                await connector._execute_hub_job("job-4", _make_job_data("job-4"))

        # Job still executed and completed
        agent.execute_job.assert_awaited_once()
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_hub_job_failed_job_still_tracked(self):
        """A failed job should still send an outcome signal with success=False."""
        agent = _make_mock_agent({"success": False, "error": "something broke"})
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_failed", new_callable=AsyncMock) as mock_fail:
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME) as mock_outcome:
                        with patch(_PATCH_FLUSH):
                            await connector._execute_hub_job("job-5", _make_job_data("job-5"))

        mock_outcome.assert_called_once()
        assert mock_outcome.call_args[1]["success"] is False
        mock_fail.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_hub_job_exception_does_not_crash(self):
        """If execute_job raises, the error is reported and tracking doesn't crash."""
        agent = _make_mock_agent()
        agent.execute_job = AsyncMock(side_effect=RuntimeError("boom"))
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_failed", new_callable=AsyncMock) as mock_fail:
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME):
                        with patch(_PATCH_FLUSH):
                            # Should NOT raise
                            await connector._execute_hub_job("job-6", _make_job_data("job-6"))

        mock_fail.assert_awaited_once()
        assert "RuntimeError" in mock_fail.call_args[0][1]

    @pytest.mark.asyncio
    async def test_execute_hub_job_uses_budget_when_no_bid_amount(self):
        """If bid_amount_usdc is missing from job_data, fall back to budget."""
        agent = _make_mock_agent()
        connector = HubConnector(agent, hub_url="ws://fake")
        connector._ws = AsyncMock()

        job_data = _make_job_data("job-7", budget=12.0)
        del job_data["bid_amount_usdc"]  # simulate missing bid amount

        mock_tracing_ctx = AsyncMock()
        mock_tracing_fn = MagicMock(return_value=mock_tracing_ctx)

        with patch("agents.src.shared.hub_connector.HubConnector._send_job_completed", new_callable=AsyncMock):
            with patch(_PATCH_IS_ENABLED, return_value=True):
                with patch(_PATCH_PAID_TRACING, mock_tracing_fn):
                    with patch(_PATCH_SEND_OUTCOME) as mock_outcome:
                        with patch(_PATCH_FLUSH):
                            await connector._execute_hub_job("job-7", job_data)

        # Falls back to budget_usdc
        assert mock_outcome.call_args[1]["revenue_usdc"] == 12.0
