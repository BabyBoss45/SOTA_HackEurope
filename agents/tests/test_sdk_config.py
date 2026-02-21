"""Unit tests for sota_sdk.config — settings, cluster, program addresses."""

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


class TestClusterConfig:
    def test_dataclass_fields(self):
        from sota_sdk.config import ClusterConfig
        n = ClusterConfig(rpc_url="https://api.devnet.solana.com", cluster_name="devnet",
                          ws_url="wss://api.devnet.solana.com", explorer_url="https://explorer.solana.com/?cluster=devnet")
        assert n.rpc_url == "https://api.devnet.solana.com"
        assert n.cluster_name == "devnet"
        assert n.native_currency == "SOL"

    def test_get_cluster_devnet(self, monkeypatch):
        monkeypatch.setenv("SOLANA_CLUSTER", "devnet")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.cluster_name == "devnet"

    def test_get_cluster_mainnet(self, monkeypatch):
        monkeypatch.setenv("SOLANA_CLUSTER", "mainnet-beta")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.cluster_name == "mainnet-beta"

    def test_get_cluster_localnet(self, monkeypatch):
        monkeypatch.setenv("SOLANA_CLUSTER", "localnet")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        net = cfg.get_network()
        assert net.cluster_name == "localnet"


class TestContractAddresses:
    def test_program_id_default(self):
        from sota_sdk.config import get_contract_addresses
        c = get_contract_addresses()
        # On Solana, all contracts map to the single program ID
        assert c.order_book != ""
        assert c.usdc != ""

    def test_usdc_from_env(self, monkeypatch):
        monkeypatch.setenv("USDC_MINT", "CustomMintAddress123456789012345678901234")
        import importlib
        import sota_sdk.config as cfg
        importlib.reload(cfg)
        c = cfg.get_contract_addresses()
        assert c.usdc != ""
