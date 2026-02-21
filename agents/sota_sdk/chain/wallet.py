"""
Simplified AgentWallet for the SOTA SDK.

Adapted from agents/src/shared/wallet.py -- keeps only what the SDK needs:
balance checks, message signing, and transaction sending.
"""

from __future__ import annotations

import logging
import re
import threading
from decimal import Decimal
from typing import Optional

from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount

from ..config import get_network, get_contract_addresses

logger = logging.getLogger(__name__)

_PRIVATE_KEY_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")

_ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


class AgentWallet:
    """
    Lightweight wallet wrapper for an SDK agent.

    Provides:
    - Address / balance queries
    - Message signing (for delivery proofs)
    - Raw transaction building (used by contracts module)
    """

    def __init__(self, private_key: str):
        # Validate key format before touching it
        if not _PRIVATE_KEY_RE.match(private_key):
            raise ValueError(
                "SOTA_AGENT_PRIVATE_KEY must be 64 hex characters "
                "(optionally prefixed with 0x)"
            )

        self.network = get_network()
        self.addresses = get_contract_addresses()
        self.w3 = Web3(Web3.HTTPProvider(self.network.rpc_url))

        # Wrap key construction so the raw key never leaks in tracebacks
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"
        try:
            self.account: LocalAccount = Account.from_key(private_key)
        except Exception:
            raise ValueError("Failed to initialise wallet (key redacted)") from None
        finally:
            # Don't keep the local reference around
            private_key = ""  # noqa: F841

        self.w3.eth.default_account = self.account.address

        # Serialises nonce reads + tx sends from concurrent threads
        self._nonce_lock = threading.Lock()

    @property
    def address(self) -> str:
        return self.account.address

    # -- Balances --------------------------------------------------------------

    def get_native_balance(self) -> Decimal:
        """Native token balance in ether."""
        wei = self.w3.eth.get_balance(self.address)
        return Decimal(self.w3.from_wei(wei, "ether"))

    def get_usdc_balance(self) -> Decimal:
        """USDC balance (human units)."""
        if not self.addresses.usdc:
            return Decimal(0)
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.addresses.usdc),
            abi=_ERC20_ABI,
        )
        raw = contract.functions.balanceOf(self.address).call()
        return Decimal(raw) / Decimal(10**6)

    # -- Signing ---------------------------------------------------------------

    def sign_message(self, message: str) -> str:
        """Sign an arbitrary text message. Returns hex signature."""
        from eth_account.messages import encode_defunct

        msg = encode_defunct(text=message)
        signed = self.w3.eth.account.sign_message(msg, self.account.key)
        return signed.signature.hex()

    # -- Tx helpers (used by contracts.py) -------------------------------------

    def build_and_send(self, fn, value: int = 0, gas: int | None = None) -> str:
        """Build, sign, and send a contract function call. Returns tx hash hex."""
        with self._nonce_lock:
            if gas is None:
                try:
                    gas = int(
                        fn.estimate_gas({"from": self.address, "value": value}) * 1.3
                    )
                except Exception:
                    gas = 600_000  # fallback if estimate fails

            nonce = self.w3.eth.get_transaction_count(self.address, "pending")
            tx = fn.build_transaction({
                "from": self.address,
                "nonce": nonce,
                "gas": gas,
                "gasPrice": self.w3.eth.gas_price,
                "value": value,
            })
            signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120):
        """Wait for a transaction receipt."""
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def __repr__(self) -> str:
        return f"AgentWallet({self.address[:10]}...)"
