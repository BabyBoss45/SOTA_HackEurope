"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "motion/react";
import { MessageCircle, Wallet, History, LogOut } from "lucide-react";
import { Providers } from "@/src/providers";
import { useAuth } from "@/src/context/AuthContext";
import ChatScreen from "@/src/components/ChatScreen";
import WalletScreen from "@/src/components/WalletScreen";
import AuthScreen from "@/src/components/AuthScreen";

const Waves = dynamic(
  () => import("@/components/ui/wave-background").then((mod) => mod.Waves),
  { ssr: false }
);

type View = "chat" | "wallet";

function AppContent() {
  const { user, loading, logout } = useAuth();
  const [activeView, setActiveView] = useState<View>("chat");
  const [historySidebarOpen, setHistorySidebarOpen] = useState(false);

  const handleHistoryClick = useCallback(() => {
    if (activeView !== "chat") {
      setActiveView("chat");
    }
    setHistorySidebarOpen(true);
  }, [activeView]);

  // Loading state while checking auth
  if (loading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-spinner" />
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Loading...</p>
      </div>
    );
  }

  // Not authenticated — show login/register
  if (!user) {
    return (
      <div className="app-shell">
        <AuthScreen />
      </div>
    );
  }

  // Authenticated — show main app
  return (
    <div className="app-shell">
      {/* ── Top nav bar ── */}
      <motion.nav
        className="top-nav"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <div className="top-nav-pills">
          {/* History button */}
          <motion.button
            className="top-nav-item"
            onClick={handleHistoryClick}
            whileTap={{ scale: 0.92 }}
          >
            <History size={18} className="top-nav-icon" />
            <span className="top-nav-label">History</span>
          </motion.button>

          {/* Butler & Wallet tabs */}
          {([
            { id: "chat" as View, icon: MessageCircle, label: "Butler" },
            { id: "wallet" as View, icon: Wallet, label: "Wallet" },
          ]).map((item) => {
            const isActive = activeView === item.id;
            return (
              <motion.button
                key={item.id}
                className={`top-nav-item ${isActive ? "active" : ""}`}
                onClick={() => setActiveView(item.id)}
                whileTap={{ scale: 0.92 }}
              >
                {isActive && (
                  <motion.div
                    className="top-nav-active-bg"
                    layoutId="navIndicator"
                    transition={{ type: "spring", stiffness: 400, damping: 28 }}
                  />
                )}
                <item.icon size={18} className="top-nav-icon" />
                <span className="top-nav-label">{item.label}</span>
              </motion.button>
            );
          })}

          {/* Logout button */}
          <motion.button
            className="top-nav-item"
            onClick={logout}
            whileTap={{ scale: 0.92 }}
          >
            <LogOut size={18} className="top-nav-icon" />
            <span className="top-nav-label">Logout</span>
          </motion.button>
        </div>
      </motion.nav>

      {/* ── Page content ── */}
      <AnimatePresence mode="wait">
        {activeView === "chat" && (
          <motion.div
            key="chat"
            className="app-view"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          >
            <ChatScreen
              sidebarOpen={historySidebarOpen}
              onSidebarOpenChange={setHistorySidebarOpen}
            />
          </motion.div>
        )}
        {activeView === "wallet" && (
          <motion.div
            key="wallet"
            className="app-view"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          >
            <WalletScreen />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function Home() {
  return (
    <Providers>
      {/* ── Full-page wave background ── */}
      <Waves
        className="fixed inset-0 w-full h-full"
        strokeColor="rgba(99, 102, 241, 0.12)"
        backgroundColor="#020617"
        pointerSize={0.4}
      />

      <AppContent />
    </Providers>
  );
}