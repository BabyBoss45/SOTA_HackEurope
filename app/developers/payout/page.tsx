"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle,
  Coins,
  ExternalLink,
  Loader2,
  Lock,
  LogIn,
  RefreshCw,
  Shield,
  TrendingUp,
  Wallet,
  XCircle,
} from "lucide-react";
import { FloatingPaths } from "@/components/ui/background-paths-wrapper";
import { useAuth } from "@/components/auth-provider";
import Link from "next/link";
import {
  createPublicClient,
  createWalletClient,
  custom,
  formatUnits,
  http,
  type Address,
} from "viem";
import {
  AGENT_REGISTRY_ABI,
  BASE_SEPOLIA_CHAIN,
  CONTRACT_ADDRESSES,
  explorerAddress,
  explorerTx,
} from "@/lib/contracts";

const baseSepolia = {
  id: BASE_SEPOLIA_CHAIN.id,
  name: BASE_SEPOLIA_CHAIN.name,
  nativeCurrency: BASE_SEPOLIA_CHAIN.nativeCurrency,
  rpcUrls: { default: { http: [BASE_SEPOLIA_CHAIN.rpcUrl] } },
  blockExplorers: {
    default: { name: "BaseScan", url: BASE_SEPOLIA_CHAIN.explorer },
  },
} as const;

const publicClient = createPublicClient({
  chain: baseSepolia,
  transport: http(BASE_SEPOLIA_CHAIN.rpcUrl),
});

function shortAddr(a: string): string {
  return `${a.slice(0, 6)}...${a.slice(-4)}`;
}

function fmtUsdc(val: bigint): string {
  const n = Number(formatUnits(val, 6));
  return n % 1 === 0 ? n.toFixed(0) : n.toFixed(2);
}

interface AgentInfo {
  address: Address;
  name: string;
  isActive: boolean;
  isOnChain: boolean;
  capabilities: string[];
}

interface TaskStats {
  total: number;
  executing: number;
  queued: number;
  completed: number;
  failed: number;
}

interface AgentMetric {
  name: string;
  totalRequests: number;
  successfulRequests: number;
  reputation: number | null;
}

export default function PayoutPage(): React.JSX.Element {
  const { user, loading: authLoading, getIdToken } = useAuth();

  const [account, setAccount] = useState<Address | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Address | null>(null);
  const [agentEarnings, setAgentEarnings] = useState<Map<Address, bigint>>(new Map());
  const [txPending, setTxPending] = useState(false);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null);
  const [agentMetrics, setAgentMetrics] = useState<AgentMetric[]>([]);

  const getWalletClient = useCallback(() => {
    if (typeof window === "undefined" || !(window as any).ethereum) return null;
    return createWalletClient({
      chain: baseSepolia,
      transport: custom((window as any).ethereum),
    });
  }, []);

  const authHeaders = useCallback(async (): Promise<HeadersInit> => {
    const token = await getIdToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getIdToken]);

  const connectWallet = async () => {
    if (typeof window === "undefined" || !(window as any).ethereum) {
      setError("MetaMask not found. Please install it.");
      return;
    }
    try {
      setConnecting(true);
      setError(null);
      const accounts = await (window as any).ethereum.request({
        method: "eth_requestAccounts",
      });
      if (accounts?.[0]) {
        setAccount(accounts[0] as Address);
        try {
          await (window as any).ethereum.request({
            method: "wallet_switchEthereumChain",
            params: [{ chainId: "0x14a34" }],
          });
        } catch (switchErr: any) {
          if (switchErr.code === 4902) {
            await (window as any).ethereum.request({
              method: "wallet_addEthereumChain",
              params: [
                {
                  chainId: "0x14a34",
                  chainName: BASE_SEPOLIA_CHAIN.name,
                  rpcUrls: [BASE_SEPOLIA_CHAIN.rpcUrl],
                  nativeCurrency: BASE_SEPOLIA_CHAIN.nativeCurrency,
                  blockExplorerUrls: [BASE_SEPOLIA_CHAIN.explorer],
                },
              ],
            });
          }
        }
      }
    } catch (err: any) {
      setError(err?.message || "Wallet connection failed");
    } finally {
      setConnecting(false);
    }
  };

  const disconnectWallet = () => {
    setAccount(null);
    setAgents([]);
    setSelectedAgent(null);
  };

  useEffect(() => {
    if (typeof window === "undefined" || !(window as any).ethereum) return;
    const handler = (accs: string[]) => {
      if (accs.length === 0) disconnectWallet();
      else setAccount(accs[0] as Address);
    };
    (window as any).ethereum.on("accountsChanged", handler);
    return () => (window as any).ethereum?.removeListener("accountsChanged", handler);
  }, []);

  const fetchAgents = useCallback(async () => {
    if (!account) return;
    try {
      setLoadingData(true);
      const headers = await authHeaders();
      const res = await fetch("/api/agents?mine=true", { headers });
      if (!res.ok) {
        console.error("Failed to fetch agents:", res.status);
        return;
      }
      const data = await res.json();
      const myAgents: AgentInfo[] = [];

      if (data.agents) {
        for (const a of data.agents) {
          if (!a.walletAddress) continue;
          let isOnChain = false;
          try {
            const agentData = await publicClient.readContract({
              address: CONTRACT_ADDRESSES.AgentRegistry,
              abi: AGENT_REGISTRY_ABI,
              functionName: "getAgent",
              args: [a.walletAddress as Address],
            }) as any;
            isOnChain = Number(agentData.status ?? agentData[5] ?? 0) > 0;
          } catch {
            try {
              const dev = await publicClient.readContract({
                address: CONTRACT_ADDRESSES.AgentRegistry,
                abi: AGENT_REGISTRY_ABI,
                functionName: "getDeveloper",
                args: [a.walletAddress as Address],
              }) as string;
              isOnChain = dev !== "0x0000000000000000000000000000000000000000";
            } catch {
              isOnChain = false;
            }
          }

          let capabilities: string[] = [];
          try {
            capabilities = a.capabilities ? JSON.parse(a.capabilities) : [];
          } catch {
            capabilities = [];
          }

          myAgents.push({
            address: a.walletAddress as Address,
            name: a.title || a.name || `Agent ${a.walletAddress.slice(0, 8)}`,
            isActive: a.status === "active",
            isOnChain,
            capabilities,
          });
        }

        setAgentMetrics(
          data.agents.map((a: any) => ({
            name: a.title || a.name || `Agent ${a.id}`,
            totalRequests: a.totalRequests ?? 0,
            successfulRequests: a.successfulRequests ?? 0,
            reputation: a.reputation ?? null,
          }))
        );
      }

      setAgents(myAgents);
      setSelectedAgent((prev) => (myAgents.length > 0 && !prev ? myAgents[0].address : prev));

      const earningsMap = new Map<Address, bigint>();
      for (const agent of myAgents) {
        earningsMap.set(agent.address, 0n);
      }
      setAgentEarnings(earningsMap);
    } catch (err: any) {
      console.error("Failed to fetch agents:", err);
    } finally {
      setLoadingData(false);
    }
  }, [account, authHeaders]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const fetchTaskStats = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch("/api/tasks", { headers });
      if (!res.ok) return;
      const data = await res.json();
      if (data.stats) {
        setTaskStats({
          total: data.stats.total ?? 0,
          executing: data.stats.executing ?? 0,
          queued: data.stats.queued ?? 0,
          completed: data.stats.completed ?? 0,
          failed: data.stats.failed ?? 0,
        });
      }
    } catch (err) {
      console.error("Failed to fetch task stats:", err);
    }
  }, [authHeaders]);

  useEffect(() => {
    if (user) fetchTaskStats();
  }, [user, fetchTaskStats]);

  const doRegisterOnChain = async () => {
    if (!selectedAgent || !account) return;
    const wc = getWalletClient();
    if (!wc) return;
    const agentInfo = agents.find((a) => a.address === selectedAgent);
    if (!agentInfo) return;
    try {
      setTxPending(true);
      setError(null);
      setTxHash(null);

      try {
        const agentData = await publicClient.readContract({
          address: CONTRACT_ADDRESSES.AgentRegistry,
          abi: AGENT_REGISTRY_ABI,
          functionName: "getAgent",
          args: [selectedAgent],
        }) as any;
        if (Number(agentData.status ?? agentData[5] ?? 0) > 0) {
          agentInfo.isOnChain = true;
          setAgents([...agents]);
          setTxPending(false);
          await fetchAgents();
          return;
        }
      } catch {
        // not registered — proceed
      }

      const hash = await wc.writeContract({
        address: CONTRACT_ADDRESSES.AgentRegistry,
        abi: AGENT_REGISTRY_ABI,
        functionName: "registerAgent",
        args: [
          selectedAgent,
          agentInfo.name,
          "",
          agentInfo.capabilities.length > 0 ? agentInfo.capabilities : ["general"],
        ],
        account,
        chain: baseSepolia,
      });
      setTxHash(hash);
      await publicClient.waitForTransactionReceipt({ hash });
      await fetchAgents();
    } catch (err: any) {
      const msg = err?.shortMessage || err?.message || "Registration failed";
      if (msg.includes("already registered")) {
        await fetchAgents();
      } else {
        setError(msg);
      }
    } finally {
      setTxPending(false);
    }
  };

  const selectedAgentInfo = agents.find((a) => a.address === selectedAgent);

  const totalEarnings = Array.from(agentEarnings.values()).reduce((sum, v) => sum + v, 0n);

  return (
    <div
      className="min-h-[calc(100vh-4rem)] text-[color:var(--foreground)] overflow-hidden relative"
      style={{ background: `linear-gradient(135deg, var(--home-bg-start), var(--home-bg-mid), var(--home-bg-end))` }}
    >
      {!authLoading && !user && (
        <div className="absolute inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 backdrop-blur-md bg-[color:var(--overlay-strong)]" />
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative z-50 flex flex-col items-center gap-6 bg-[color:var(--surface-2)] backdrop-blur-xl border border-[color:var(--border-subtle)] rounded-3xl px-10 py-12 shadow-2xl shadow-violet-500/10 max-w-md mx-4"
          >
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-600/20 border border-violet-500/30 flex items-center justify-center">
              <Lock size={36} className="text-violet-400" />
            </div>
            <div className="text-center">
              <h2 className="text-2xl font-bold text-[color:var(--foreground)] mb-2">Payout Portal Locked</h2>
              <p className="text-[color:var(--text-muted)] text-sm leading-relaxed">
                Sign in to access earnings and agent management on Base Sepolia.
              </p>
            </div>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold rounded-xl transition-all shadow-lg shadow-violet-500/20"
            >
              <LogIn size={18} />
              Sign In to Continue
            </Link>
          </motion.div>
        </div>
      )}

      <FloatingPaths position={1} />
      <FloatingPaths position={-1} />

      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-30" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="payoutGrid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(99, 102, 241, 0.06)" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#payoutGrid)" />
      </svg>

      <div className={`relative z-10 max-w-5xl mx-auto px-6 py-12 ${!authLoading && !user ? "pointer-events-none select-none" : ""}`}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <h1 className="text-3xl font-bold text-[color:var(--foreground)] mb-2">Developer Payout</h1>
          <p className="text-[color:var(--text-muted)]">Manage your agents and track earnings on Base Sepolia</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="mb-8 p-4 rounded-2xl bg-[color:var(--surface-1)] backdrop-blur-sm border border-[color:var(--border-subtle)] flex items-center justify-between"
        >
          {account ? (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
                <Wallet size={16} className="text-white" />
              </div>
              <div>
                <p className="text-sm text-[color:var(--text-muted)]">Connected</p>
                <p className="text-[color:var(--foreground)] font-mono text-sm">{shortAddr(account)}</p>
              </div>
              <button
                onClick={disconnectWallet}
                className="ml-4 px-3 py-1.5 text-xs text-[color:var(--text-muted)] hover:text-[color:var(--foreground)] border border-[color:var(--border-subtle)] rounded-lg hover:border-[color:var(--accent)] transition-all"
              >
                Disconnect
              </button>
            </div>
          ) : (
            <button
              onClick={connectWallet}
              disabled={connecting}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold rounded-xl transition-all disabled:opacity-50"
            >
              {connecting ? <Loader2 size={16} className="animate-spin" /> : <Wallet size={16} />}
              Connect MetaMask
            </button>
          )}
          <a
            href={explorerAddress(CONTRACT_ADDRESSES.AgentRegistry)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[color:var(--text-muted)] hover:text-violet-400 transition-colors flex items-center gap-1"
          >
            Registry <ExternalLink size={12} />
          </a>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between"
            >
              <span>{error}</span>
              <button onClick={() => setError(null)} className="ml-4 text-red-300 hover:text-[color:var(--foreground)]">
                <XCircle size={16} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {txHash && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 p-3 rounded-xl bg-violet-500/10 border border-violet-500/30 text-violet-300 text-xs flex items-center justify-between"
            >
              <span>
                Tx:{" "}
                <a href={explorerTx(txHash)} target="_blank" rel="noopener noreferrer" className="underline hover:text-[color:var(--foreground)]">
                  {shortAddr(txHash)}
                </a>
              </span>
              <button onClick={() => setTxHash(null)} className="text-violet-300 hover:text-[color:var(--foreground)]">
                <XCircle size={14} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {account && (
          <>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="mb-6"
            >
              <label className="block text-sm text-[color:var(--text-muted)] mb-2">Select Agent</label>
              {agents.length === 0 ? (
                <p className="text-[color:var(--text-muted)] text-sm">
                  No agents found for this wallet.{" "}
                  <Link href="/developers" className="text-violet-400 underline hover:text-violet-300">Register one first</Link>.
                </p>
              ) : (
                <select
                  value={selectedAgent || ""}
                  onChange={(e) => setSelectedAgent(e.target.value as Address)}
                  className="w-full max-w-md px-4 py-2.5 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] text-[color:var(--foreground)] focus:outline-none focus:border-violet-500 transition-colors"
                >
                  {agents.map((a) => (
                    <option key={a.address} value={a.address}>
                      {a.name} ({shortAddr(a.address)}) {a.isActive ? "" : "[Inactive]"}
                    </option>
                  ))}
                </select>
              )}
            </motion.div>

            {agents.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12 }}
                className="mb-6 p-5 rounded-2xl bg-gradient-to-r from-emerald-900/30 to-teal-900/20 backdrop-blur-sm border border-emerald-700/30"
              >
                <h2 className="text-sm font-medium text-emerald-400 mb-3 flex items-center gap-2">
                  <TrendingUp size={16} />
                  Total Agent Earnings
                </h2>
                <p className="text-3xl font-bold text-[color:var(--foreground)] mb-3">
                  {fmtUsdc(totalEarnings)} USDC
                </p>
                {agents.length > 1 && (
                  <div className="space-y-1">
                    {agents.map((a) => (
                      <div key={a.address} className="flex justify-between text-sm">
                        <span className="text-[color:var(--text-muted)] truncate max-w-[60%]">{a.name}</span>
                        <span className="text-[color:var(--foreground)] font-mono">
                          {fmtUsdc(agentEarnings.get(a.address) ?? 0n)} USDC
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}

            {selectedAgent && !selectedAgentInfo?.isOnChain && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.13 }}
                className="mb-6 p-5 rounded-2xl bg-gradient-to-r from-amber-900/20 to-orange-900/10 backdrop-blur-sm border border-amber-700/30"
              >
                <h2 className="text-sm font-medium text-amber-400 mb-2 flex items-center gap-2">
                  <Shield size={16} />
                  On-Chain Registration Required
                </h2>
                <p className="text-sm text-[color:var(--text-muted)] mb-4">
                  This agent needs to be registered on the Base Sepolia blockchain before it can receive jobs. This is a one-time transaction.
                </p>
                <button
                  onClick={doRegisterOnChain}
                  disabled={txPending}
                  className="px-6 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:bg-amber-800 disabled:cursor-not-allowed text-white font-medium text-sm transition-colors"
                >
                  {txPending ? "Registering..." : "Register Agent On-Chain"}
                </button>
              </motion.div>
            )}

            {selectedAgent && (
              <>
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                  className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8"
                >
                  <StatCard
                    icon={<Coins size={20} className="text-amber-400" />}
                    label="Earned (USDC)"
                    value={`${fmtUsdc(agentEarnings.get(selectedAgent) ?? 0n)} USDC`}
                    loading={loadingData}
                  />
                  <StatCard
                    icon={<Shield size={20} className="text-violet-400" />}
                    label="On-Chain Status"
                    value={selectedAgentInfo?.isOnChain ? "Registered" : "Not Registered"}
                    loading={loadingData}
                  />
                  <StatCard
                    icon={<TrendingUp size={20} className="text-emerald-400" />}
                    label="Agent Status"
                    value={selectedAgentInfo?.isActive ? "Active" : "Inactive"}
                    loading={loadingData}
                  />
                </motion.div>

                {taskStats && taskStats.total > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 }}
                    className="mb-8 p-6 rounded-2xl bg-[color:var(--surface-1)] backdrop-blur-sm border border-[color:var(--border-subtle)]"
                  >
                    <h2 className="text-lg font-semibold text-[color:var(--foreground)] mb-6 flex items-center gap-2">
                      <BarChart3 size={18} className="text-violet-400" />
                      Agent Metrics
                    </h2>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                      <div className="p-3 rounded-xl bg-violet-500/10 border border-violet-500/20 text-center">
                        <p className="text-2xl font-bold text-[color:var(--foreground)]">{taskStats.total}</p>
                        <p className="text-xs text-[color:var(--text-muted)] flex items-center justify-center gap-1">
                          <BarChart3 size={12} /> Total Jobs
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-center">
                        <p className="text-2xl font-bold text-emerald-400">{taskStats.completed}</p>
                        <p className="text-xs text-[color:var(--text-muted)] flex items-center justify-center gap-1">
                          <CheckCircle size={12} /> Completed
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-center">
                        <p className="text-2xl font-bold text-red-400">{taskStats.failed}</p>
                        <p className="text-xs text-[color:var(--text-muted)] flex items-center justify-center gap-1">
                          <AlertTriangle size={12} /> Failed
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-center">
                        <p className="text-2xl font-bold text-blue-400">
                          {Math.round((taskStats.completed / taskStats.total) * 100)}%
                        </p>
                        <p className="text-xs text-[color:var(--text-muted)] flex items-center justify-center gap-1">
                          <TrendingUp size={12} /> Success Rate
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row items-center gap-6 mb-6">
                      <JobsPieChart stats={taskStats} />
                      <div className="flex flex-col gap-2 text-sm">
                        {[
                          { label: "Completed", count: taskStats.completed, color: "bg-emerald-500" },
                          { label: "Executing", count: taskStats.executing, color: "bg-violet-500" },
                          { label: "Queued", count: taskStats.queued, color: "bg-blue-500" },
                          { label: "Failed", count: taskStats.failed, color: "bg-red-500" },
                        ].map((item) => (
                          <div key={item.label} className="flex items-center gap-2">
                            <div className={`w-3 h-3 rounded-full ${item.color}`} />
                            <span className="text-[color:var(--text-muted)]">{item.label}</span>
                            <span className="text-[color:var(--foreground)] font-medium ml-auto">{item.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {agentMetrics.length > 0 && (
                      <div>
                        <h3 className="text-sm font-medium text-[color:var(--text-muted)] mb-3">Agent Breakdown</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-[color:var(--border-subtle)]">
                                <th className="text-left py-2 text-[color:var(--text-muted)] font-medium">Agent</th>
                                <th className="text-right py-2 text-[color:var(--text-muted)] font-medium">Requests</th>
                                <th className="text-right py-2 text-[color:var(--text-muted)] font-medium">Success Rate</th>
                                <th className="text-right py-2 text-[color:var(--text-muted)] font-medium">Reputation</th>
                              </tr>
                            </thead>
                            <tbody>
                              {agentMetrics.map((agent, i) => {
                                const successRate = agent.totalRequests > 0
                                  ? Math.round((agent.successfulRequests / agent.totalRequests) * 100)
                                  : 0;
                                const rateColor = agent.totalRequests === 0
                                  ? "text-[color:var(--text-muted)]"
                                  : successRate >= 80
                                  ? "text-emerald-400"
                                  : "text-amber-400";
                                return (
                                  <tr key={i} className="border-b border-[color:var(--border-subtle)]/50">
                                    <td className="py-2 text-[color:var(--foreground)]">{agent.name}</td>
                                    <td className="py-2 text-right text-[color:var(--foreground)] font-mono">{agent.totalRequests}</td>
                                    <td className={`py-2 text-right ${rateColor}`}>{successRate}%</td>
                                    <td className="py-2 text-right text-[color:var(--foreground)] font-mono">
                                      {agent.reputation !== null ? agent.reputation.toFixed(1) : "--"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                  className="p-4 rounded-2xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)]"
                >
                  <h3 className="text-sm font-medium text-[color:var(--text-muted)] mb-3">Contracts on Base Sepolia</h3>
                  <div className="flex flex-wrap gap-3">
                    {[
                      { name: "AgentRegistry", addr: CONTRACT_ADDRESSES.AgentRegistry },
                      { name: "OrderBook", addr: CONTRACT_ADDRESSES.OrderBook },
                      { name: "Escrow", addr: CONTRACT_ADDRESSES.Escrow },
                      { name: "USDC", addr: CONTRACT_ADDRESSES.USDC },
                    ].map((c) => (
                      <a
                        key={c.name}
                        href={explorerAddress(c.addr)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] text-xs text-[color:var(--foreground)] hover:text-violet-400 hover:border-violet-500/30 transition-all"
                      >
                        {c.name}
                        <ExternalLink size={10} />
                      </a>
                    ))}
                  </div>
                </motion.div>

                <div className="mt-6 flex justify-center">
                  <button
                    onClick={fetchAgents}
                    className="flex items-center gap-2 text-xs text-[color:var(--text-muted)] hover:text-violet-400 transition-colors"
                  >
                    <RefreshCw size={12} />
                    Refresh data
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  loading: boolean;
}

function StatCard({ icon, label, value, loading }: StatCardProps): React.JSX.Element {
  return (
    <div className="p-4 rounded-2xl bg-[color:var(--surface-1)] backdrop-blur-sm border border-[color:var(--border-subtle)]">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-[color:var(--text-muted)]">{label}</span>
      </div>
      {loading ? (
        <div className="h-7 w-24 bg-[color:var(--surface-1)] rounded animate-pulse mt-1" />
      ) : (
        <p className="text-xl font-bold text-[color:var(--foreground)]">{value}</p>
      )}
    </div>
  );
}

function JobsPieChart({ stats }: { stats: TaskStats }): React.JSX.Element {
  const total = stats.total || 1;
  const segments = [
    { value: stats.completed, color: "#10b981" },
    { value: stats.executing, color: "#8b5cf6" },
    { value: stats.queued, color: "#3b82f6" },
    { value: stats.failed, color: "#ef4444" },
  ];

  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <svg width="120" height="120" viewBox="0 0 120 120" className="flex-shrink-0">
      <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="20" />
      {segments.map((seg, i) => {
        const dashLen = (seg.value / total) * circumference;
        const dashOffset = -offset;
        offset += dashLen;
        if (seg.value === 0) return null;
        return (
          <circle
            key={i}
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke={seg.color}
            strokeWidth="20"
            strokeDasharray={`${dashLen} ${circumference - dashLen}`}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 60 60)"
            className="transition-all duration-500"
          />
        );
      })}
      <text x="60" y="56" textAnchor="middle" className="fill-[color:var(--foreground)]" fontSize="20" fontWeight="bold">
        {total}
      </text>
      <text x="60" y="72" textAnchor="middle" className="fill-[color:var(--text-muted)]" fontSize="10">
        jobs
      </text>
    </svg>
  );
}
