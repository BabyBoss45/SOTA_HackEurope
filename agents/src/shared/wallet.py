"""
Wallet Management for SOTA Agents -- Solana Edition

Each agent has its own Solana keypair for:
- Signing transactions
- Managing SOL and USDC balances
- Interacting with the Anchor program
"""

import os
import json
import base64
import logging
from typing import Optional, Union
from dataclasses import dataclass
from decimal import Decimal

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from solders.message import Message
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed

from .chain_config import (
    get_cluster,
    get_keypair,
    USDC_MINT,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
)

logger = logging.getLogger(__name__)


@dataclass
class WalletBalance:
    """Wallet balance information"""
    native: Decimal  # SOL balance
    usdc: Decimal    # USDC balance

    def to_dict(self) -> dict:
        return {
            "native": str(self.native),
            "usdc": str(self.usdc),
        }


@dataclass
class TransactionResult:
    """Result of a transaction"""
    success: bool
    tx_hash: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tx_hash": self.tx_hash,
            "error": self.error,
        }


def _get_associated_token_address(wallet: Pubkey, mint: Pubkey) -> Pubkey:
    """Derive the associated token account address for a wallet + mint."""
    seeds = [
        bytes(wallet),
        bytes(TOKEN_PROGRAM_ID),
        bytes(mint),
    ]
    ata, _ = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)
    return ata


def _parse_keypair(raw: Union[str, Keypair]) -> Keypair:
    """
    Parse a Keypair from various formats.

    Accepts:
      - A Keypair object (returned as-is)
      - A base58-encoded secret key string
      - A JSON byte array string: [12, 34, ...]
      - A base64-encoded secret key string
    """
    if isinstance(raw, Keypair):
        return raw

    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Cannot parse Solana keypair: input is empty or not a string.")

    raw = raw.strip()

    # JSON byte array: [12, 34, ...]
    if raw.startswith("["):
        try:
            byte_list = json.loads(raw)
            return Keypair.from_bytes(bytes(byte_list))
        except (json.JSONDecodeError, ValueError, OverflowError):
            pass

    # base58
    try:
        return Keypair.from_base58_string(raw)
    except Exception:
        pass

    # base64
    try:
        decoded = base64.b64decode(raw)
        return Keypair.from_bytes(decoded)
    except Exception:
        pass

    raise ValueError("Cannot parse Solana keypair from provided private key.")


class AgentWallet:
    """
    Wallet wrapper for a Solana-based agent.

    Provides high-level methods for:
    - Balance checking (SOL + USDC)
    - SOL transfers
    - USDC transfers (SPL token)
    - Message signing (ed25519)
    """

    def __init__(self, private_key: Union[str, Keypair], agent_name: str = "agent"):
        """
        Initialize wallet with a Solana keypair or private key string.

        Args:
            private_key: Solana Keypair, base58 secret key, JSON byte array,
                         or base64-encoded secret key.
            agent_name: Name of the agent for logging.
        """
        self.agent_name = agent_name
        self.cluster = get_cluster()
        self.keypair: Keypair = _parse_keypair(private_key)
        self._client = Client(self.cluster.rpc_url)

    @property
    def address(self) -> str:
        """Get wallet address (base58)"""
        return str(self.keypair.pubkey())

    @property
    def pubkey(self) -> Pubkey:
        """Get wallet public key"""
        return self.keypair.pubkey()

    def get_balance(self) -> WalletBalance:
        """Get current wallet balances"""
        # SOL balance
        try:
            resp = self._client.get_balance(self.pubkey, commitment=Confirmed)
            lamports = resp.value
            sol = Decimal(lamports) / Decimal(10**9)
        except Exception as e:
            logger.warning("Failed to get SOL balance: %s", e)
            sol = Decimal(0)

        # USDC balance (SPL token)
        usdc = self.get_usdc_balance()

        return WalletBalance(native=sol, usdc=usdc)

    def get_native_balance(self) -> Decimal:
        """Get SOL balance"""
        try:
            resp = self._client.get_balance(self.pubkey, commitment=Confirmed)
            return Decimal(resp.value) / Decimal(10**9)
        except Exception:
            return Decimal(0)

    def get_usdc_balance(self) -> Decimal:
        """Get USDC balance"""
        try:
            ata = _get_associated_token_address(self.pubkey, USDC_MINT)
            resp = self._client.get_token_account_balance(ata, commitment=Confirmed)
            if resp.value:
                return Decimal(resp.value.ui_amount_string)
        except Exception:
            pass
        return Decimal(0)

    def transfer_native(self, to: str, amount_sol: Decimal) -> TransactionResult:
        """
        Transfer SOL to another address.

        Args:
            to: Recipient address (base58)
            amount_sol: Amount in SOL
        """
        try:
            to_pubkey = Pubkey.from_string(to)
            lamports = int(amount_sol * Decimal(10**9))

            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=self.pubkey,
                    to_pubkey=to_pubkey,
                    lamports=lamports,
                )
            )

            blockhash_resp = self._client.get_latest_blockhash(commitment=Confirmed)
            recent_blockhash = blockhash_resp.value.blockhash

            msg = Message.new_with_blockhash(
                [transfer_ix],
                self.pubkey,
                recent_blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self.keypair], recent_blockhash)

            resp = self._client.send_transaction(tx)
            sig = str(resp.value)

            # Confirm
            self._client.confirm_transaction(resp.value, commitment=Confirmed)

            return TransactionResult(success=True, tx_hash=sig)
        except Exception as e:
            return TransactionResult(success=False, error=str(e))

    def transfer_usdc(self, to: str, amount: Decimal) -> TransactionResult:
        """
        Transfer USDC tokens (SPL transfer).

        Args:
            to: Recipient address (base58)
            amount: Amount in USDC (human units, not raw)
        """
        try:
            from spl.token.instructions import transfer_checked, TransferCheckedParams

            to_pubkey = Pubkey.from_string(to)
            raw_amount = int(amount * Decimal(10**6))  # USDC has 6 decimals

            source_ata = _get_associated_token_address(self.pubkey, USDC_MINT)
            dest_ata = _get_associated_token_address(to_pubkey, USDC_MINT)

            ix = transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=source_ata,
                    mint=USDC_MINT,
                    dest=dest_ata,
                    owner=self.pubkey,
                    amount=raw_amount,
                    decimals=6,
                )
            )

            blockhash_resp = self._client.get_latest_blockhash(commitment=Confirmed)
            recent_blockhash = blockhash_resp.value.blockhash

            msg = Message.new_with_blockhash(
                [ix],
                self.pubkey,
                recent_blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self.keypair], recent_blockhash)

            resp = self._client.send_transaction(tx)
            sig = str(resp.value)
            self._client.confirm_transaction(resp.value, commitment=Confirmed)

            return TransactionResult(success=True, tx_hash=sig)
        except Exception as e:
            return TransactionResult(success=False, error=str(e))

    def sign_message(self, message: str) -> str:
        """Sign a message with the wallet's keypair. Returns hex signature."""
        msg_bytes = message.encode("utf-8")
        sig = self.keypair.sign_message(msg_bytes)
        return bytes(sig).hex()

    def get_address(self) -> str:
        """Get wallet address (alias for address property)."""
        return self.address

    def __repr__(self) -> str:
        return f"AgentWallet({self.agent_name}, {self.address[:10]}...)"


def create_wallet_from_env(agent_type: str) -> Optional[AgentWallet]:
    """
    Create a wallet from environment variable.

    Args:
        agent_type: One of 'butler', 'worker', 'caller', 'hackathon'

    Returns:
        AgentWallet or None if key not found
    """
    keypair = get_keypair(agent_type)
    if not keypair:
        return None
    return AgentWallet(keypair, agent_type)


def generate_new_wallet() -> tuple[str, str]:
    """
    Generate a new random Solana wallet.

    Returns:
        Tuple of (address_base58, secret_key_base58)
    """
    kp = Keypair()
    return str(kp.pubkey()), str(kp)
