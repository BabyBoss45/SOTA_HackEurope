"use client";

import React, { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  ConnectionProvider,
  WalletProvider,
  useWallet,
} from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import {
  WalletError,
  WalletAdapterNetwork,
  WalletName,
} from "@solana/wallet-adapter-base";
import {
  PhantomWalletAdapter,
  SolflareWalletAdapter,
  CoinbaseWalletAdapter,
} from "@solana/wallet-adapter-wallets";
import { WalletConnectWalletAdapter } from "@walletconnect/solana-adapter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SOLANA_RPC_URL } from "./solanaConfig";
import { AuthProvider } from "./context/AuthContext";
import { HardcodedWalletAdapter } from "./HardcodedWalletAdapter";

// Import default wallet adapter styles
import "@solana/wallet-adapter-react-ui/styles.css";

/** Auto-selects and connects the Demo Wallet on mount */
function AutoConnectDemo() {
  const { select, connect, connected, wallet } = useWallet();
  const [tried, setTried] = useState(false);

  useEffect(() => {
    if (tried || connected) return;
    setTried(true);
    select("Demo Wallet" as WalletName);
  }, [tried, connected, select]);

  useEffect(() => {
    if (wallet?.adapter.name === "Demo Wallet" && !connected) {
      connect().catch(() => {});
    }
  }, [wallet, connected, connect]);

  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
          },
        },
      })
  );
  const wallets = useMemo(
    () => [
      new HardcodedWalletAdapter(),
      new PhantomWalletAdapter(),
      new SolflareWalletAdapter(),
      new CoinbaseWalletAdapter(),
      new WalletConnectWalletAdapter({
        network: WalletAdapterNetwork.Devnet,
        options: {
          projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID!,
          metadata: {
            name: "SOTA Butler",
            description: "AI-powered Solana agent",
            url: typeof window !== "undefined" ? window.location.origin : "",
            icons: [],
          },
        },
      }),
    ],
    []
  );

  // Silently log wallet errors instead of triggering modal popups
  const onError = useCallback((error: WalletError) => {
    console.warn("Wallet error (non-blocking):", error.message);
  }, []);

  return (
    <AuthProvider>
      <ConnectionProvider endpoint={SOLANA_RPC_URL}>
        <WalletProvider wallets={wallets} autoConnect onError={onError}>
          <WalletModalProvider>
            <AutoConnectDemo />
            <QueryClientProvider client={queryClient}>
              {children}
            </QueryClientProvider>
          </WalletModalProvider>
        </WalletProvider>
      </ConnectionProvider>
    </AuthProvider>
  );
}
