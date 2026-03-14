"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CreditCard, Wallet, ArrowLeft, Loader2, Check } from "lucide-react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletName } from "@solana/wallet-adapter-base";
import { usePaymentMethod } from "@/src/context/PaymentMethodContext";
import UsdcBalance from "./UsdcBalance";

// ── Helpers ──────────────────────────────────────────────────

const isMobileDevice = () => {
  if (typeof navigator === "undefined") return false;
  return /Mobi|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent
  );
};

// ── Glass card style constants ──────────────────────────────

const glassStyle: React.CSSProperties = {
  background: "rgba(255, 255, 255, 0.04)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  borderRadius: 16,
  backdropFilter: "blur(12px)",
};

// ── Component ───────────────────────────────────────────────

export default function PaymentGateScreen() {
  const { setPaymentMethod } = usePaymentMethod();
  const { select, connect, connected, connecting, publicKey, disconnect } =
    useWallet();
  const [showWalletFlow, setShowWalletFlow] = useState(false);
  const [connectingWallet, setConnectingWallet] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const mobile = mounted && isMobileDevice();

  const handleWalletConnect = async (walletName: string) => {
    setError(null);
    setConnectingWallet(walletName);
    try {
      select(walletName as WalletName);
      await connect();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Connection failed";
      if (/user rejected|user denied|window closed/i.test(msg)) {
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setConnectingWallet(null);
    }
  };

  const handleBack = async () => {
    if (connected) {
      await disconnect();
    }
    setShowWalletFlow(false);
    setError(null);
  };

  // ── Wallet connection sub-flow ────────────────────────────

  if (showWalletFlow) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100%",
          padding: "24px 16px",
          position: "relative",
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          style={{
            width: "100%",
            maxWidth: 400,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {/* Back button */}
          <motion.button
            onClick={handleBack}
            whileTap={{ scale: 0.95 }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "none",
              border: "none",
              color: "rgba(255, 255, 255, 0.6)",
              cursor: "pointer",
              padding: "8px 0",
              fontSize: 14,
            }}
          >
            <ArrowLeft size={16} />
            Back to payment options
          </motion.button>

          <h2
            style={{
              color: "#fff",
              fontSize: 22,
              fontWeight: 700,
              textAlign: "center",
              margin: 0,
            }}
          >
            Connect Your Wallet
          </h2>
          <p
            style={{
              color: "rgba(255, 255, 255, 0.5)",
              fontSize: 14,
              textAlign: "center",
              margin: "0 0 8px 0",
            }}
          >
            {connected
              ? "Wallet connected! Review your balance below."
              : "Choose a wallet to pay with USDC on Solana Devnet"}
          </p>

          <AnimatePresence mode="wait">
            {connected && publicKey ? (
              <motion.div
                key="connected"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.3 }}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                  alignItems: "center",
                }}
              >
                {/* Connected indicator */}
                <div
                  style={{
                    ...glassStyle,
                    padding: "16px 20px",
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    width: "100%",
                    background: "rgba(34, 197, 94, 0.08)",
                    border: "1px solid rgba(34, 197, 94, 0.2)",
                  }}
                >
                  <Check size={18} style={{ color: "#22c55e" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        color: "#22c55e",
                        fontSize: 13,
                        fontWeight: 600,
                      }}
                    >
                      Wallet Connected
                    </div>
                    <div
                      style={{
                        color: "rgba(255, 255, 255, 0.5)",
                        fontSize: 12,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {publicKey.toBase58()}
                    </div>
                  </div>
                </div>

                {/* USDC Balance */}
                <UsdcBalance publicKey={publicKey} />

                {/* Continue button */}
                <motion.button
                  onClick={() => setPaymentMethod("usdc")}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  style={{
                    width: "100%",
                    padding: "16px 24px",
                    borderRadius: 16,
                    background:
                      "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                    border: "none",
                    color: "#fff",
                    fontSize: 16,
                    fontWeight: 600,
                    cursor: "pointer",
                    marginTop: 8,
                  }}
                >
                  Continue to Chat
                </motion.button>
              </motion.div>
            ) : (
              <motion.div
                key="options"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{ display: "flex", flexDirection: "column", gap: 12 }}
              >
                {mobile ? (
                  <>
                    <WalletOptionButton
                      label="Open Phantom"
                      sublabel="Tap to open Phantom app"
                      loading={connectingWallet === "Phantom"}
                      disabled={!!connectingWallet || connecting}
                      onClick={() => handleWalletConnect("Phantom")}
                    />
                    <WalletOptionButton
                      label="Open Solflare"
                      sublabel="Tap to open Solflare app"
                      loading={connectingWallet === "Solflare"}
                      disabled={!!connectingWallet || connecting}
                      onClick={() => handleWalletConnect("Solflare")}
                    />
                  </>
                ) : (
                  <WalletOptionButton
                    label="Connect with WalletConnect"
                    sublabel="Scan QR code with Phantom or any Solana wallet"
                    loading={connectingWallet === "WalletConnect"}
                    disabled={!!connectingWallet || connecting}
                    onClick={() => handleWalletConnect("WalletConnect")}
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                color: "#ef4444",
                fontSize: 13,
                textAlign: "center",
                margin: 0,
              }}
            >
              {error}
            </motion.p>
          )}
        </motion.div>
      </div>
    );
  }

  // ── Main payment selection ────────────────────────────────

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100%",
        padding: "24px 16px",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        style={{
          width: "100%",
          maxWidth: 400,
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 8 }}>
          <h2
            style={{
              color: "#fff",
              fontSize: 24,
              fontWeight: 700,
              margin: "0 0 8px 0",
            }}
          >
            How would you like to pay?
          </h2>
          <p
            style={{
              color: "rgba(255, 255, 255, 0.5)",
              fontSize: 14,
              margin: 0,
            }}
          >
            Choose your payment method to start chatting with Butler
          </p>
        </div>

        {/* USD option */}
        <motion.button
          onClick={() => setPaymentMethod("stripe")}
          whileHover={{ scale: 1.02, borderColor: "rgba(99, 102, 241, 0.4)" }}
          whileTap={{ scale: 0.98 }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
          style={{
            ...glassStyle,
            padding: "24px 20px",
            display: "flex",
            alignItems: "center",
            gap: 16,
            cursor: "pointer",
            textAlign: "left",
            width: "100%",
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: "rgba(99, 102, 241, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <CreditCard size={24} style={{ color: "#6366f1" }} />
          </div>
          <div>
            <div
              style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}
            >
              Pay with Card (USD)
            </div>
            <div
              style={{
                color: "rgba(255, 255, 255, 0.45)",
                fontSize: 13,
                marginTop: 2,
              }}
            >
              Visa, Mastercard, Apple Pay
            </div>
          </div>
        </motion.button>

        {/* Crypto option */}
        <motion.button
          onClick={() => setShowWalletFlow(true)}
          whileHover={{ scale: 1.02, borderColor: "rgba(99, 102, 241, 0.4)" }}
          whileTap={{ scale: 0.98 }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.4 }}
          style={{
            ...glassStyle,
            padding: "24px 20px",
            display: "flex",
            alignItems: "center",
            gap: 16,
            cursor: "pointer",
            textAlign: "left",
            width: "100%",
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: "rgba(99, 102, 241, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Wallet size={24} style={{ color: "#6366f1" }} />
          </div>
          <div>
            <div
              style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}
            >
              Pay with Wallet (USDC)
            </div>
            <div
              style={{
                color: "rgba(255, 255, 255, 0.45)",
                fontSize: 13,
                marginTop: 2,
              }}
            >
              Phantom, Solflare -- Solana Devnet
            </div>
          </div>
        </motion.button>
      </motion.div>
    </div>
  );
}

// ── Sub-component: wallet option button ─────────────────────

function WalletOptionButton({
  label,
  sublabel,
  loading,
  disabled,
  onClick,
}: {
  label: string;
  sublabel: string;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { scale: 1.02 }}
      whileTap={disabled ? {} : { scale: 0.98 }}
      style={{
        ...glassStyle,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled && !loading ? 0.5 : 1,
        width: "100%",
        textAlign: "left",
      }}
    >
      {loading ? (
        <Loader2 size={20} style={{ color: "#6366f1" }} className="spinning" />
      ) : (
        <Wallet size={20} style={{ color: "#6366f1" }} />
      )}
      <div>
        <div style={{ color: "#fff", fontSize: 15, fontWeight: 600 }}>
          {loading ? "Connecting..." : label}
        </div>
        <div
          style={{ color: "rgba(255, 255, 255, 0.45)", fontSize: 12, marginTop: 1 }}
        >
          {sublabel}
        </div>
      </div>
    </motion.button>
  );
}
