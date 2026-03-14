"use client";

import React, { ReactNode, useCallback, useMemo, useState } from "react";
import {
  ConnectionProvider,
  WalletProvider,
} from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import {
  WalletError,
  WalletAdapterNetwork,
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
import { PaymentMethodProvider } from "./context/PaymentMethodContext";

// Import default wallet adapter styles
import "@solana/wallet-adapter-react-ui/styles.css";

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
        <WalletProvider wallets={wallets} autoConnect={false} onError={onError}>
          <WalletModalProvider>
            <PaymentMethodProvider>
              <QueryClientProvider client={queryClient}>
                {children}
              </QueryClientProvider>
            </PaymentMethodProvider>
          </WalletModalProvider>
        </WalletProvider>
      </ConnectionProvider>
    </AuthProvider>
  );
}
