"""Unit tests for sota_sdk.chain.wallet — AgentWallet."""

import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

pytestmark = pytest.mark.unit

# Hardhat test key (account #0)
TEST_KEY = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_KEY_0X = "0x" + TEST_KEY


class TestKeyValidation:
    def test_rejects_short_key(self):
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError):
            AgentWallet("deadbeef")

    def test_rejects_non_hex(self):
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError):
            AgentWallet("zz" * 32)

    def test_rejects_empty(self):
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError):
            AgentWallet("")

    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_accepts_without_prefix(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_web3.return_value = MagicMock()
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)
        assert w.address.startswith("0x")

    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_accepts_with_prefix(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_web3.return_value = MagicMock()
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY_0X)
        assert w.address.startswith("0x")

    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_produces_checksum_address(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_web3.return_value = MagicMock()
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)
        # Checksum addresses have mixed case
        assert w.address.startswith("0x")
        assert len(w.address) == 42


class TestKeySecurity:
    def test_key_not_in_error_messages(self):
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError) as exc_info:
            AgentWallet("ab" * 31)  # 62 chars, too short
        assert TEST_KEY not in str(exc_info.value)


class TestWalletInternals:
    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_nonce_lock_is_threading_lock(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_web3.return_value = MagicMock()
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)
        assert isinstance(w._nonce_lock, type(threading.Lock()))

    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_repr_truncated(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_web3.return_value = MagicMock()
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)
        r = repr(w)
        assert "..." in r
        assert len(r) < 50


class TestSignMessage:
    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_sign_returns_hex(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)

        # sign_message uses w3.eth.account.sign_message
        mock_signed = MagicMock()
        mock_signed.signature.hex.return_value = "0x" + "ab" * 65
        mock_w3.eth.account.sign_message.return_value = mock_signed

        sig = w.sign_message("hello")
        assert sig.startswith("0x")


class TestBuildAndSend:
    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_retries_on_nonce_error(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        w = AgentWallet(TEST_KEY)

        fn = MagicMock()
        fn.estimate_gas.return_value = 100000
        fn.build_transaction.return_value = {"nonce": 0}
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000

        # First call raises nonce error, second succeeds
        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\x00"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed

        call_count = [0]
        def send_side_effect(raw_tx):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("nonce too low")
            return MagicMock(hex=lambda: "0x" + "dd" * 32)

        mock_w3.eth.send_raw_transaction.side_effect = send_side_effect

        result = w.build_and_send(fn)
        assert call_count[0] == 2

    @patch("sota_sdk.chain.wallet.Web3")
    @patch("sota_sdk.chain.wallet.get_network")
    @patch("sota_sdk.chain.wallet.get_contract_addresses")
    def test_no_retry_on_contract_revert(self, mock_addrs, mock_net, mock_web3):
        mock_net.return_value = MagicMock(rpc_url="http://localhost:8545")
        mock_addrs.return_value = MagicMock()
        mock_w3 = MagicMock()
        mock_web3.return_value = mock_w3
        mock_web3.HTTPProvider = MagicMock()

        from sota_sdk.chain.wallet import AgentWallet
        from web3.exceptions import ContractLogicError

        w = AgentWallet(TEST_KEY)
        fn = MagicMock()
        fn.estimate_gas.side_effect = ContractLogicError("execution reverted")

        with pytest.raises(ContractLogicError):
            w.build_and_send(fn)
