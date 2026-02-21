"""Unit tests for sota_sdk.chain.contracts and chain.registry."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestABILoading:
    @patch("sota_sdk.chain.contracts._artifacts_dir")
    def test_missing_abi_raises(self, mock_dir, tmp_path):
        mock_dir.return_value = tmp_path / "nonexistent"
        from sota_sdk.chain.contracts import _load_abi
        with pytest.raises(FileNotFoundError, match="ABI not found"):
            _load_abi("OrderBook")


class TestMissingContractAddress:
    def test_order_book_missing(self):
        from sota_sdk.config import ContractAddresses
        with patch("sota_sdk.chain.contracts.get_contract_addresses", return_value=ContractAddresses()):
            from sota_sdk.chain.contracts import _order_book
            with pytest.raises(ValueError, match="not configured"):
                _order_book(MagicMock())

    def test_escrow_missing(self):
        from sota_sdk.config import ContractAddresses
        with patch("sota_sdk.chain.contracts.get_contract_addresses", return_value=ContractAddresses()):
            from sota_sdk.chain.contracts import _escrow
            with pytest.raises(ValueError, match="not configured"):
                _escrow(MagicMock())


class TestGetJob:
    @patch("sota_sdk.chain.contracts._order_book")
    def test_parses_tuple_to_dict(self, mock_ob):
        contract = MagicMock()
        contract.functions.getJob.return_value.call.return_value = (
            1,              # id
            "0xPoster",     # poster
            "0xProvider",   # provider
            "ipfs://meta",  # metadata_uri
            5_000_000,      # budget (raw int, 6 decimals)
            1700000000,     # deadline
            2,              # status
            b"\x00" * 32,   # delivery_proof
            1699000000,     # created_at
        )
        mock_ob.return_value = contract

        from sota_sdk.chain.contracts import get_job
        result = get_job(MagicMock(), 1)
        assert result["id"] == 1
        assert result["poster"] == "0xPoster"
        assert result["provider"] == "0xProvider"
        assert result["metadata_uri"] == "ipfs://meta"
        assert result["budget_usdc"] == 5.0
        assert result["deadline"] == 1700000000
        assert result["status"] == 2
        assert result["created_at"] == 1699000000


class TestSubmitDeliveryProof:
    @patch("sota_sdk.chain.contracts._order_book")
    def test_calls_mark_completed(self, mock_ob):
        contract = MagicMock()
        mock_ob.return_value = contract
        wallet = MagicMock()
        wallet.build_and_send.return_value = "0xtxhash"
        wallet.wait_for_receipt.return_value = {"status": 1}

        from sota_sdk.chain.contracts import submit_delivery_proof
        tx = submit_delivery_proof(wallet, 1, b"\xaa" * 32)
        contract.functions.markCompleted.assert_called_once_with(1, b"\xaa" * 32)
        assert tx == "0xtxhash"


class TestClaimPayment:
    @patch("sota_sdk.chain.contracts._escrow")
    def test_calls_release_to_provider(self, mock_esc):
        contract = MagicMock()
        mock_esc.return_value = contract
        wallet = MagicMock()
        wallet.build_and_send.return_value = "0xtxhash"
        wallet.wait_for_receipt.return_value = {"status": 1}

        from sota_sdk.chain.contracts import claim_payment
        tx = claim_payment(wallet, 1)
        contract.functions.releaseToProvider.assert_called_once_with(1)
        assert tx == "0xtxhash"


class TestChainRegistry:
    @patch("sota_sdk.chain.registry._agent_registry")
    def test_register_agent_calls_contract(self, mock_reg):
        contract = MagicMock()
        mock_reg.return_value = contract
        wallet = MagicMock()
        wallet.address = "0xAgent"
        wallet.build_and_send.return_value = "0xtxhash"
        wallet.wait_for_receipt.return_value = {"status": 1}

        from sota_sdk.chain.registry import register_agent
        tx = register_agent(wallet, "my-agent", "ipfs://meta", ["nlp"])
        contract.functions.registerAgent.assert_called_once_with(
            "0xAgent", "my-agent", "ipfs://meta", ["nlp"]
        )
        assert tx == "0xtxhash"

    @patch("sota_sdk.chain.registry._agent_registry")
    def test_is_agent_active_returns_bool(self, mock_reg):
        contract = MagicMock()
        contract.functions.isAgentActive.return_value.call.return_value = True
        mock_reg.return_value = contract

        from sota_sdk.chain.registry import is_agent_active
        result = is_agent_active(MagicMock(), "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
        assert result is True
