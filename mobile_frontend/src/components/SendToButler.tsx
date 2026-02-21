"use client";

import React, { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { useConnection } from "@solana/wallet-adapter-react";
import {
  createTransferInstruction,
  getAssociatedTokenAddress,
  createAssociatedTokenAccountInstruction,
  getAccount,
} from "@solana/spl-token";
import { Transaction, PublicKey } from "@solana/web3.js";
import {
  USDC_MINT,
  BUTLER_ADDRESS,
  USDC_DECIMALS,
  explorerLink,
} from "@/src/solanaConfig";

export const SendToButler: React.FC = () => {
  const { publicKey, connected, sendTransaction } = useWallet();
  const { connection } = useConnection();

  const [amount, setAmount] = useState("1.00");
  const [localError, setLocalError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [txSignature, setTxSignature] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSend = async () => {
    setLocalError(null);
    setTxSignature(null);
    setIsSuccess(false);

    if (!connected || !publicKey) {
      setLocalError("Connect your wallet first.");
      return;
    }

    // Parse and validate amount
    let rawAmount: bigint;
    try {
      const parsed = parseFloat(amount.trim() || "0");
      if (isNaN(parsed) || parsed <= 0) {
        setLocalError("Enter an amount greater than 0.");
        return;
      }
      // Convert to smallest unit (6 decimals for USDC)
      rawAmount = BigInt(Math.round(parsed * 10 ** USDC_DECIMALS));
    } catch {
      setLocalError("Enter a valid amount.");
      return;
    }

    setIsSending(true);

    try {
      // 1. Get blockhash FIRST to avoid race condition
      const { blockhash, lastValidBlockHeight } =
        await connection.getLatestBlockhash();

      // 2. Derive sender and butler ATAs
      const senderAta = await getAssociatedTokenAddress(
        USDC_MINT,
        publicKey
      );
      const butlerAta = await getAssociatedTokenAddress(
        USDC_MINT,
        BUTLER_ADDRESS
      );

      const transaction = new Transaction();
      transaction.recentBlockhash = blockhash;
      transaction.feePayer = publicKey;

      // 3. Check if the sender ATA exists; if not, create it
      const senderAcct = await connection.getAccountInfo(senderAta);
      if (!senderAcct) {
        transaction.add(
          createAssociatedTokenAccountInstruction(
            publicKey,   // payer
            senderAta,   // associated token account
            publicKey,   // owner
            USDC_MINT    // mint
          )
        );
      }

      // 4. Check if the butler ATA exists; if not, create it
      try {
        await getAccount(connection, butlerAta);
      } catch {
        transaction.add(
          createAssociatedTokenAccountInstruction(
            publicKey,     // payer
            butlerAta,     // associated token account
            BUTLER_ADDRESS, // owner
            USDC_MINT      // mint
          )
        );
      }

      // 5. Add the transfer instruction
      transaction.add(
        createTransferInstruction(
          senderAta,    // source
          butlerAta,    // destination
          publicKey,    // owner of source
          rawAmount     // amount in smallest unit
        )
      );

      // 6. Send and confirm (blockhash already set on the transaction)
      const signature = await sendTransaction(transaction, connection);
      setTxSignature(signature);
      setIsSending(false);
      setIsConfirming(true);

      // Wait for confirmation using the same blockhash we fetched earlier
      await connection.confirmTransaction(
        {
          signature,
          blockhash,
          lastValidBlockHeight,
        },
        "confirmed"
      );

      setIsConfirming(false);
      setIsSuccess(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (/user rejected|user denied|cancelled/i.test(msg)) {
        setLocalError(null);
      } else {
        setLocalError(msg);
      }
    } finally {
      setIsSending(false);
      setIsConfirming(false);
    }
  };

  return (
    <div className="send-card">
      <div className="send-heading">
        <span className="send-title">Send USDC to Butler</span>
        <span className="send-subtitle">Solana Devnet - USDC</span>
      </div>

      <div className="send-target" title="Butler address">
        {BUTLER_ADDRESS.toBase58()}
      </div>

      <div className="send-input-row">
        <input
          type="text"
          inputMode="decimal"
          className="send-input"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.01"
        />
        <button
          type="button"
          className="btn-primary send-button"
          onClick={handleSend}
          disabled={isSending || isConfirming}
        >
          {isSending
            ? "Sending..."
            : isConfirming
            ? "Confirming..."
            : "Send"}
        </button>
      </div>

      <div className="send-status">
        {!connected && !localError && "Connect wallet to send."}
        {localError && (
          <span className="send-status-error">{localError}</span>
        )}
        {isConfirming && "Waiting for confirmation..."}
        {isSuccess && txSignature && (
          <a
            href={explorerLink(txSignature, "tx")}
            target="_blank"
            rel="noreferrer"
            className="send-link"
          >
            View on Solana Explorer
          </a>
        )}
      </div>
    </div>
  );
};
