"use client";

import { useState, useCallback } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { useConnection } from "@solana/wallet-adapter-react";
import {
  createTransferInstruction,
  getAssociatedTokenAddress,
  createAssociatedTokenAccountInstruction,
  getAccount,
} from "@solana/spl-token";
import { Transaction } from "@solana/web3.js";
import {
  USDC_MINT,
  BUTLER_ADDRESS,
  USDC_DECIMALS,
} from "@/src/solanaConfig";

interface UsdcPaymentProps {
  jobId: number;
  amount: number;
  agentAddress: string;
  boardJobId?: string;
  userId?: number;
  onSuccess: () => void;
  onError: (error: string) => void;
}

type PaymentStatus = "idle" | "processing" | "confirming" | "success" | "error";

export default function UsdcPayment({
  amount,
  onSuccess,
  onError,
}: UsdcPaymentProps) {
  const { publicKey, connected, sendTransaction } = useWallet();
  const { connection } = useConnection();
  const [status, setStatus] = useState<PaymentStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handlePay = useCallback(async () => {
    setErrorMsg(null);

    if (!connected || !publicKey) {
      setErrorMsg("Wallet not connected");
      setStatus("error");
      return;
    }

    if (!BUTLER_ADDRESS) {
      setErrorMsg("Payment destination not configured");
      setStatus("error");
      return;
    }

    setStatus("processing");

    try {
      const rawAmount = BigInt(Math.round(amount * 10 ** USDC_DECIMALS));

      // 1. Get blockhash
      const { blockhash, lastValidBlockHeight } =
        await connection.getLatestBlockhash();

      // 2. Derive ATAs
      const senderAta = await getAssociatedTokenAddress(USDC_MINT, publicKey);
      const destinationAta = await getAssociatedTokenAddress(
        USDC_MINT,
        BUTLER_ADDRESS
      );

      const transaction = new Transaction();
      transaction.recentBlockhash = blockhash;
      transaction.feePayer = publicKey;

      // 3. Check if sender ATA exists; create if needed
      const senderAcct = await connection.getAccountInfo(senderAta);
      if (!senderAcct) {
        transaction.add(
          createAssociatedTokenAccountInstruction(
            publicKey,
            senderAta,
            publicKey,
            USDC_MINT
          )
        );
      }

      // 4. Check if destination ATA exists; create if needed
      try {
        await getAccount(connection, destinationAta);
      } catch {
        transaction.add(
          createAssociatedTokenAccountInstruction(
            publicKey,
            destinationAta,
            BUTLER_ADDRESS,
            USDC_MINT
          )
        );
      }

      // 5. Add transfer instruction
      transaction.add(
        createTransferInstruction(
          senderAta,
          destinationAta,
          publicKey,
          rawAmount
        )
      );

      // 6. Send transaction
      const signature = await sendTransaction(transaction, connection);

      setStatus("confirming");

      // 7. Confirm transaction
      await connection.confirmTransaction(
        { signature, blockhash, lastValidBlockHeight },
        "confirmed"
      );

      setStatus("success");
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);

      // If user rejected/denied/cancelled, silently reset
      if (/user rejected|user denied|cancelled/i.test(msg)) {
        setStatus("idle");
        setErrorMsg(null);
        return;
      }

      setStatus("error");
      setErrorMsg(msg);
      onError(msg);
    }
  }, [amount, connected, publicKey, connection, sendTransaction, onSuccess, onError]);

  const handleRetry = useCallback(() => {
    setStatus("idle");
    setErrorMsg(null);
  }, []);

  // Success state
  if (status === "success") {
    return (
      <div className="stripe-payment-container">
        <div className="stripe-payment-status stripe-payment-success">
          <div className="stripe-payment-icon">&#10003;</div>
          <p>Payment confirmed!</p>
          <p className="stripe-payment-sub">Escrow funded on-chain.</p>
        </div>
      </div>
    );
  }

  // Error state
  if (status === "error") {
    return (
      <div className="stripe-payment-container">
        <div className="stripe-payment-header">
          <h3>Fund Escrow</h3>
          <p className="stripe-payment-amount">{amount.toFixed(2)} USDC</p>
        </div>
        <div className="stripe-payment-status stripe-payment-error">
          <p>{errorMsg || "Payment failed"}</p>
        </div>
        <button className="stripe-pay-btn" onClick={handleRetry}>
          Retry
        </button>
      </div>
    );
  }

  // Idle / processing / confirming
  return (
    <div className="stripe-payment-container">
      <div className="stripe-payment-header">
        <h3>Fund Escrow</h3>
        <p className="stripe-payment-amount">{amount.toFixed(2)} USDC</p>
      </div>

      {status === "processing" && (
        <div className="stripe-payment-loading">
          <div className="stripe-spinner" />
          <p>Sending transaction...</p>
        </div>
      )}

      {status === "confirming" && (
        <div className="stripe-payment-loading">
          <div className="stripe-spinner" />
          <p>Confirming on-chain...</p>
        </div>
      )}

      {status === "idle" && (
        <button className="stripe-pay-btn" onClick={handlePay}>
          Pay {amount.toFixed(2)} USDC
        </button>
      )}
    </div>
  );
}
