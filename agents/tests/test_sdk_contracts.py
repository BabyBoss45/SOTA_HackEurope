"""Unit tests for sota_sdk.chain.contracts and chain.registry (Solana/Anchor)."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestIDLLoading:
    @patch("sota_sdk.chain.contracts._IDL_PATH")
    def test_missing_idl_raises(self, mock_path, tmp_path):
        mock_path.__truediv__ = MagicMock(return_value=tmp_path / "nonexistent.json")
        mock_path.exists = MagicMock(return_value=False)
        from sota_sdk.chain.contracts import _load_idl
        with pytest.raises(FileNotFoundError, match="IDL not found"):
            _load_idl("sota_marketplace")


class TestGetJob:
    @patch("sota_sdk.chain.contracts._get_client")
    def test_parses_account_data(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock account data for a job
        mock_account = MagicMock()
        mock_account.data = {
            "id": 1,
            "poster": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            "provider": "9wHGtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            "metadata_uri": "ipfs://meta",
            "budget_usdc": 5.0,
            "deadline": 1700000000,
            "status": 2,
            "created_at": 1699000000,
        }
        mock_client.get_account_info.return_value = MagicMock(value=mock_account)

        from sota_sdk.chain.contracts import get_job
        result = get_job(mock_client, 1)
        assert result["id"] == 1
        assert result["poster"] == "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
        assert result["budget_usdc"] == 5.0


class TestSubmitDeliveryProof:
    @patch("sota_sdk.chain.contracts._build_instruction")
    def test_calls_mark_completed(self, mock_build_ix):
        mock_ix = MagicMock()
        mock_build_ix.return_value = mock_ix
        wallet = MagicMock()
        wallet.build_and_send.return_value = "5wHGtxsignature"

        from sota_sdk.chain.contracts import submit_delivery_proof
        tx = submit_delivery_proof(wallet, 1, b"\xaa" * 32)
        assert tx == "5wHGtxsignature"


class TestClaimPayment:
    @patch("sota_sdk.chain.contracts._build_instruction")
    def test_calls_release_to_provider(self, mock_build_ix):
        mock_ix = MagicMock()
        mock_build_ix.return_value = mock_ix
        wallet = MagicMock()
        wallet.build_and_send.return_value = "5wHGtxsignature"

        from sota_sdk.chain.contracts import claim_payment
        tx = claim_payment(wallet, 1)
        assert tx == "5wHGtxsignature"


class TestChainRegistry:
    @patch("sota_sdk.chain.registry._build_register_ix")
    def test_register_agent_builds_instruction(self, mock_build_ix):
        mock_ix = MagicMock()
        mock_build_ix.return_value = mock_ix
        wallet = MagicMock()
        wallet.address = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
        wallet.build_and_send.return_value = "5wHGtxsignature"

        from sota_sdk.chain.registry import register_agent
        tx = register_agent(wallet, "my-agent", "ipfs://meta", ["nlp"])
        assert tx == "5wHGtxsignature"

    @patch("sota_sdk.chain.registry._get_agent_account")
    def test_is_agent_active_returns_bool(self, mock_get_account):
        mock_get_account.return_value = MagicMock(is_active=True)

        from sota_sdk.chain.registry import is_agent_active
        result = is_agent_active(MagicMock(), "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU")
        assert result is True
