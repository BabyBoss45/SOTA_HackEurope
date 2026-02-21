"use client";

import { useWallet } from "@solana/wallet-adapter-react";

export default function StatusBar() {
  const { publicKey, connected } = useWallet();

  const address = publicKey?.toBase58() ?? null;
  const shortAddr = address
    ? `${address.slice(0, 4)}...${address.slice(-4)}`
    : null;

  return (
    <header className="status-bar">
      <div className="status-bar-left">
        <span className="status-logo">SOTA</span>
        <span className="status-badge">Solana Devnet</span>
      </div>
      <div className="status-bar-right">
        {connected && shortAddr ? (
          <span className="status-wallet-chip">{shortAddr}</span>
        ) : (
          <span className="status-wallet-chip disconnected">No Wallet</span>
        )}
      </div>
    </header>
  );
}
