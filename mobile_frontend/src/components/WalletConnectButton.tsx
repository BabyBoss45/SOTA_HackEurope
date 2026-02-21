"use client";

import React, { useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletName } from "@solana/wallet-adapter-base";
import {
  Loader2,
  Download,
  ExternalLink,
  Smartphone,
  Monitor,
} from "lucide-react";

// ── Helpers ──────────────────────────────────────────────────

const isMobileDevice = () => {
  if (typeof navigator === "undefined") return false;
  return /Mobi|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent
  );
};

const walletIcon = (name: string): React.ReactNode => {
  // Wallet adapters expose their own icons, but we fall back to generic
  return null;
};

// ── Component ────────────────────────────────────────────────

export const WalletConnectButton: React.FC = () => {
  const [mounted, setMounted] = useState(false);
  const [connectingName, setConnectingName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { wallets, select, connect, connected, connecting } = useWallet();

  useEffect(() => {
    setMounted(true);
  }, []);

  const mobile = mounted && isMobileDevice();

  const handleConnect = async (walletName: WalletName) => {
    setError(null);
    setConnectingName(walletName as string);
    try {
      select(walletName);
      // Explicitly call connect() after select() to trigger the wallet
      // connection prompt immediately rather than relying solely on autoConnect.
      await connect();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Connection failed";
      if (/user rejected|user denied/i.test(msg)) {
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setConnectingName(null);
    }
  };

  if (connected || !mounted) return null;

  // Filter to installed or loadable wallets
  const available = wallets.filter(
    (w) =>
      w.readyState === "Installed" || w.readyState === "Loadable"
  );

  const notInstalled = wallets.filter(
    (w) => w.readyState === "NotDetected"
  );

  return (
    <div className="wallet-connect-options">
      {/* Device mode indicator */}
      <div className="wallet-device-hint">
        {mobile ? (
          <>
            <Smartphone size={14} />{" "}
            <span>Mobile -- tap to open wallet app</span>
          </>
        ) : (
          <>
            <Monitor size={14} />{" "}
            <span>Desktop -- select your Solana wallet</span>
          </>
        )}
      </div>

      {available.map((wallet) => {
        const isLoading =
          connectingName === wallet.adapter.name || connecting;
        const isPrimary = wallet.adapter.name === "Phantom";

        return (
          <button
            key={wallet.adapter.name}
            type="button"
            className={`wallet-connect-btn${
              isPrimary ? " wallet-connect-btn--primary" : ""
            }`}
            onClick={() =>
              handleConnect(wallet.adapter.name as WalletName)
            }
            disabled={!!connectingName || connecting}
          >
            <span className="wallet-connect-btn-icon">
              {isLoading ? (
                <Loader2 size={18} className="spinning" />
              ) : wallet.adapter.icon ? (
                <img
                  src={wallet.adapter.icon}
                  alt={wallet.adapter.name}
                  width={18}
                  height={18}
                  style={{ borderRadius: 4 }}
                />
              ) : (
                <Monitor size={18} />
              )}
            </span>
            <span className="wallet-connect-btn-text">
              <span className="wallet-connect-btn-label">
                {isLoading ? "Connecting..." : wallet.adapter.name}
              </span>
              <span className="wallet-connect-btn-sub">
                {wallet.readyState === "Installed"
                  ? "Detected"
                  : "Click to connect"}
              </span>
            </span>
          </button>
        );
      })}

      {/* Show install links for wallets not detected */}
      {!mobile && notInstalled.length > 0 && available.length === 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ fontSize: 13, opacity: 0.7, margin: 0 }}>
            No Solana wallets detected. Install one to get started:
          </p>
          <a
            href="https://phantom.app/download"
            target="_blank"
            rel="noopener noreferrer"
            className="wallet-install-link"
          >
            <Download size={16} />
            <span>Install Phantom Wallet</span>
            <ExternalLink size={12} />
          </a>
          <a
            href="https://solflare.com/download"
            target="_blank"
            rel="noopener noreferrer"
            className="wallet-install-link"
          >
            <Download size={16} />
            <span>Install Solflare Wallet</span>
            <ExternalLink size={12} />
          </a>
        </div>
      )}

      {error && <p className="wallet-connect-error">{error}</p>}
    </div>
  );
};
