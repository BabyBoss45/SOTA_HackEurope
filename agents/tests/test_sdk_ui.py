"""Unit tests for sota_sdk.ui.app — Agent Builder web UI API."""

import pytest
from fastapi.testclient import TestClient

from sota_sdk.ui.app import create_ui_app

pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    app = create_ui_app()
    return TestClient(app)


class TestGenerate:
    def test_returns_file_list(self, client):
        resp = client.post("/api/generate", json={"name": "test-agent", "tags": ["nlp"]})
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert "agent.py" in files
        assert ".env" in files
        assert "requirements.txt" in files

    def test_custom_tags_in_output(self, client):
        resp = client.post("/api/generate", json={"name": "test", "tags": ["web_scraping", "nlp"]})
        agent_code = resp.json()["files"]["agent.py"]
        assert "web_scraping" in agent_code
        assert "nlp" in agent_code


class TestDownload:
    def test_returns_zip(self, client):
        resp = client.post("/api/download", json={"name": "test-agent", "tags": ["t"]})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"


class TestCheck:
    def test_valid_config_ok(self, client):
        resp = client.post("/api/check", json={
            "name": "my-agent", "tags": ["test"],
            "marketplace_url": "ws://localhost:3002/ws/agent", "private_key": "",
        })
        data = resp.json()
        assert data["ok"] is True

    def test_missing_name_error(self, client):
        resp = client.post("/api/check", json={"name": "", "tags": ["t"]})
        assert resp.json()["ok"] is False
        assert any("name" in e.lower() for e in resp.json()["errors"])

    def test_missing_tags_error(self, client):
        resp = client.post("/api/check", json={"name": "a", "tags": []})
        assert resp.json()["ok"] is False

    def test_bad_url_error(self, client):
        resp = client.post("/api/check", json={
            "name": "a", "tags": ["t"], "marketplace_url": "http://bad",
        })
        assert resp.json()["ok"] is False

    def test_bad_key_error(self, client):
        resp = client.post("/api/check", json={
            "name": "a", "tags": ["t"], "private_key": "short",
        })
        assert resp.json()["ok"] is False

    def test_no_key_warning(self, client):
        resp = client.post("/api/check", json={"name": "a", "tags": ["t"], "private_key": ""})
        assert len(resp.json()["warnings"]) > 0


class TestTemplates:
    def test_returns_list(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        templates = resp.json()["templates"]
        assert len(templates) > 0
        assert all("id" in t for t in templates)


class TestNetworks:
    def test_returns_3_networks(self, client):
        resp = client.get("/api/networks")
        assert resp.status_code == 200
        networks = resp.json()["networks"]
        assert len(networks) == 3
        chain_ids = {n["chain_id"] for n in networks}
        assert 84532 in chain_ids
        assert 8453 in chain_ids
        assert 31337 in chain_ids
