"""Unit tests for sota_sdk.marketplace.registration — build_register_message."""

import pytest

from sota_sdk.marketplace.registration import build_register_message

pytestmark = pytest.mark.unit


class TestBuildRegisterMessage:
    def test_structure(self):
        msg = build_register_message(name="a", tags=["t"], version="1.0.0")
        assert msg["type"] == "register"
        assert "agent" in msg
        assert msg["agent"]["name"] == "a"
        assert msg["agent"]["tags"] == ["t"]
        assert msg["agent"]["version"] == "1.0.0"

    def test_wallet_defaults_to_empty(self):
        msg = build_register_message(name="a", tags=["t"], version="1.0.0")
        assert msg["agent"]["wallet_address"] == ""

    def test_wallet_custom(self):
        msg = build_register_message(name="a", tags=["t"], version="1.0.0", wallet_address="0xABC")
        assert msg["agent"]["wallet_address"] == "0xABC"

    def test_capabilities_default_to_tags(self):
        msg = build_register_message(name="a", tags=["t1", "t2"], version="1.0.0")
        assert msg["agent"]["capabilities"] == ["t1", "t2"]

    def test_capabilities_custom(self):
        msg = build_register_message(name="a", tags=["t"], version="1.0.0", capabilities=["c1"])
        assert msg["agent"]["capabilities"] == ["c1"]

    def test_compatible_with_hub_agentinfo(self):
        """The register message payload must be parseable by the hub's AgentInfo model."""
        from marketplace.models import AgentInfo
        msg = build_register_message(name="test", tags=["t"], version="1.0.0", wallet_address="0x123")
        info = AgentInfo(**msg["agent"])
        assert info.name == "test"
        assert info.tags == ["t"]
        assert info.wallet_address == "0x123"
