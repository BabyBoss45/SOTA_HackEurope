"""Unit tests for sota_sdk.config — settings, network, contract addresses."""

import pytest

pytestmark = pytest.mark.unit


class TestDefaults:
    def test_default_marketplace_url(self):
        from sota_sdk.config import SOTA_MARKETPLACE_URL
        assert SOTA_MARKETPLACE_URL.startswith("ws://") or SOTA_MARKETPLACE_URL.startswith("wss://")

    def test_ws_heartbeat_type(self):
        from sota_sdk.config import WS_HEARTBEAT_INTERVAL
        assert isinstance(WS_HEARTBEAT_INTERVAL, int)
        assert WS_HEARTBEAT_INTERVAL > 0

    def test_ws_reconnect_bounds(self):
        from sota_sdk.config import WS_RECONNECT_MIN, WS_RECONNECT_MAX
        assert WS_RECONNECT_MIN > 0
        assert WS_RECONNECT_MAX > WS_RECONNECT_MIN


class TestNetworkConfig:
    def test_dataclass_fields(self):
        from sota_sdk.config import NetworkConfig
        n = NetworkConfig(rpc_url="http://localhost:8545", chain_id=31337, explorer_url="")
        assert n.rpc_url == "http://localhost:8545"
        assert n.chain_id == 31337
        assert n.native_currency == "ETH"

    def test_get_network_base_sepolia(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "84532")
        # Re-import to pick up env
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.chain_id == 84532

    def test_get_network_base_mainnet(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "8453")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.chain_id == 8453

    def test_get_network_hardhat(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "31337")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.chain_id == 31337


class TestContractAddresses:
    def test_dataclass_defaults(self):
        from sota_sdk.config import ContractAddresses
        c = ContractAddresses()
        assert c.order_book == ""
        assert c.escrow == ""
        assert c.agent_registry == ""
        assert c.usdc == ""
        assert c.reputation_token == ""

    def test_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("ORDERBOOK_ADDRESS", "0x1111")
        monkeypatch.setenv("ESCROW_ADDRESS", "0x2222")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        c = cfg.get_contract_addresses()
        assert c.order_book == "0x1111"
        assert c.escrow == "0x2222"

    def test_empty_fallback(self, monkeypatch):
        monkeypatch.delenv("ORDERBOOK_ADDRESS", raising=False)
        monkeypatch.delenv("ESCROW_ADDRESS", raising=False)
        monkeypatch.delenv("AGENT_REGISTRY_ADDRESS", raising=False)
        monkeypatch.delenv("USDC_ADDRESS", raising=False)
        monkeypatch.delenv("REPUTATION_TOKEN_ADDRESS", raising=False)
        monkeypatch.setenv("SOTA_CONTRACTS_DIR", "/nonexistent/path")
        from sota_sdk.config import get_contract_addresses
        c = get_contract_addresses()
        assert c.order_book == ""
