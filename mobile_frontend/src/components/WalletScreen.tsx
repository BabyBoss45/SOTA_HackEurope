"use client";

import { useState, useEffect, useCallback } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { useConnection } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL } from "@solana/web3.js";
import { motion, AnimatePresence } from "motion/react";
import {
  Copy,
  Check,
  ExternalLink,
  LogOut,
  Wallet,
  RefreshCw,
  Circle,
} from "lucide-react";
import { WalletConnectButton } from "./WalletConnectButton";
import { explorerLink } from "@/src/solanaConfig";

export default function WalletScreen() {
  const { publicKey, connected, wallet, disconnect } = useWallet();
  const { connection } = useConnection();

  const [balance, setBalance] = useState<number | null>(null);
  const [balLoading, setBalLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const address = publicKey?.toBase58() ?? null;
  const shortAddr = address
    ? `${address.slice(0, 4)}...${address.slice(-4)}`
    : null;

  const fetchBalance = useCallback(async () => {
    if (!publicKey) return;
    setBalLoading(true);
    try {
      const lamports = await connection.getBalance(publicKey);
      setBalance(lamports / LAMPORTS_PER_SOL);
    } catch (err) {
      console.error("Failed to fetch SOL balance:", err);
      setBalance(null);
    } finally {
      setBalLoading(false);
    }
  }, [publicKey, connection]);

  // Fetch balance on connect and poll every 12s
  useEffect(() => {
    if (!connected || !publicKey) {
      setBalance(null);
      return;
    }
    fetchBalance();
    const interval = setInterval(fetchBalance, 12_000);
    return () => clearInterval(interval);
  }, [connected, publicKey, fetchBalance]);

  const copyAddress = () => {
    if (!address) return;
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /* -- Not connected -- */
  if (!connected) {
    return (
      <div className="wallet-screen">
        <h2 className="screen-title">Wallet</h2>

        <motion.div
          className="wallet-connect-prompt"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="wallet-connect-hero">
            <div className="wallet-connect-icon-ring">
              <Wallet size={32} />
            </div>
            <h3 className="wallet-connect-heading">Connect Your Wallet</h3>
            <p className="wallet-connect-sub">
              Link your Solana wallet to view balances, sign transactions, and
              interact with SOTA Butler on Devnet.
            </p>
          </div>

          <WalletConnectButton />

          <p className="wallet-connect-network">
            <Circle size={8} className="wallet-network-dot" />
            Solana Devnet
          </p>
        </motion.div>
      </div>
    );
  }

  /* -- Connected -- */
  const balFormatted =
    balance !== null ? `${balance.toFixed(4)} SOL` : "--";

  const explorerUrl = address ? explorerLink(address, "address") : "#";

  return (
    <div className="wallet-screen">
      <h2 className="screen-title">Wallet</h2>

      {/* -- Connection status -- */}
      <motion.div
        className="glass-card wallet-status-card"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="wallet-status-row">
          <div className="wallet-status-dot connected" />
          <span className="wallet-status-label">
            Connected via {wallet?.adapter.name || "Wallet"}
          </span>
        </div>
        <span className="wallet-status-network">Solana Devnet</span>
      </motion.div>

      {/* -- Address card -- */}
      <motion.div
        className="glass-card wallet-address-card"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <span className="wallet-label">Address</span>
        <div className="wallet-address-row">
          <span className="wallet-address-full">{address}</span>
          <div className="wallet-address-actions">
            <button
              className="wallet-icon-btn"
              onClick={copyAddress}
              title="Copy address"
            >
              <AnimatePresence mode="wait">
                {copied ? (
                  <motion.div
                    key="check"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                  >
                    <Check size={14} className="text-green" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="copy"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                  >
                    <Copy size={14} />
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
            <a
              href={explorerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="wallet-icon-btn"
              title="View on Solana Explorer"
            >
              <ExternalLink size={14} />
            </a>
          </div>
        </div>
      </motion.div>

      {/* -- Balance card -- */}
      <motion.div
        className="glass-card wallet-balance-card"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <div className="wallet-balance-header">
          <span className="wallet-label">Native Balance</span>
          <button
            className="wallet-icon-btn"
            onClick={fetchBalance}
            title="Refresh balance"
          >
            <RefreshCw size={14} className={balLoading ? "spinning" : ""} />
          </button>
        </div>
        <div className="wallet-balance-value">
          {balLoading ? (
            <span className="wallet-balance-loading">Loading...</span>
          ) : (
            <span className="wallet-balance-amount">{balFormatted}</span>
          )}
        </div>
      </motion.div>

      {/* -- Disconnect -- */}
      <motion.button
        className="disconnect-btn"
        onClick={() => disconnect()}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        whileTap={{ scale: 0.97 }}
      >
        <LogOut size={16} />
        <span>Disconnect Wallet</span>
      </motion.button>
    </div>
  );
}
