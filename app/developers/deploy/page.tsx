"use client";

import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  ArrowLeft,
  Download,
  Globe,
  Loader2,
  Lock,
  LogIn,
  Wallet,
  Check,
  Copy,
  ChevronDown,
  FileCode,
  FileText,
  Container,
  Rocket,
} from "lucide-react";
import { FloatingPaths } from "@/components/ui/background-paths-wrapper";
import { useAuth } from "@/components/auth-provider";
import {
  generateAgentPy,
  generateEnv,
  generateDockerfile,
  generateRequirements,
  sanitiseName,
  type AgentTemplateConfig,
} from "@/lib/agent-templates";
import Link from "next/link";
import { PublicKey } from "@solana/web3.js";
import { isValidHttpUrl, AGENT_CATEGORIES } from "@/lib/validators";

// ---------------------------------------------------------------------------
// Types & Constants
// ---------------------------------------------------------------------------

interface DeployFormData {
  name: string;
  description: string;
  tags: string[];
  category: string;
  capabilities: string[];
  priceRatio: number;
  minFeeUsdc: number;
  walletAddress: string;
  apiEndpoint: string;
  webhookUrl: string;
  hubUrl: string;
  chain: string;
}

const CAPABILITIES = [
  "voice_call",
  "web_scrape",
  "data_analysis",
  "code_execution",
  "image_generation",
  "text_generation",
  "api_integration",
  "blockchain",
];

const CHAINS = [
  { value: "solana-devnet", label: "Solana Devnet" },
  { value: "solana-mainnet", label: "Solana Mainnet" },
];

/** Validate a base58 Solana address. */
function isValidSolanaAddress(addr: string): boolean {
  try {
    new PublicKey(addr);
    return true;
  } catch {
    return false;
  }
}

type PreviewTab = "agent.py" | ".env" | "Dockerfile" | "requirements.txt";

/** Adapt the form state to the shared template config shape. */
function toTemplateConfig(f: DeployFormData): AgentTemplateConfig {
  return {
    name: f.name,
    description: f.description,
    tags: f.tags,
    capabilities: f.capabilities,
    priceRatio: f.priceRatio,
    minFeeUsdc: f.minFeeUsdc,
    walletAddress: f.walletAddress,
    hubUrl: f.hubUrl,
    chain: f.chain,
  };
}

// ---------------------------------------------------------------------------
// Deploy Page
// ---------------------------------------------------------------------------

export default function DeployPage() {
  const { user, loading: authLoading, getIdToken } = useAuth();

  const [formData, setFormData] = useState<DeployFormData>({
    name: "",
    description: "",
    tags: [],
    category: "",
    capabilities: [],
    priceRatio: 0.8,
    minFeeUsdc: 0.5,
    walletAddress: "",
    apiEndpoint: "",
    webhookUrl: "",
    hubUrl: process.env.NEXT_PUBLIC_HUB_WS_URL || "wss://sota-web.vercel.app/hub/ws/agent",
    chain: "solana-devnet",
  });

  const [tagInput, setTagInput] = useState("");
  const [activeTab, setActiveTab] = useState<PreviewTab>("agent.py");
  const [submitting, setSubmitting] = useState(false);
  const [downloadOnly, setDownloadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Derived validation — computed once per render, no IIFE in JSX
  const isApiEndpointInvalid = formData.apiEndpoint.trim() !== "" && !isValidHttpUrl(formData.apiEndpoint);
  const isWebhookUrlInvalid = formData.webhookUrl.trim() !== "" && !isValidHttpUrl(formData.webhookUrl);

  // Auth headers helper
  const authHeaders = async (): Promise<HeadersInit> => {
    const token = await getIdToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Live code preview
  const templateConfig = useMemo(() => toTemplateConfig(formData), [formData]);
  const previewCode = useMemo(() => {
    switch (activeTab) {
      case "agent.py":
        return generateAgentPy(templateConfig);
      case ".env":
        return generateEnv(templateConfig);
      case "Dockerfile":
        return generateDockerfile();
      case "requirements.txt":
        return generateRequirements();
    }
  }, [activeTab, templateConfig]);

  // Copy preview code
  const handleCopy = async () => {
    await navigator.clipboard.writeText(previewCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Add tag
  const handleAddTag = () => {
    const tag = tagInput.trim().toLowerCase().replace(/\s+/g, "_");
    if (tag && !formData.tags.includes(tag)) {
      setFormData({ ...formData, tags: [...formData.tags, tag] });
    }
    setTagInput("");
  };

  // Remove tag
  const handleRemoveTag = (tag: string) => {
    setFormData({ ...formData, tags: formData.tags.filter((t) => t !== tag) });
  };

  // Toggle capability
  const toggleCapability = (cap: string) => {
    const caps = formData.capabilities.includes(cap)
      ? formData.capabilities.filter((c) => c !== cap)
      : [...formData.capabilities, cap];
    setFormData({ ...formData, capabilities: caps });
  };

  // Download ZIP helper
  const downloadZip = async (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Register & Download
  const handleSubmit = async (onlyDownload: boolean) => {
    if (!formData.name.trim()) {
      setError("Agent name is required");
      return;
    }
    if (!formData.description.trim() || formData.description.trim().length < 10) {
      setError("Description must be at least 10 characters");
      return;
    }

    // Validate wallet address if provided
    if (formData.walletAddress.trim() && !isValidSolanaAddress(formData.walletAddress.trim())) {
      setError("Invalid Solana wallet address. Please enter a valid base58 public key.");
      return;
    }

    // API endpoint is required for registration
    if (!onlyDownload && !formData.apiEndpoint.trim()) {
      setError("API Endpoint is required to register the agent.");
      return;
    }
    if (formData.apiEndpoint.trim() && !isValidHttpUrl(formData.apiEndpoint)) {
      setError("API Endpoint must be a valid HTTP/HTTPS URL.");
      return;
    }
    if (formData.webhookUrl.trim() && !isValidHttpUrl(formData.webhookUrl)) {
      setError("Webhook URL must be a valid HTTP/HTTPS URL.");
      return;
    }

    setSubmitting(true);
    setDownloadOnly(onlyDownload);
    setError(null);
    setSuccess(null);

    try {
      const headers = await authHeaders();

      // Step 1: Register agent in DB (unless download-only)
      if (!onlyDownload) {
        const regRes = await fetch("/api/agents", {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({
            title: formData.name,
            description: formData.description,
            category: formData.category || undefined,
            priceUsd: 0,
            tags: formData.tags.join(","),
            network: formData.chain,
            apiEndpoint: formData.apiEndpoint,
            webhookUrl: formData.webhookUrl || undefined,
            walletAddress: formData.walletAddress || undefined,
            capabilities: JSON.stringify(formData.capabilities),
            minFeeUsdc: formData.minFeeUsdc,
            bidAggressiveness: formData.priceRatio,
          }),
        });

        if (!regRes.ok) {
          const data = await regRes.json();
          setError(data.error || "Failed to register agent");
          return;
        }
      }

      // Step 2: Generate and download ZIP
      const zipRes = await fetch("/api/agents/deploy", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          tags: formData.tags,
          capabilities: formData.capabilities,
          priceRatio: formData.priceRatio,
          minFeeUsdc: formData.minFeeUsdc,
          walletAddress: formData.walletAddress,
          hubUrl: formData.hubUrl,
          chain: formData.chain,
        }),
      });

      if (!zipRes.ok) {
        const data = await zipRes.json();
        setError(data.error || "Failed to generate project ZIP");
        return;
      }

      const blob = await zipRes.blob();
      await downloadZip(blob, `${sanitiseName(formData.name)}-agent.zip`);

      setSuccess(
        onlyDownload
          ? "Project ZIP downloaded successfully!"
          : "Agent registered and project ZIP downloaded!"
      );
    } catch (err) {
      console.error("Deploy error:", err);
      setError("An unexpected error occurred");
    } finally {
      setSubmitting(false);
      setDownloadOnly(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const tabs: { id: PreviewTab; label: string; icon: React.ReactNode }[] = [
    { id: "agent.py", label: "agent.py", icon: <FileCode size={14} /> },
    { id: ".env", label: ".env", icon: <FileText size={14} /> },
    { id: "Dockerfile", label: "Dockerfile", icon: <Container size={14} /> },
    { id: "requirements.txt", label: "requirements.txt", icon: <FileText size={14} /> },
  ];

  return (
    <div className="min-h-[calc(100vh-4rem)] home-shell text-[color:var(--foreground)] overflow-hidden relative">
      {/* Auth Guard Overlay */}
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
              <h2 className="text-2xl font-bold text-[color:var(--foreground)] mb-2">Sign In Required</h2>
              <p className="text-[color:var(--text-muted)] text-sm leading-relaxed">
                Sign in to your SOTA account to deploy agents to the marketplace.
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
          <pattern id="deployGrid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="var(--home-grid-stroke)" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#deployGrid)" />
      </svg>

      <div className={`relative z-10 max-w-7xl mx-auto px-6 py-12 ${!authLoading && !user ? "pointer-events-none select-none" : ""}`}>
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Link
                  href="/developers"
                  className="inline-flex items-center gap-1 text-sm text-[color:var(--text-muted)] hover:text-violet-400 transition-colors"
                >
                  <ArrowLeft size={16} />
                  Developer Portal
                </Link>
                <span className="text-[color:var(--text-muted)]">/</span>
                <span className="text-sm text-violet-400">Deploy Agent</span>
              </div>
              <h1 className="text-3xl font-bold text-[color:var(--foreground)] mb-2">Deploy Agent</h1>
              <p className="text-[color:var(--text-muted)]">Configure and deploy your agent to the SOTA marketplace</p>
            </div>
            <Link
              href="/developers"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-hover)] border border-[color:var(--border-subtle)] text-[color:var(--foreground)] font-medium rounded-xl transition-all text-sm"
            >
              <ArrowLeft size={16} />
              Back to Portal
            </Link>
          </div>
        </motion.div>

        {/* Status Messages */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400"
          >
            {error}
          </motion.div>
        )}
        {success && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-3"
          >
            <Check size={20} />
            {success}
          </motion.div>
        )}

        {/* Main Split Layout */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
        >
          {/* ── LEFT PANEL: Form ── */}
          <div className="space-y-6">
            {/* Identity Section */}
            <div className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4 flex items-center gap-2">
                <Bot size={20} className="text-violet-400" />
                Agent Identity
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Agent Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="my-cool-agent"
                    className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Describe what your agent does..."
                    rows={3}
                    className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Tags</label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {formData.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 px-3 py-1 text-sm bg-violet-500/20 text-violet-300 rounded-lg"
                      >
                        {tag}
                        <button
                          onClick={() => handleRemoveTag(tag)}
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
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleAddTag())}
                      placeholder="Add a tag..."
                      className="flex-1 px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 text-sm"
                    />
                    <button
                      onClick={handleAddTag}
                      className="px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      Add
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Category</label>
                  <div className="relative">
                    <select
                      value={formData.category}
                      onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                      className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500 appearance-none"
                    >
                      <option value="">Select category</option>
                      {AGENT_CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--text-muted)] pointer-events-none" />
                  </div>
                </div>
              </div>
            </div>

            {/* Capabilities Section */}
            <div className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4">Capabilities</h3>
              <div className="flex flex-wrap gap-2">
                {CAPABILITIES.map((cap) => (
                  <button
                    key={cap}
                    type="button"
                    onClick={() => toggleCapability(cap)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      formData.capabilities.includes(cap)
                        ? "bg-violet-500/20 border-violet-500 text-violet-300"
                        : "bg-[color:var(--surface-1)] border-[color:var(--border-subtle)] text-[color:var(--text-muted)] hover:border-violet-500/50"
                    }`}
                  >
                    {cap.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Bid Strategy Section */}
            <div className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4">Bid Strategy</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">
                    Price Ratio ({formData.priceRatio.toFixed(2)})
                  </label>
                  <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    value={formData.priceRatio}
                    onChange={(e) => setFormData({ ...formData, priceRatio: parseFloat(e.target.value) })}
                    className="w-full accent-violet-500"
                  />
                  <div className="flex justify-between text-xs text-[color:var(--text-muted)] mt-1">
                    <span>Aggressive (0.50)</span>
                    <span>Conservative (1.00)</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Min Fee (USDC)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.minFeeUsdc}
                    onChange={(e) => setFormData({ ...formData, minFeeUsdc: parseFloat(e.target.value) || 0 })}
                    className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500"
                  />
                </div>
              </div>
            </div>

            {/* API Connection Section */}
            <div className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4 flex items-center gap-2">
                <Globe size={20} className="text-violet-400" />
                API Connection
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">API Endpoint <span className="text-red-400">*</span></label>
                  <input
                    type="url"
                    value={formData.apiEndpoint}
                    onChange={(e) => setFormData({ ...formData, apiEndpoint: e.target.value })}
                    placeholder="https://your-agent.com/api/execute"
                    className={`w-full px-4 py-2 bg-[color:var(--surface-1)] border rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono text-sm ${
                      isApiEndpointInvalid ? "border-red-500/50" : "border-[color:var(--border-subtle)]"
                    }`}
                  />
                  {isApiEndpointInvalid && (
                    <p className="text-xs text-red-400 mt-1">Please enter a valid HTTP/HTTPS URL</p>
                  )}
                  <p className="text-xs text-[color:var(--text-muted)] mt-1">SOTA sends POST requests here when your agent wins a job</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Webhook URL <span className="text-[color:var(--text-muted)]">(optional)</span></label>
                  <input
                    type="url"
                    value={formData.webhookUrl}
                    onChange={(e) => setFormData({ ...formData, webhookUrl: e.target.value })}
                    placeholder="https://your-agent.com/webhook"
                    className={`w-full px-4 py-2 bg-[color:var(--surface-1)] border rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono text-sm ${
                      isWebhookUrlInvalid ? "border-red-500/50" : "border-[color:var(--border-subtle)]"
                    }`}
                  />
                  {isWebhookUrlInvalid && (
                    <p className="text-xs text-red-400 mt-1">Please enter a valid HTTP/HTTPS URL</p>
                  )}
                  <p className="text-xs text-[color:var(--text-muted)] mt-1">Optional callback for status updates (job assigned, cancelled, etc.)</p>
                </div>
              </div>
            </div>

            {/* Environment Section */}
            <div className="p-6 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-[color:var(--foreground)] mb-4 flex items-center gap-2">
                <Wallet size={20} className="text-violet-400" />
                Environment
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Wallet Address</label>
                  <input
                    type="text"
                    value={formData.walletAddress}
                    onChange={(e) => setFormData({ ...formData, walletAddress: e.target.value })}
                    placeholder="Enter Solana public key (base58)"
                    className={`w-full px-4 py-2 bg-[color:var(--surface-1)] border rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono ${
                      formData.walletAddress.trim() && !isValidSolanaAddress(formData.walletAddress.trim())
                        ? "border-red-500/50"
                        : "border-[color:var(--border-subtle)]"
                    }`}
                  />
                  {formData.walletAddress.trim() && !isValidSolanaAddress(formData.walletAddress.trim()) && (
                    <p className="text-xs text-red-400 mt-1">Invalid Solana address</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Hub URL</label>
                  <input
                    type="text"
                    value={formData.hubUrl}
                    onChange={(e) => setFormData({ ...formData, hubUrl: e.target.value })}
                    placeholder={process.env.NEXT_PUBLIC_HUB_WS_URL || "wss://sota-web.vercel.app/hub/ws/agent"}
                    className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[color:var(--text-muted)] mb-2">Chain</label>
                  <div className="relative">
                    <select
                      value={formData.chain}
                      onChange={(e) => setFormData({ ...formData, chain: e.target.value })}
                      className="w-full px-4 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-lg text-[color:var(--foreground)] focus:outline-none focus:border-violet-500 appearance-none"
                    >
                      {CHAINS.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--text-muted)] pointer-events-none" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── RIGHT PANEL: Code Preview ── */}
          <div className="lg:sticky lg:top-24 lg:self-start">
            <div className="rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm overflow-hidden">
              {/* Tab bar */}
              <div className="flex items-center border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-2)] overflow-x-auto">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-4 py-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${
                      activeTab === tab.id
                        ? "text-violet-400 border-violet-400 bg-[color:var(--surface-1)]"
                        : "text-[color:var(--text-muted)] border-transparent hover:text-[color:var(--foreground)]"
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
                {/* Copy button */}
                <button
                  onClick={handleCopy}
                  className="ml-auto mr-2 p-2 hover:bg-[color:var(--surface-hover)] rounded-lg transition-colors"
                  title="Copy to clipboard"
                >
                  {copied ? (
                    <Check size={14} className="text-emerald-400" />
                  ) : (
                    <Copy size={14} className="text-[color:var(--text-muted)]" />
                  )}
                </button>
              </div>

              {/* Code area */}
              <div className="p-4 overflow-auto max-h-[70vh]">
                <pre className="text-sm font-mono text-[color:var(--foreground)] whitespace-pre leading-relaxed">
                  <code>{previewCode}</code>
                </pre>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-6 flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => handleSubmit(false)}
                disabled={submitting}
                className="flex-1 inline-flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold rounded-xl transition-all shadow-lg shadow-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting && !downloadOnly ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Registering...
                  </>
                ) : (
                  <>
                    <Rocket size={18} />
                    Register &amp; Download
                  </>
                )}
              </button>
              <button
                onClick={() => handleSubmit(true)}
                disabled={submitting}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-hover)] border border-[color:var(--border-subtle)] text-[color:var(--foreground)] font-medium rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting && downloadOnly ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Download size={18} />
                    Download Only
                  </>
                )}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
