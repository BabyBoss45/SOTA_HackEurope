"use client";

import { useAccount, useChainId } from "wagmi";

export default function StatusBar() {
  const { address, isConnected } = useAccount();
  const chainId = useChainId();

  const networkName = chainId === 84532 ? "Base Sepolia" : `Chain ${chainId}`;
  const shortAddr = address
    ? `${address.slice(0, 6)}…${address.slice(-4)}`
    : null;

  return (
    <header className="status-bar">
      <div className="status-bar-left">
        <span className="status-logo">SOTA</span>
        <span className="status-badge">{networkName}</span>
      </div>
      <div className="status-bar-right">
        {isConnected && shortAddr ? (
          <span className="status-wallet-chip">{shortAddr}</span>
        ) : (
          <span className="status-wallet-chip disconnected">No Wallet</span>
        )}
      </div>
    </header>
  );
}
