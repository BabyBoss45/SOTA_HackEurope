"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Plus,
  Eye,
  Pencil,
  Trash2,
  Activity,
  DollarSign,
  TrendingUp,
  Shield,
  AlertCircle,
  ChevronRight,
  Loader2,
  X,
  Wallet,
  Key,
  Copy,
  Check,
  RefreshCw,
  Lock,
  LogIn,
  Info,
  Globe,
  Cpu,
  BookOpen,
  ClipboardList,
  type LucideIcon,
} from "lucide-react";
import { FloatingPaths } from "@/components/ui/background-paths-wrapper";
import { useAuth } from "@/components/auth-provider";
import { isValidSolanaAddress as validateSolanaAddr, isValidHttpUrl, AGENT_CATEGORIES, parseCapabilities } from "@/lib/validators";
import Link from "next/link";

interface Agent {
  id: number;
  title: string;
  description: string;
  category: string | null;
  status: string;
  isVerified: boolean;
  reputation: number;
  totalRequests: number;
  successfulRequests: number;
  minFeeUsdc: number;
  capabilities: string | null;
  icon: string | null;
  walletAddress: string;
  apiEndpoint: string | null;
  webhookUrl: string | null;
}

interface ApiKey {
  id: number;
  keyId: string;
  name: string;
  permissions: string[];
  lastUsedAt: string | null;
  expiresAt: string | null;
  isActive: boolean;
  createdAt: string;
}

export default function DeveloperPortal() {
  const { user, loading: authLoading, getIdToken } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNewAgentModal, setShowNewAgentModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Auth headers helper
  const authHeaders = async (): Promise<HeadersInit> => {
    const token = await getIdToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Fetch only the current user's agents
  const fetchAgents = async () => {
    try {
      setLoading(true);
      const headers = await authHeaders();
      const res = await fetch('/api/agents?mine=true', { headers });
      if (res.status === 401) {
        setAgents([]);
        setError(null);
        return;
      }
      if (!res.ok) {
        setError('Failed to load agents');
        return;
      }
      const data = await res.json();
      if (data.agents) {
        setAgents(data.agents.map((a: Record<string, unknown>) => ({
          ...a,
          walletAddress: a.walletAddress || '',
          apiEndpoint: a.apiEndpoint || null,
          webhookUrl: a.webhookUrl || null,
          category: a.category || null,
        })));
      }
      setError(null);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
      setError('Failed to load agents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) fetchAgents();
    else setLoading(false);
  }, [user]);

  const handleDeleteAgent = async (agent: Agent) => {
    try {
      const headers = await authHeaders();
      const res = await fetch(`/api/agents/${agent.id}`, {
        method: 'DELETE',
        headers,
      });
      
      if (res.ok) {
        setAgents(agents.filter((a) => a.id !== agent.id));
        setShowDeleteConfirm(false);
        setSelectedAgent(null);
        setActionError(null);
      } else {
        const data = await res.json();
        setActionError(data.error || 'Failed to delete agent');
      }
    } catch (err) {
      console.error('Delete error:', err);
      setActionError('Failed to delete agent');
    }
  };

  const handleAgentCreated = () => {
    fetchAgents();
    setShowNewAgentModal(false);
  };

  const handleAgentUpdated = (updated: Agent) => {
    setAgents(agents.map(a => a.id === updated.id ? updated : a));
    setShowEditModal(false);
    setSelectedAgent(null);
  };

  const successRate = (agent: Agent) => {
    if (agent.totalRequests === 0) return 100;
    return Math.round((agent.successfulRequests / agent.totalRequests) * 100);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] home-shell text-[color:var(--foreground)] overflow-hidden relative">
      {/* Auth Guard Overlay — blurs page content but nav remains accessible */}
      {!authLoading && !user && (
        <div className="absolute inset-0 z-40 flex items-center justify-center">
          {/* Blur backdrop */}
          <div className="absolute inset-0 backdrop-blur-md bg-[color:var(--overlay-strong)]" />
          {/* Locked card */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative z-50 flex flex-col items-center gap-6 bg-[color:var(--surface-2)] backdrop-blur-xl border border-[color:var(--border-subtle)] rounded-3xl px-10 py-12 shadow-2xl shadow-violet-500/10 max-w-md mx-4"
          >
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-600/20 border border-violet-500/30 flex items-center justify-center">
              <Lock size={36} className="text-violet-400" />
            </div>
            <div className="text-center">
              <h2 className="text-2xl font-bold text-[color:var(--foreground)] mb-2">Developer Portal Locked</h2>
              <p className="text-[color:var(--text-muted)] text-sm leading-relaxed">
                Sign in to your SOTA account to access the Developer Portal,
                register agents, and manage your marketplace presence.
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

      {/* Background */}
      <FloatingPaths position={1} />
      <FloatingPaths position={-1} />

      {/* Grid Background */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-30" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="devGrid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="var(--home-grid-stroke)" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#devGrid)" />
      </svg>

      <div className={`relative z-10 max-w-7xl mx-auto px-6 py-12 ${!authLoading && !user ? 'pointer-events-none select-none' : ''}`}>
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-[color:var(--foreground)] mb-2">Developer Portal</h1>
              <p className="text-[color:var(--text-muted)]">Register and manage your AI agents on the SOTA marketplace</p>
            </div>
            <button
              onClick={() => setShowNewAgentModal(true)}
              className="inline-flex items-center gap-2 px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-all"
            >
              <Plus size={20} />
              Register Agent
            </button>
          </div>
        </motion.div>

        {(error || actionError) && (
          <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400">
            {error || actionError}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={32} className="text-violet-500 animate-spin" />
          </div>
        ) : (
          <>
            {/* Agents List */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-6"
            >
                {agents.length === 0 ? (
                  <div className="text-center py-20">
                    <Bot size={48} className="text-[color:var(--text-muted)] mx-auto mb-4" />
                    <h3 className="text-xl font-semibold text-[color:var(--foreground)] mb-2">No agents registered yet</h3>
                    <p className="text-[color:var(--text-muted)] mb-6">Register your first AI agent to get started on the SOTA marketplace</p>
                    <button
                      onClick={() => setShowNewAgentModal(true)}
                      className="inline-flex items-center gap-2 px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-all"
                    >
                      <Plus size={20} />
                      Register Agent
                    </button>
                  </div>
                ) : (
                  <div className="grid gap-6">
                    {agents.map((agent) => (
                      <motion.div
                        key={agent.id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-4">
                            <div className="w-12 h-12 rounded-xl bg-violet-500/20 flex items-center justify-center">
                              <Bot size={24} className="text-violet-400" />
                            </div>
                            <div>
                              <div className="flex items-center gap-3 mb-1">
                                <h3 className="text-lg font-semibold text-[color:var(--foreground)]">{agent.title}</h3>
                                {agent.isVerified && (
                                  <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/20 text-emerald-400">
                                    <Shield size={12} />
                                    Verified
                                  </span>
                                )}
                                <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                                  agent.status === "active"
                                    ? "bg-emerald-500/20 text-emerald-400"
                                    : "bg-amber-500/20 text-amber-400"
                                }`}>
                                  {agent.status}
                                </span>
                              </div>
                              <p className="text-sm text-[color:var(--text-muted)] mb-3">{agent.description}</p>
                              <div className="flex items-center gap-4 text-sm">
                                <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                  <Activity size={14} />
                                  <span>{agent.totalRequests} requests</span>
                                </div>
                                <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                  <TrendingUp size={14} />
                                  <span>{successRate(agent)}% success</span>
                                </div>
                                <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                  <DollarSign size={14} />
                                  <span>${agent.minFeeUsdc} min fee</span>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => {
                                setSelectedAgent(agent);
                                setShowViewModal(true);
                              }}
                              className="p-2 hover:bg-[color:var(--surface-hover)] rounded-lg transition-colors"
                              title="View Details"
                            >
                              <Eye size={18} className="text-[color:var(--text-muted)]" />
                            </button>
                            <button
                              onClick={() => {
                                setSelectedAgent(agent);
                                setShowEditModal(true);
                              }}
                              className="p-2 hover:bg-[color:var(--surface-hover)] rounded-lg transition-colors"
                              title="Edit Agent"
                            >
                              <Pencil size={18} className="text-[color:var(--text-muted)]" />
                            </button>
                            <button
                              onClick={() => {
                                setSelectedAgent(agent);
                                setShowDeleteConfirm(true);
                              }}
                              className="p-2 hover:bg-red-500/20 rounded-lg transition-colors"
                              title="Delete Agent"
                            >
                              <Trash2 size={18} className="text-red-400" />
                            </button>
                          </div>
                        </div>

                        {/* Stats Bar */}
                        <div className="mt-6 grid grid-cols-4 gap-4">
                          <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                            <div className="text-2xl font-bold text-[color:var(--foreground)]">{agent.reputation.toFixed(1)}</div>
                            <div className="text-xs text-[color:var(--text-muted)]">Reputation</div>
                          </div>
                          <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                            <div className="text-2xl font-bold text-[color:var(--foreground)]">{agent.totalRequests}</div>
                            <div className="text-xs text-[color:var(--text-muted)]">Total Jobs</div>
                          </div>
                          <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                            <div className="text-2xl font-bold text-emerald-400">{successRate(agent)}%</div>
                            <div className="text-xs text-[color:var(--text-muted)]">Success Rate</div>
                          </div>
                          <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                            <div className="text-2xl font-bold text-violet-400">${agent.minFeeUsdc}</div>
                            <div className="text-xs text-[color:var(--text-muted)]">Min Fee</div>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
          </>
        )}
      </div>

      {/* New Agent Modal */}
      {showNewAgentModal && (
        <NewAgentModal
          onClose={() => setShowNewAgentModal(false)}
          onSuccess={handleAgentCreated}
          getAuthHeaders={authHeaders}
        />
      )}

      {/* View Agent Modal */}
      {showViewModal && selectedAgent && (
        <ViewAgentModal
          agent={selectedAgent}
          onClose={() => {
            setShowViewModal(false);
            setSelectedAgent(null);
          }}
          getAuthHeaders={authHeaders}
        />
      )}

      {/* Edit Agent Modal */}
      {showEditModal && selectedAgent && (
        <EditAgentModal
          agent={selectedAgent}
          onClose={() => {
            setShowEditModal(false);
            setSelectedAgent(null);
          }}
          onSave={handleAgentUpdated}
          getAuthHeaders={authHeaders}
        />
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && selectedAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[color:var(--overlay-strong)] backdrop-blur-sm" onClick={() => setShowDeleteConfirm(false)} />
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative w-full max-w-md bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)] rounded-2xl p-6 shadow-2xl"
          >
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
                <Trash2 size={24} className="text-red-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-[color:var(--foreground)]">Delete Agent</h3>
                <p className="text-sm text-[color:var(--text-muted)]">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-[color:var(--foreground)] mb-6">
              Are you sure you want to delete <span className="font-semibold text-[color:var(--foreground)]">{selectedAgent.title}</span>? 
              All associated data will be permanently removed.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 px-4 py-2 bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-hover)] text-[color:var(--foreground)] rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteAgent(selectedAgent)}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors"
              >
                Delete
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

// --- Inline helpers for NewAgentModal ---

const STEPS: { num: number; title: string; icon: LucideIcon; description: string }[] = [
  { num: 1, title: "Agent Identity",    icon: Bot,           description: "Name, description & category" },
  { num: 2, title: "Wallet & Payment",  icon: Wallet,        description: "Payout wallet & pricing" },
  { num: 3, title: "API Connection",    icon: Globe,         description: "Endpoint for job execution" },
  { num: 4, title: "Capabilities",      icon: Cpu,           description: "What your agent can do" },
  { num: 5, title: "Integration Guide", icon: BookOpen,      description: "How to connect to SOTA" },
  { num: 6, title: "Review & Submit",   icon: ClipboardList, description: "Verify and register" },
];

const CAPABILITY_DETAILS: Record<string, { label: string; description: string }> = {
  voice_call:       { label: "Voice Call",        description: "Make or receive voice calls on behalf of users" },
  web_scrape:       { label: "Web Scraping",      description: "Extract structured data from websites" },
  data_analysis:    { label: "Data Analysis",     description: "Analyze datasets, generate insights & charts" },
  code_execution:   { label: "Code Execution",    description: "Run code in a sandboxed environment" },
  image_generation: { label: "Image Generation",  description: "Generate images from text prompts" },
  text_generation:  { label: "Text Generation",   description: "Generate or transform text content" },
  api_integration:  { label: "API Integration",   description: "Call third-party APIs and aggregate results" },
  blockchain:       { label: "Blockchain",        description: "Read/write on-chain data and execute transactions" },
};

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 mt-2 px-3 py-2 rounded-lg border border-violet-500/30 bg-violet-500/5 text-xs text-violet-300">
      <Info size={14} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function CodeBlock({ title, language, code }: { title: string; language: string; code: string }) {
  const [copied, setCopied] = React.useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API may fail in non-HTTPS contexts
    }
  };
  return (
    <div className="rounded-lg border border-[color:var(--border-subtle)] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-[color:var(--surface-1)] border-b border-[color:var(--border-subtle)]">
        <span className="text-sm font-medium text-[color:var(--foreground)]">{title}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded bg-violet-500/20 text-violet-300">{language}</span>
          <button onClick={handleCopy} className="p-1 hover:bg-[color:var(--surface-hover)] rounded transition-colors" title="Copy">
            {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} className="text-[color:var(--text-muted)]" />}
          </button>
        </div>
      </div>
      <pre className="px-4 py-3 text-xs font-mono text-[color:var(--foreground)] bg-[color:var(--surface-1)]/50 overflow-x-auto whitespace-pre">
{code}</pre>
    </div>
  );
}

// New Agent Registration Modal
function NewAgentModal({ onClose, onSuccess, getAuthHeaders }: { onClose: () => void; onSuccess: () => void; getAuthHeaders: () => Promise<HeadersInit> }) {
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    category: "",
    tags: [] as string[],
    walletAddress: "",
    apiEndpoint: "",
    webhookUrl: "",
    capabilities: [] as string[],
    minFeeUsdc: 0.05,
    network: "solana-devnet",
    bidAggressiveness: 0.8,
  });
  const [tagInput, setTagInput] = useState("");

  const canProceed = (s: number): boolean => {
    switch (s) {
      case 1: return formData.title.length >= 3 && formData.description.length >= 10;
      case 2: return validateSolanaAddr(formData.walletAddress);
      case 3: return isValidHttpUrl(formData.apiEndpoint);
      case 4: return formData.capabilities.length >= 1;
      case 5: return true; // read-only guide
      case 6: return true; // review page
      default: return false;
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await fetch('/api/agents', {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: formData.title,
          description: formData.description,
          category: formData.category,
          tags: formData.tags.join(",") || undefined,
          network: formData.network,
          walletAddress: formData.walletAddress,
          apiEndpoint: formData.apiEndpoint,
          webhookUrl: formData.webhookUrl || undefined,
          capabilities: JSON.stringify(formData.capabilities),
          minFeeUsdc: formData.minFeeUsdc,
          priceUsd: formData.minFeeUsdc,
          bidAggressiveness: formData.bidAggressiveness,
        }),
      });

      if (res.ok) {
        onSuccess();
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to create agent');
      }
    } catch (err) {
      console.error('Create error:', err);
      setError('Failed to create agent');
    } finally {
      setSubmitting(false);
    }
  };

  const currentStep = STEPS[step - 1];
  const StepIcon = currentStep.icon;

  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://sota.market";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[color:var(--overlay-strong)] backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative w-full max-w-2xl bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[color:var(--border-subtle)]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center">
              <StepIcon size={20} className="text-violet-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-[color:var(--foreground)]">Register New Agent</h2>
              <p className="text-sm text-[color:var(--text-muted)]">Step {step} of 6 &mdash; {currentStep.title}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[color:var(--surface-1)] rounded-lg" aria-label="Close">
            <X size={20} className="text-[color:var(--text-muted)]" />
          </button>
        </div>

        {/* Progress */}
        <div className="flex gap-1.5 px-6 py-3 bg-[color:var(--surface-1)]">
          {STEPS.map((s) => (
            <div
              key={s.num}
              className={`flex-1 h-1 rounded-full transition-colors ${s.num <= step ? "bg-violet-500" : "bg-[color:var(--surface-hover)]"}`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          {/* Step 1 — Agent Identity */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Agent Name <span className="text-red-400">*</span></label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="My Awesome Agent"
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500"
                />
                <Tip>This name appears on the marketplace. Make it descriptive so users know what your agent does.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Description <span className="text-red-400">*</span></label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Describe what your agent does..."
                  rows={3}
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 resize-none"
                />
                <Tip>A clear description helps the marketplace match your agent with the right jobs. Minimum 10 characters.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Category</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
                >
                  <option value="">Select category</option>
                  {AGENT_CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Tags</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {formData.tags.map((tag) => (
                    <span key={tag} className="inline-flex items-center gap-1 px-3 py-1 text-sm bg-violet-500/20 text-violet-300 rounded-lg">
                      {tag}
                      <button
                        onClick={() => setFormData(prev => ({ ...prev, tags: prev.tags.filter(t => t !== tag) }))}
                        className="hover:text-white transition-colors ml-1"
                      >
                        &times;
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const tag = tagInput.trim().toLowerCase().replace(/\s+/g, "_");
                        if (tag && !formData.tags.includes(tag)) {
                          setFormData(prev => ({ ...prev, tags: [...prev.tags, tag] }));
                        }
                        setTagInput("");
                      }
                    }}
                    placeholder="Add a tag..."
                    className="flex-1 px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const tag = tagInput.trim().toLowerCase().replace(/\s+/g, "_");
                      if (tag && !formData.tags.includes(tag)) {
                        setFormData(prev => ({ ...prev, tags: [...prev.tags, tag] }));
                      }
                      setTagInput("");
                    }}
                    className="px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    Add
                  </button>
                </div>
                <Tip>Tags help users discover your agent in search. E.g. &quot;scraper&quot;, &quot;defi&quot;, &quot;nlp&quot;.</Tip>
              </div>
            </div>
          )}

          {/* Step 2 — Wallet & Payment */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">
                  <span className="flex items-center gap-2">
                    <Wallet size={16} />
                    Wallet Address <span className="text-red-400">*</span>
                  </span>
                </label>
                <input
                  type="text"
                  value={formData.walletAddress}
                  onChange={(e) => setFormData(prev => ({ ...prev, walletAddress: e.target.value }))}
                  placeholder="Enter Solana address (base58)"
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono"
                />
                {formData.walletAddress && !validateSolanaAddr(formData.walletAddress) && (
                  <p className="text-xs text-red-400 mt-1">Must be a valid Solana address (base58, 32-44 characters)</p>
                )}
                <Tip>Payments settle in USDC on Solana Devnet. This wallet will receive all marketplace earnings for this agent.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Minimum Fee (USDC)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.minFeeUsdc}
                  onChange={(e) => setFormData(prev => ({ ...prev, minFeeUsdc: parseFloat(e.target.value) || 0 }))}
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
                />
                <Tip>The lowest price your agent will accept per job. You can still bid higher on individual jobs.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">
                  Bid Aggressiveness ({formData.bidAggressiveness.toFixed(2)})
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="1.0"
                  step="0.05"
                  value={formData.bidAggressiveness}
                  onChange={(e) => setFormData(prev => ({ ...prev, bidAggressiveness: parseFloat(e.target.value) }))}
                  className="w-full accent-violet-500"
                />
                <div className="flex justify-between text-xs text-[color:var(--text-muted)] mt-1">
                  <span>Aggressive (0.50)</span>
                  <span>Conservative (1.00)</span>
                </div>
                <Tip>Controls how competitively your agent bids. Lower values = undercut competitors more, higher = preserve margins.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Network</label>
                <select
                  value={formData.network}
                  onChange={(e) => setFormData(prev => ({ ...prev, network: e.target.value }))}
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
                >
                  <option value="solana-devnet">Solana Devnet</option>
                  <option value="solana-mainnet">Solana Mainnet</option>
                </select>
                <Tip>Choose Devnet for testing, Mainnet for production. Payments settle on the selected network.</Tip>
              </div>
            </div>
          )}

          {/* Step 3 — API Connection */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">API Endpoint <span className="text-red-400">*</span></label>
                <input
                  type="url"
                  value={formData.apiEndpoint}
                  onChange={(e) => setFormData(prev => ({ ...prev, apiEndpoint: e.target.value }))}
                  placeholder="https://your-agent.com/api/execute"
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500"
                />
                {formData.apiEndpoint && !isValidHttpUrl(formData.apiEndpoint) && (
                  <p className="text-xs text-red-400 mt-1">Please enter a valid HTTP/HTTPS URL</p>
                )}
                <Tip>SOTA sends POST requests to this URL when your agent wins a job. The request body contains the job description, parameters, and a callback URL for results.</Tip>
              </div>
              <div>
                <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Webhook URL (optional)</label>
                <input
                  type="url"
                  value={formData.webhookUrl}
                  onChange={(e) => setFormData(prev => ({ ...prev, webhookUrl: e.target.value }))}
                  placeholder="https://your-agent.com/webhook"
                  className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500"
                />
                <Tip>Optional callback for status updates (job assigned, cancelled, etc.). If blank, you can poll the marketplace API instead.</Tip>
              </div>
            </div>
          )}

          {/* Step 4 — Capabilities */}
          {step === 4 && (
            <div className="space-y-4">
              <p className="text-sm text-[color:var(--text-muted)]">Select at least one capability that describes what your agent can do. This helps the marketplace route the right jobs to you.</p>
              {formData.capabilities.length === 0 && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-400">
                  <AlertCircle size={14} />
                  Select at least 1 capability to continue
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(CAPABILITY_DETAILS).map(([key, { label, description }]) => {
                  const selected = formData.capabilities.includes(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        const caps = selected
                          ? formData.capabilities.filter((c) => c !== key)
                          : [...formData.capabilities, key];
                        setFormData(prev => ({ ...prev, capabilities: caps }));
                      }}
                      className={`text-left p-3 rounded-lg border transition-all ${
                        selected
                          ? "bg-violet-500/15 border-violet-500 ring-1 ring-violet-500/50"
                          : "bg-[color:var(--surface-1)] border-[color:var(--border-subtle)] hover:border-violet-500/40"
                      }`}
                    >
                      <div className={`text-sm font-medium mb-0.5 ${selected ? "text-violet-300" : "text-[color:var(--foreground)]"}`}>
                        {label}
                      </div>
                      <div className="text-xs text-[color:var(--text-muted)]">{description}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step 5 — Integration Guide */}
          {step === 5 && (
            <div className="space-y-5">
              <p className="text-sm text-[color:var(--text-muted)]">
                Use these endpoints to integrate your agent with the SOTA marketplace. Generate an API key after registration from the agent details panel.
              </p>

              <CodeBlock
                title="1. Authenticate"
                language="HTTP"
                code={`# Include this header in every request\nAuthorization: ApiKey ak_xxx.secret\n\n# Generate your key from the Developer Portal\n# after registering this agent.`}
              />

              <CodeBlock
                title="2. Poll for Jobs"
                language="HTTP"
                code={`GET ${baseUrl}/api/marketplace/bid\n\n# Response\n{\n  "jobs": [\n    {\n      "id": "job_abc123",\n      "description": "Scrape product prices from ...",\n      "budget": 0.50,\n      "requiredCapabilities": ["web_scrape"]\n    }\n  ]\n}`}
              />

              <CodeBlock
                title="3. Submit a Bid"
                language="HTTP"
                code={`POST ${baseUrl}/api/marketplace/bid\nContent-Type: application/json\n\n{\n  "jobId": "job_abc123",\n  "bidPrice": 0.35\n}`}
              />

              <CodeBlock
                title="4. Execute & Report"
                language="HTTP"
                code={`POST ${baseUrl}/api/marketplace/execute\nContent-Type: application/json\n\n{\n  "jobId": "job_abc123",\n  "result": { "data": "..." },\n  "status": "completed"\n}`}
              />
            </div>
          )}

          {/* Step 6 — Review & Submit */}
          {step === 6 && (
            <div className="space-y-4">
              <div className="rounded-xl border border-[color:var(--border-subtle)] overflow-hidden">
                {[
                  { label: "Name",          value: formData.title },
                  { label: "Description",   value: formData.description },
                  { label: "Category",      value: formData.category || "Not set" },
                  { label: "Tags",          value: formData.tags.length > 0 ? formData.tags.join(", ") : "None" },
                  { label: "Wallet",        value: formData.walletAddress, mono: true },
                  { label: "Min Fee",       value: `$${formData.minFeeUsdc} USDC` },
                  { label: "Bid Strategy",  value: `${formData.bidAggressiveness.toFixed(2)} (${formData.bidAggressiveness <= 0.6 ? "Aggressive" : formData.bidAggressiveness >= 0.9 ? "Conservative" : "Moderate"})` },
                  { label: "Network",       value: formData.network === "solana-mainnet" ? "Solana Mainnet" : "Solana Devnet" },
                  { label: "API Endpoint",  value: formData.apiEndpoint, mono: true },
                  { label: "Webhook",       value: formData.webhookUrl || "Not set", mono: !!formData.webhookUrl },
                  { label: "Capabilities",  value: formData.capabilities.map(c => CAPABILITY_DETAILS[c]?.label ?? c).join(", ") },
                ].map(({ label, value, mono }, i) => (
                  <div key={label} className={`flex items-start gap-4 px-4 py-3 ${i % 2 === 0 ? "bg-[color:var(--surface-1)]" : ""}`}>
                    <span className="text-sm text-[color:var(--text-muted)] w-32 shrink-0">{label}</span>
                    <span className={`text-sm text-[color:var(--foreground)] break-all ${mono ? "font-mono" : ""}`}>{value}</span>
                  </div>
                ))}
              </div>

              <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <div className="flex items-start gap-3">
                  <AlertCircle size={20} className="text-amber-400 mt-0.5" />
                  <div>
                    <h4 className="font-medium text-amber-400">Before submitting</h4>
                    <ul className="text-sm text-[color:var(--text-muted)] mt-1 space-y-1">
                      <li>&bull; Your agent will be in &quot;pending&quot; status until verified</li>
                      <li>&bull; SOTA will test your API endpoint for connectivity</li>
                      <li>&bull; Generate an API key after registration to start receiving jobs</li>
                    </ul>
                  </div>
                </div>
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
          <button
            onClick={() => (step > 1 ? setStep(step - 1) : onClose())}
            className="px-4 py-2 text-[color:var(--text-muted)] hover:text-[color:var(--foreground)] transition-colors"
            disabled={submitting}
          >
            {step > 1 ? "Back" : "Cancel"}
          </button>
          <button
            onClick={() => (step < 6 ? setStep(step + 1) : handleSubmit())}
            disabled={submitting || (step < 6 && !canProceed(step))}
            className="inline-flex items-center gap-2 px-6 py-2 bg-violet-600 hover:bg-violet-500 text-white font-medium rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Creating...
              </>
            ) : step < 6 ? (
              <>
                Next
                <ChevronRight size={16} />
              </>
            ) : (
              "Register Agent"
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// View Agent Modal with API Keys
function ViewAgentModal({ agent, onClose, getAuthHeaders }: { agent: Agent; onClose: () => void; getAuthHeaders: () => Promise<HeadersInit> }) {
  const [activeTab, setActiveTab] = useState<'details' | 'api-keys'>('details');
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [generatingKey, setGeneratingKey] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [showNewKeyModal, setShowNewKeyModal] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);

  const successRate = agent.totalRequests === 0 ? 100 : Math.round((agent.successfulRequests / agent.totalRequests) * 100);
  const capabilities = parseCapabilities(agent.capabilities);

  // Fetch API keys for this agent
  const fetchApiKeys = async () => {
    setLoadingKeys(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`/api/agents/${agent.id}/keys`, { headers });
      if (res.ok) {
        const data = await res.json();
        setApiKeys(data.keys || []);
      }
    } catch (err) {
      console.error('Failed to fetch API keys:', err);
    } finally {
      setLoadingKeys(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'api-keys') {
      fetchApiKeys();
    }
  }, [activeTab, agent.id]);

  // Generate new API key
  const handleGenerateKey = async () => {
    setGeneratingKey(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`/api/agents/${agent.id}/keys`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newKeyName || 'Default' }),
      });
      
      if (res.ok) {
        const data = await res.json();
        setGeneratedKey(data.apiKey.fullKey);
        setNewKeyName('');
        setKeyError(null);
        fetchApiKeys();
      } else {
        const data = await res.json();
        setKeyError(data.error || 'Failed to generate API key');
      }
    } catch (err) {
      console.error('Generate key error:', err);
      setKeyError('Failed to generate API key');
    } finally {
      setGeneratingKey(false);
      setShowNewKeyModal(false);
    }
  };

  // Revoke API key
  const handleRevokeKey = async (keyId: string) => {
    setRevokingKeyId(keyId);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`/api/agents/${agent.id}/keys`, {
        method: 'DELETE',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyId }),
      });
      
      if (res.ok) {
        setKeyError(null);
        fetchApiKeys();
      } else {
        const data = await res.json();
        setKeyError(data.error || 'Failed to revoke API key');
      }
    } catch (err) {
      console.error('Revoke key error:', err);
      setKeyError('Failed to revoke API key');
    } finally {
      setRevokingKeyId(null);
    }
  };

  // Copy key to clipboard
  const handleCopyKey = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {
      // clipboard API may fail in non-HTTPS contexts
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[color:var(--overlay-strong)] backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative w-full max-w-2xl bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[color:var(--border-subtle)]">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-violet-500/20 flex items-center justify-center">
              <Bot size={24} className="text-violet-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-[color:var(--foreground)]">{agent.title}</h2>
                {agent.isVerified && (
                  <Shield size={16} className="text-emerald-400" />
                )}
              </div>
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                agent.status === "active"
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "bg-amber-500/20 text-amber-400"
              }`}>
                {agent.status}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[color:var(--surface-1)] rounded-lg">
            <X size={20} className="text-[color:var(--text-muted)]" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[color:var(--border-subtle)]">
          <button
            onClick={() => setActiveTab('details')}
            className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'details'
                ? 'text-violet-400 border-b-2 border-violet-400'
                : 'text-[color:var(--text-muted)] hover:text-[color:var(--foreground)]'
            }`}
          >
            Details
          </button>
          <button
            onClick={() => setActiveTab('api-keys')}
            className={`flex-1 px-6 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              activeTab === 'api-keys'
                ? 'text-violet-400 border-b-2 border-violet-400'
                : 'text-[color:var(--text-muted)] hover:text-[color:var(--foreground)]'
            }`}
          >
            <Key size={16} />
            API Keys
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
          {activeTab === 'details' ? (
            <>
              <div>
                <h4 className="text-sm font-medium text-[color:var(--text-muted)] mb-2">Description</h4>
                <p className="text-[color:var(--foreground)]">{agent.description}</p>
              </div>

              <div>
                <h4 className="text-sm font-medium text-[color:var(--text-muted)] mb-2">Wallet Address</h4>
                <code className="block px-3 py-2 bg-[color:var(--surface-1)] rounded-lg text-sm text-violet-400 font-mono">
                  {agent.walletAddress}
                </code>
              </div>

              <div className="grid grid-cols-4 gap-4">
                <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                  <div className="text-2xl font-bold text-[color:var(--foreground)]">{agent.reputation.toFixed(1)}</div>
                  <div className="text-xs text-[color:var(--text-muted)]">Reputation</div>
                </div>
                <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                  <div className="text-2xl font-bold text-[color:var(--foreground)]">{agent.totalRequests}</div>
                  <div className="text-xs text-[color:var(--text-muted)]">Total Jobs</div>
                </div>
                <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                  <div className="text-2xl font-bold text-emerald-400">{successRate}%</div>
                  <div className="text-xs text-[color:var(--text-muted)]">Success Rate</div>
                </div>
                <div className="p-3 rounded-lg bg-[color:var(--surface-1)]">
                  <div className="text-2xl font-bold text-violet-400">${agent.minFeeUsdc}</div>
                  <div className="text-xs text-[color:var(--text-muted)]">Min Fee</div>
                </div>
              </div>

              {capabilities.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-[color:var(--text-muted)] mb-2">Capabilities</h4>
                  <div className="flex flex-wrap gap-2">
                    {capabilities.map((cap: string) => (
                      <span key={cap} className="px-3 py-1 text-sm bg-violet-500/20 text-violet-300 rounded-lg">
                        {cap.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Generated Key Display */}
              <AnimatePresence>
                {generatedKey && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30"
                  >
                    <div className="flex items-start gap-3">
                      <Key size={20} className="text-emerald-400 mt-0.5" />
                      <div className="flex-1">
                        <h4 className="font-medium text-emerald-400 mb-1">API Key Generated!</h4>
                        <p className="text-sm text-[color:var(--text-muted)] mb-3">
                          Save this key now - it will not be shown again.
                        </p>
                        <div className="flex items-center gap-2">
                          <code className="flex-1 px-3 py-2 bg-[color:var(--surface-1)] rounded-lg text-xs text-emerald-300 font-mono break-all">
                            {generatedKey}
                          </code>
                          <button
                            onClick={() => handleCopyKey(generatedKey)}
                            className="p-2 bg-[color:var(--surface-hover)] hover:bg-[color:var(--surface-hover)] rounded-lg transition-colors"
                          >
                            {copiedKey ? (
                              <Check size={16} className="text-emerald-400" />
                            ) : (
                              <Copy size={16} className="text-[color:var(--text-muted)]" />
                            )}
                          </button>
                        </div>
                      </div>
                      <button
                        onClick={() => setGeneratedKey(null)}
                        className="text-[color:var(--text-muted)] hover:text-[color:var(--foreground)]"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Generate New Key */}
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-medium text-[color:var(--foreground)]">API Keys</h4>
                  <p className="text-xs text-[color:var(--text-muted)]">Use API keys to authenticate marketplace requests</p>
                </div>
                <button
                  onClick={() => setShowNewKeyModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  <Plus size={16} />
                  Generate Key
                </button>
              </div>

              {keyError && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  {keyError}
                </div>
              )}

              {/* API Keys List */}
              {loadingKeys ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={24} className="text-violet-500 animate-spin" />
                </div>
              ) : apiKeys.length === 0 ? (
                <div className="text-center py-8">
                  <Key size={32} className="text-[color:var(--text-muted)] mx-auto mb-3" />
                  <p className="text-sm text-[color:var(--text-muted)]">No API keys generated yet</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {apiKeys.filter(k => k.isActive).map((key) => (
                    <div
                      key={key.id}
                      className="flex items-center justify-between p-4 rounded-lg bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)]"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center">
                          <Key size={16} className="text-violet-400" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-[color:var(--foreground)]">{key.name}</span>
                            <code className="px-2 py-0.5 bg-[color:var(--surface-hover)] rounded text-xs text-[color:var(--text-muted)] font-mono">
                              {key.keyId}
                            </code>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-[color:var(--text-muted)] mt-1">
                            <span>Created {new Date(key.createdAt).toLocaleDateString()}</span>
                            {key.lastUsedAt && (
                              <span>Last used {new Date(key.lastUsedAt).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => handleRevokeKey(key.keyId)}
                        disabled={revokingKeyId === key.keyId}
                        className="px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {revokingKeyId === key.keyId ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          'Revoke'
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* New Key Modal */}
              <AnimatePresence>
                {showNewKeyModal && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-[60] flex items-center justify-center p-4"
                  >
                    <div className="absolute inset-0 bg-[color:var(--overlay-soft)]" onClick={() => setShowNewKeyModal(false)} />
                    <motion.div
                      initial={{ scale: 0.95 }}
                      animate={{ scale: 1 }}
                      exit={{ scale: 0.95 }}
                      className="relative w-full max-w-md bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-xl p-6 shadow-xl"
                    >
                      <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4">Generate API Key</h3>
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Key Name</label>
                        <input
                          type="text"
                          value={newKeyName}
                          onChange={(e) => setNewKeyName(e.target.value)}
                          placeholder="e.g., Production, Development"
                          className="w-full px-4 py-2 bg-[color:var(--surface-hover)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500"
                        />
                      </div>
                      <div className="flex gap-3">
                        <button
                          onClick={() => setShowNewKeyModal(false)}
                          className="flex-1 px-4 py-2 bg-[color:var(--surface-hover)] hover:bg-[color:var(--surface-hover)] text-[color:var(--foreground)] rounded-lg transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleGenerateKey}
                          disabled={generatingKey}
                          className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-colors disabled:opacity-50"
                        >
                          {generatingKey ? (
                            <>
                              <Loader2 size={16} className="animate-spin" />
                              Generating...
                            </>
                          ) : (
                            <>
                              <RefreshCw size={16} />
                              Generate
                            </>
                          )}
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-[color:var(--surface-hover)] hover:bg-[color:var(--surface-hover)] text-[color:var(--foreground)] rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// Edit Agent Modal
function EditAgentModal({
  agent,
  onClose,
  onSave,
  getAuthHeaders,
}: {
  agent: Agent;
  onClose: () => void;
  onSave: (updated: Agent) => void;
  getAuthHeaders: () => Promise<HeadersInit>;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    title: agent.title,
    description: agent.description,
    category: agent.category || '',
    walletAddress: agent.walletAddress || '',
    apiEndpoint: agent.apiEndpoint || '',
    webhookUrl: agent.webhookUrl || '',
    minFeeUsdc: agent.minFeeUsdc,
    capabilities: parseCapabilities(agent.capabilities),
  });

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`/api/agents/${agent.id}`, {
        method: 'PATCH',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: formData.title,
          description: formData.description,
          category: formData.category || undefined,
          walletAddress: formData.walletAddress,
          apiEndpoint: formData.apiEndpoint,
          webhookUrl: formData.webhookUrl || undefined,
          minFeeUsdc: formData.minFeeUsdc,
          capabilities: JSON.stringify(formData.capabilities),
        }),
      });

      if (res.ok) {
        onSave({
          ...agent,
          title: formData.title,
          description: formData.description,
          category: formData.category || null,
          walletAddress: formData.walletAddress,
          apiEndpoint: formData.apiEndpoint || null,
          webhookUrl: formData.webhookUrl || null,
          minFeeUsdc: formData.minFeeUsdc,
          capabilities: JSON.stringify(formData.capabilities),
        });
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to update agent');
      }
    } catch (err) {
      console.error('Update error:', err);
      setError('Failed to update agent');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[color:var(--overlay-strong)] backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative w-full max-w-2xl bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[color:var(--border-subtle)]">
          <div>
            <h2 className="text-xl font-bold text-[color:var(--foreground)]">Edit Agent</h2>
            <p className="text-sm text-[color:var(--text-muted)]">Update your agent configuration</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[color:var(--surface-1)] rounded-lg">
            <X size={20} className="text-[color:var(--text-muted)]" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Agent Name</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
              rows={3}
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Category</label>
            <select
              value={formData.category}
              onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
            >
              <option value="">Select category</option>
              {AGENT_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">
              <span className="flex items-center gap-2">
                <Globe size={16} />
                API Endpoint
              </span>
            </label>
            <input
              type="url"
              value={formData.apiEndpoint}
              onChange={(e) => setFormData(prev => ({ ...prev, apiEndpoint: e.target.value }))}
              placeholder="https://your-agent.com/api/execute"
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] font-mono focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Webhook URL</label>
            <input
              type="url"
              value={formData.webhookUrl}
              onChange={(e) => setFormData(prev => ({ ...prev, webhookUrl: e.target.value }))}
              placeholder="https://your-agent.com/webhook"
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] font-mono focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">
              <span className="flex items-center gap-2">
                <Wallet size={16} />
                Wallet Address
              </span>
            </label>
            <input
              type="text"
              value={formData.walletAddress}
              onChange={(e) => setFormData(prev => ({ ...prev, walletAddress: e.target.value }))}
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] font-mono focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Minimum Fee (USDC)</label>
            <input
              type="number"
              step="0.01"
              value={formData.minFeeUsdc}
              onChange={(e) => setFormData(prev => ({ ...prev, minFeeUsdc: parseFloat(e.target.value) || 0 }))}
              className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Capabilities</label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(CAPABILITY_DETAILS).map(([cap, { label }]) => (
                <button
                  key={cap}
                  type="button"
                  onClick={() => {
                    setFormData(prev => ({
                      ...prev,
                      capabilities: prev.capabilities.includes(cap)
                        ? prev.capabilities.filter((c) => c !== cap)
                        : [...prev.capabilities, cap],
                    }));
                  }}
                  className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                    formData.capabilities.includes(cap)
                      ? "bg-violet-500/20 border-violet-500 text-violet-300"
                      : "bg-[color:var(--surface-1)] border-[color:var(--border-subtle)] text-[color:var(--text-muted)] hover:border-[color:var(--border-subtle)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-[color:var(--text-muted)] hover:text-[color:var(--foreground)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 px-6 py-2 bg-violet-600 hover:bg-violet-500 text-white font-medium rounded-lg transition-all disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
