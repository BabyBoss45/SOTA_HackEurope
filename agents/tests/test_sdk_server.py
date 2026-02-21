"""Unit tests for sota_sdk.server — create_app, health, status endpoints."""

from unittest.mock import MagicMock, PropertyMock

import pytest
from fastapi.testclient import TestClient

from sota_sdk.server import create_app, _mask_address

pytestmark = pytest.mark.unit


def _mock_agent(**kwargs):
    """Create a mock SOTAAgent with sensible defaults."""
    agent = MagicMock()
    agent.name = kwargs.get("name", "test-agent")
    agent.description = kwargs.get("description", "A test agent")
    agent.version = kwargs.get("version", "1.0.0")
    agent.tags = kwargs.get("tags", ["test"])
    agent._active_jobs = kwargs.get("active_jobs", {})
    agent._wallet = kwargs.get("wallet", None)
    agent._ws_client = kwargs.get("ws_client", None)
    return agent


class TestHealth:
    def test_health_200(self):
        agent = _mock_agent()
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStatus:
    def test_all_fields_present(self):
        agent = _mock_agent()
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        data = resp.json()
        assert data["name"] == "test-agent"
        assert data["description"] == "A test agent"
        assert data["version"] == "1.0.0"
        assert data["tags"] == ["test"]
        assert "wallet_address" in data
        assert "active_jobs" in data
        assert "connected" in data

    def test_wallet_masked(self):
        wallet = MagicMock()
        wallet.address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        agent = _mock_agent(wallet=wallet)
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        addr = resp.json()["wallet_address"]
        assert addr.startswith("0xf39F")
        assert addr.endswith("2266")
        assert "..." in addr

    def test_wallet_none(self):
        agent = _mock_agent(wallet=None)
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        assert resp.json()["wallet_address"] is None

    def test_active_jobs_count(self):
        agent = _mock_agent(active_jobs={"j1": MagicMock(), "j2": MagicMock()})
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        assert resp.json()["active_jobs"] == 2

    def test_connected_from_ws_client(self):
        ws_client = MagicMock()
        type(ws_client).connected = PropertyMock(return_value=True)
        agent = _mock_agent(ws_client=ws_client)
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        assert resp.json()["connected"] is True

    def test_disconnected_without_ws_client(self):
        agent = _mock_agent(ws_client=None)
        app = create_app(agent)
        client = TestClient(app)
        resp = client.get("/status")
        assert resp.json()["connected"] is False


class TestMaskAddress:
    def test_none_returns_none(self):
        assert _mask_address(None) is None

    def test_short_unchanged(self):
        assert _mask_address("0x1234") == "0x1234"

    def test_full_address_masked(self):
        addr = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        masked = _mask_address(addr)
        assert masked == "0xf39F...2266"

    def test_empty_returns_empty(self):
        assert _mask_address("") == ""
