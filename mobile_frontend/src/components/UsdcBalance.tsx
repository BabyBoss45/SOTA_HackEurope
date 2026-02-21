"use client";

import { useState, useEffect, useCallback } from "react";
import { useConnection } from "@solana/wallet-adapter-react";
import { getAssociatedTokenAddress } from "@solana/spl-token";
import { USDC_MINT, BUTLER_ADDRESS } from "@/src/solanaConfig";

export default function UsdcBalance() {
  const { connection } = useConnection();
  const [balance, setBalance] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchBalance = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);

      const ata = await getAssociatedTokenAddress(
        USDC_MINT,
        BUTLER_ADDRESS
      );

      const tokenAccountInfo = await connection.getTokenAccountBalance(ata);
      const uiAmount = tokenAccountInfo.value.uiAmountString ?? "0";
      setBalance(uiAmount);
    } catch (err) {
      // Token account may not exist yet (no USDC received)
      console.warn("Failed to fetch USDC balance:", err);
      setBalance("0");
      // Only flag as error if it's not a "account not found" situation
      const msg = err instanceof Error ? err.message : String(err);
      if (/could not find/i.test(msg) || /account.*not.*found/i.test(msg)) {
        setBalance("0");
      } else {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, [connection]);

  useEffect(() => {
    fetchBalance();
    const interval = setInterval(fetchBalance, 15_000);
    return () => clearInterval(interval);
  }, [fetchBalance]);

  let content: string;
  if (error) {
    content = "Unable to load balance";
  } else if (loading) {
    content = "Loading balance...";
  } else {
    content = `${balance} USDC`;
  }

  return (
    <div className="flex items-center gap-2 rounded-xl bg-slate-900/70 border border-slate-700 px-3 py-2 text-xs text-gray-100">
      <span className="font-semibold">Butler USDC</span>
      <span className="text-gray-300">{content}</span>
    </div>
  );
}
