"""
Simplified AgentWallet for the SOTA SDK.

Adapted from agents/src/shared/wallet.py -- keeps only what the SDK needs:
balance checks, message signing, and transaction sending.

Migrated from EVM/Web3 to Solana/solders.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from decimal import Decimal
from typing import Optional, Union

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.system_program import transfer, TransferParams
from solders.instruction import Instruction, AccountMeta
from spl.token.instructions import (
    get_associated_token_address,
    transfer_checked,
    TransferCheckedParams,
)

from ..config import (
    get_cluster,
    get_keypair,
    USDC_MINT,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
)

logger = logging.getLogger(__name__)


def _parse_keypair(key: Union[str, Keypair]) -> Keypair:
    """Parse a Keypair from various formats (base58, JSON byte array, base64, or Keypair)."""
    if isinstance(key, Keypair):
        return key

    raw = key.strip()

    # JSON array: [12, 34, ...]
    if raw.startswith("["):
        import json
        byte_list = json.loads(raw)
        return Keypair.from_bytes(bytes(byte_list))

    # base58
    try:
        return Keypair.from_base58_string(raw)
    except Exception:
        pass

    # base64
    import base64
    try:
        decoded = base64.b64decode(raw)
        return Keypair.from_bytes(decoded)
    except Exception:
        pass

    raise ValueError("Cannot parse keypair. Provide base58, base64, or JSON byte array.")


class AgentWallet:
    """
    Lightweight wallet wrapper for an SDK agent on Solana.

    Provides:
    - Address / balance queries (SOL + USDC)
    - Message signing (ed25519)
    - Transaction building and sending
    """

    def __init__(self, private_key: Union[str, Keypair]):
        self.cluster = get_cluster()
        self.client = Client(self.cluster.rpc_url)

        try:
            self.keypair: Keypair = _parse_keypair(private_key)
        except Exception:
            raise ValueError("Failed to initialise wallet (key redacted)") from None

    @property
    def address(self) -> str:
        """Base58 public key string."""
        return str(self.keypair.pubkey())

    @property
    def pubkey(self) -> Pubkey:
        """Solders Pubkey."""
        return self.keypair.pubkey()

    # -- Balances --------------------------------------------------------------

    def get_native_balance(self) -> Decimal:
        """SOL balance in human units."""
        resp = self.client.get_balance(self.pubkey, commitment=Confirmed)
        lamports = resp.value
        return Decimal(lamports) / Decimal(10**9)

    def get_usdc_balance(self) -> Decimal:
        """USDC balance in human units (6 decimals)."""
        try:
            ata = get_associated_token_address(self.pubkey, USDC_MINT)
            resp = self.client.get_token_account_balance(ata, commitment=Confirmed)
            if resp.value:
                return Decimal(resp.value.amount) / Decimal(10**6)
        except Exception:
            pass
        return Decimal(0)

    def get_balance(self) -> dict:
        """Get both SOL and USDC balances."""
        return {
            "sol": float(self.get_native_balance()),
            "usdc": float(self.get_usdc_balance()),
            "address": self.address,
        }

    # -- Signing ---------------------------------------------------------------

    def sign_message(self, message: str) -> str:
        """Sign an arbitrary text message using ed25519. Returns hex signature."""
        msg_bytes = message.encode("utf-8")
        sig = self.keypair.sign_message(msg_bytes)
        return bytes(sig).hex()

    def hash_data(self, data: bytes) -> bytes:
        """SHA-256 hash of data, truncated to 32 bytes (for delivery proofs)."""
        return hashlib.sha256(data).digest()

    # -- Transaction Helpers ---------------------------------------------------

    def build_and_send(
        self,
        ix: Instruction,
        extra_signers: list[Keypair] | None = None,
        retries: int = 3,
    ) -> str:
        """Build, sign, and send a transaction with a single instruction. Returns tx signature."""
        import time

        signers = [self.keypair]
        if extra_signers:
            signers.extend(extra_signers)

        last_err = None
        for attempt in range(retries):
            try:
                recent = self.client.get_latest_blockhash(Confirmed)
                blockhash = recent.value.blockhash

                tx = Transaction()
                tx.recent_blockhash = blockhash
                tx.fee_payer = self.pubkey
                tx.add(ix)

                result = self.client.send_transaction(
                    tx,
                    *signers,
                    opts=TxOpts(
                        skip_preflight=False,
                        preflight_commitment=Confirmed,
                    ),
                )
                sig = str(result.value)
                logger.info("Transaction sent: %s", sig)
                return sig

            except Exception as e:
                last_err = e
                err_msg = str(e).lower()
                if ("blockhash" in err_msg or "expired" in err_msg) and attempt < retries - 1:
                    time.sleep(1)
                    continue
                raise

        raise last_err  # type: ignore[misc]

    def confirm_transaction(self, sig: str, timeout: int = 60) -> dict:
        """Wait for transaction confirmation."""
        resp = self.client.confirm_transaction(sig, commitment=Confirmed)
        return resp

    def transfer_sol(self, to: str, lamports: int) -> str:
        """Transfer SOL to another address. Returns tx signature."""
        to_pubkey = Pubkey.from_string(to)
        ix = transfer(TransferParams(
            from_pubkey=self.pubkey,
            to_pubkey=to_pubkey,
            lamports=lamports,
        ))
        return self.build_and_send(ix)

    def transfer_usdc(self, to: str, amount: float) -> str:
        """
        Transfer USDC to another address via SPL token transfer_checked.

        Args:
            to: Recipient wallet address (base58). ATA is derived automatically.
            amount: USDC amount in human units (e.g. 1.5 = 1,500,000 raw).

        Returns: tx signature
        """
        to_pubkey = Pubkey.from_string(to)
        source_ata = get_associated_token_address(self.pubkey, USDC_MINT)
        dest_ata = get_associated_token_address(to_pubkey, USDC_MINT)
        raw_amount = int(amount * 1e6)

        ix = transfer_checked(TransferCheckedParams(
            program_id=TOKEN_PROGRAM_ID,
            source=source_ata,
            mint=USDC_MINT,
            dest=dest_ata,
            owner=self.pubkey,
            amount=raw_amount,
            decimals=6,
        ))
        return self.build_and_send(ix)

    def __repr__(self) -> str:
        return f"AgentWallet({self.address[:12]}...)"


def create_wallet_from_env() -> Optional[AgentWallet]:
    """
    Create an AgentWallet from the SOTA_AGENT_PRIVATE_KEY environment variable.
    Returns None if the key is not set.
    """
    kp = get_keypair()
    if kp is None:
        return None
    return AgentWallet(kp)
