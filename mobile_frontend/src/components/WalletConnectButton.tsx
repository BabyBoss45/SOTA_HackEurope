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
  QrCode,
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

  // Auto-connect the hardcoded demo wallet on mount
  useEffect(() => {
    if (!mounted || connected || connecting || connectingName) return;
    const demoWallet = wallets.find(
      (w) => w.adapter.name === "Demo Wallet"
    );
    if (demoWallet) {
      handleConnect(demoWallet.adapter.name as WalletName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, connected]);

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
      if (/user rejected|user denied|window closed/i.test(msg)) {
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setConnectingName(null);
    }
  };

  if (connected || !mounted) return null;

  // Show all wallets — installed ones first, then others
  const installed = wallets.filter(
    (w) => w.readyState === "Installed" || w.readyState === "Loadable"
  );
  const notInstalled = wallets.filter(
    (w) => w.readyState === "NotDetected"
  );
  const allWallets = [...installed, ...notInstalled];

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

      {allWallets.map((wallet) => {
        const isLoading =
          connectingName === wallet.adapter.name || connecting;
        const isDemo = wallet.adapter.name === "Demo Wallet";
        const isPrimary = isDemo || wallet.adapter.name === "Phantom";
        const isWC = wallet.adapter.name === "WalletConnect";
        const isInstalled = wallet.readyState === "Installed" || wallet.readyState === "Loadable";

        // WalletConnect is always "connectable" — it opens its own QR modal
        const canConnect = isInstalled || isWC;

        return (
          <button
            key={wallet.adapter.name}
            type="button"
            className={`wallet-connect-btn${
              isPrimary ? " wallet-connect-btn--primary" : ""
            }${isWC ? " wallet-connect-btn--qr" : ""}`}
            onClick={() => {
              if (canConnect) {
                handleConnect(wallet.adapter.name as WalletName);
              } else {
                // Open wallet install page
                const url = wallet.adapter.url;
                if (url) window.open(url, "_blank");
              }
            }}
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
                {isLoading
                  ? isWC
                    ? "Opening QR..."
                    : "Connecting..."
                  : wallet.adapter.name}
              </span>
              <span className="wallet-connect-btn-sub">
                {isDemo
                  ? "Hackathon demo wallet (devnet)"
                  : isWC
                    ? "Scan with Phantom or any Solana wallet"
                    : isInstalled
                      ? "Detected"
                      : "Not installed — click to get"}
              </span>
            </span>
            {isWC ? (
              <span className="wallet-connect-btn-icon" style={{ marginLeft: "auto" }}>
                <QrCode size={14} />
              </span>
            ) : !isInstalled ? (
              <span className="wallet-connect-btn-icon" style={{ marginLeft: "auto" }}>
                <Download size={14} />
              </span>
            ) : null}
          </button>
        );
      })}

      {error && <p className="wallet-connect-error">{error}</p>}
    </div>
  );
};
