"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useWallet, useConnection } from "@solana/wallet-adapter-react";
import {
  PublicKey,
  Transaction,
  SystemProgram,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import { useConversation } from "@elevenlabs/react";
import { motion, AnimatePresence } from "motion/react";
import { X, Plus, MessageSquare, Send } from "lucide-react";
import AgentOrb from "./AgentOrb";
import { useToast } from "./ToastProvider";
import StripePayment from "./StripePayment";
import { explorerLink } from "@/src/solanaConfig";
import { useAuth } from "@/src/context/AuthContext";

/* ── Config ── */
const BUTLER_URL =
  process.env.NEXT_PUBLIC_BUTLER_API_URL || "http://localhost:3001/api/v1";

/* ── Types ── */
interface TranscriptLine {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ConvSummary {
  id: string;
  title: string | null;
}

type OrbStatus = "idle" | "listening" | "thinking" | "speaking";

/** SSR-safe unique ID (avoids Webpack resolving Node crypto module) */
function newSessionId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  // Fallback for SSR / older runtimes
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/* ── Bid Progress Bar Component (Glassmorphism Style) ── */
function BidProgressBar({ duration, onComplete }: { duration: number; onComplete?: () => void }) {
  const [progress, setProgress] = useState(0);
  const [timeLeft, setTimeLeft] = useState(duration);
  const startTimeRef = useRef(Date.now());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    startTimeRef.current = Date.now();
    completedRef.current = false;

    intervalRef.current = setInterval(() => {
      const elapsed = (Date.now() - startTimeRef.current) / 1000;
      const pct = Math.min((elapsed / duration) * 100, 100);
      setProgress(pct);
      setTimeLeft(Math.max(duration - elapsed, 0));

      if (pct >= 100 && !completedRef.current) {
        completedRef.current = true;
        if (intervalRef.current) clearInterval(intervalRef.current);
        onCompleteRef.current?.();
      }
    }, 100);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []); // Empty deps -- mount once only, immune to parent re-renders

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10 }}
      className="transcript-msg assistant"
    >
      <span className="transcript-msg-role">Butler</span>
      <p className="transcript-msg-text">
        Let me find the best specialist for your request...
      </p>
      <div className="mt-2 w-full">
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ background: 'rgba(255, 255, 255, 0.08)' }}
        >
          <motion.div
            className="h-full rounded-full"
            style={{ background: 'linear-gradient(90deg, #6366f1, #a78bfa, #c084fc)' }}
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3, ease: "linear" }}
          />
        </div>
        <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted, #64748b)' }}>
          {Math.ceil(timeLeft)}s remaining
        </p>
      </div>
    </motion.div>
  );
}

/* ── Task Execution Progress (styled as normal butler message) ── */
function TaskExecutionProgress({ message }: { message: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10 }}
      className="transcript-msg assistant"
    >
      <span className="transcript-msg-role">Butler</span>
      <p className="transcript-msg-text">
        {message}
        <span className="inline-flex ml-2 gap-0.5 align-middle">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="inline-block w-1 h-1 rounded-full bg-current opacity-50"
              animate={{ opacity: [0.3, 0.8, 0.3] }}
              transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
            />
          ))}
        </span>
      </p>
    </motion.div>
  );
}

/* ─────────────────────────────────────────────────── */
interface ChatScreenProps {
  sidebarOpen?: boolean;
  onSidebarOpenChange?: (open: boolean) => void;
}

export default function ChatScreen({ sidebarOpen: sidebarOpenProp, onSidebarOpenChange }: ChatScreenProps) {
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [orbStatus, setOrbStatus] = useState<OrbStatus>("idle");
  const [sidebarOpenLocal, setSidebarOpenLocal] = useState(false);

  // Use prop-controlled sidebar if provided, otherwise local state
  const sidebarOpen = sidebarOpenProp ?? sidebarOpenLocal;
  const setSidebarOpen = onSidebarOpenChange ?? setSidebarOpenLocal;
  const [sessionId, setSessionId] = useState(newSessionId);
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [bidProgress, setBidProgress] = useState<{ active: boolean; duration: number } | null>(null);
  const [taskExecution, setTaskExecution] = useState<{ active: boolean; message: string } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bidActiveRef = useRef(false);

  const { user } = useAuth();
  const { publicKey, sendTransaction, connected } = useWallet();
  const { connection } = useConnection();
  const address = publicKey?.toBase58() ?? null;
  const { showToast } = useToast();
  const [textInput, setTextInput] = useState("");
  const [stripePayment, setStripePayment] = useState<{
    jobId: number;
    amount: number;
    agentAddress: string;
    boardJobId?: string;
    userId?: number;
  } | null>(null);

  // Refs to avoid stale closures in addLine callback
  const sessionIdRef = useRef(sessionId);
  const addressRef = useRef(address);
  const userIdRef = useRef(user?.id ?? null);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
  useEffect(() => { addressRef.current = address; }, [address]);
  useEffect(() => { userIdRef.current = user?.id ?? null; }, [user?.id]);
  const [isSending, setIsSending] = useState(false);

  // Safety net: catch unhandled ElevenLabs SDK errors that would crash the page
  useEffect(() => {
    const handler = (event: PromiseRejectionEvent) => {
      const msg = String(event.reason?.message ?? event.reason ?? "");
      if (msg.includes("error_event") || msg.includes("error_type")) {
        event.preventDefault();
        console.warn("[ElevenLabs safety net] Suppressed unhandled rejection:", event.reason);
        setOrbStatus("idle");
      }
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  // Auto-scroll transcript to bottom on new messages or progress bar or task execution
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [transcript, bidProgress, taskExecution]);

  // Load conversations when sidebar opens (filtered by userId or wallet)
  useEffect(() => {
    if (!sidebarOpen) return;
    const query = user?.id ? `userId=${user.id}` : address ? `wallet=${address}` : null;
    if (!query) return;
    fetch(`/api/chat?${query}`)
      .then((r) => r.json())
      .then((sessions: any[]) => {
        if (Array.isArray(sessions))
          setConversations(sessions.map((s: any) => ({ id: s.id, title: s.title })));
      })
      .catch(() => {});
  }, [sidebarOpen, user?.id, address]);

  const addLine = useCallback((role: TranscriptLine["role"], content: string) => {
    setTranscript((p) => [
      ...p,
      { id: crypto.randomUUID(), role, content, timestamp: new Date() },
    ]);
    // Persist to database via API (fire-and-forget)
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionId: sessionIdRef.current,
        role,
        text: content,
        wallet: addressRef.current,
        userId: userIdRef.current,
      }),
    }).catch(() => {});
  }, []);

  /* ── Helper: trigger Stripe payment UI for a job result ── */
  const triggerStripePayment = useCallback((jobResult: any) => {
    const escrowInfo = jobResult?.escrow;
    if (!escrowInfo?.needs_user_funding) return;

    const budgetUsdc = escrowInfo.budget_usdc || escrowInfo.budget_usd || 0.02;
    const jobId = jobResult.on_chain_job_id || jobResult.job_id;
    const boardJobId = jobResult.job_id;
    const rawWinnerAddr = jobResult.winning_bid?.address;

    // Validate as base58 Solana address; fall back to connected wallet or system program
    let winnerAddr: string;
    try {
      if (rawWinnerAddr) {
        new PublicKey(rawWinnerAddr); // throws if invalid
        winnerAddr = rawWinnerAddr;
      } else {
        winnerAddr = address || SystemProgram.programId.toBase58();
      }
    } catch {
      winnerAddr = address || SystemProgram.programId.toBase58();
    }

    addLine("assistant", `Payment of ${budgetUsdc.toFixed(2)} USDC needed. Please complete payment below.`);
    setStripePayment({ jobId, amount: budgetUsdc, agentAddress: winnerAddr, boardJobId, userId: user?.id });
  }, [address, addLine, user?.id]);

  /* ── Post job JSON to backend marketplace ── */
  const postJobToMarketplace = useCallback(async (jobData: Record<string, any>) => {
    if (bidActiveRef.current) return "Bid already in progress";
    bidActiveRef.current = true;
    console.log("Posting job to marketplace:", jobData);
    // Normalize: if theme_technology_focus is a string, split to array
    if (typeof jobData.theme_technology_focus === "string") {
      jobData.theme_technology_focus = jobData.theme_technology_focus
        .split(/[/,]+/)
        .map((s: string) => s.trim())
        .filter(Boolean);
    }
    // Attach wallet address
    if (address) jobData.wallet_address = address;
    if (!jobData.budget_usd) {
      jobData.budget_usd = 1.0;
    }

    // Show progress bar during bid collection (15 seconds)
    setBidProgress({ active: true, duration: 15 });

    try {
      const res = await fetch(`${BUTLER_URL}/marketplace/post`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(jobData),
      });

      if (!res.ok) throw new Error(`Post failed: ${res.statusText}`);
      const data = await res.json();

      // ── Parse result JSON to extract escrow info ──
      let jobResult: any = null;
      try {
        jobResult = typeof data.message === "string" ? JSON.parse(data.message) : data.message;
      } catch {
        // message is not JSON
      }

      // ── Surface job failure to the user ──
      if (jobResult && jobResult.success === false) {
        const reason = jobResult.reason || "No specialists available";
        showToast(reason, "warning");
        return `Job failed: ${reason}`;
      }

      // ── Fund escrow via Stripe Apple Pay / card ──
      if (jobResult?.escrow?.needs_user_funding) {
        triggerStripePayment(jobResult);
        const budgetUsdc = jobResult.escrow.budget_usdc || jobResult.escrow.budget_usd || 0.02;
        return `Job posted — awaiting payment of ${budgetUsdc.toFixed(2)} USDC`;
      }

      showToast("Job posted to marketplace!", "success");
      return data.message || "Job posted successfully";
    } catch (err: any) {
      setBidProgress(null);
      bidActiveRef.current = false;
      setTaskExecution(null);
      console.error("Marketplace post error:", err);
      showToast("Failed to post job", "error");
      return `Failed to post job: ${err.message}`;
    }
  }, [address, showToast, triggerStripePayment]);

  /* ── Try to extract & auto-post JSON from assistant text ── */
  const interceptJsonJob = useCallback(async (text: string) => {
    const jsonMatch = text.match(/\{[\s\S]*"task"\s*:\s*"[^"]+"[\s\S]*\}/);
    if (!jsonMatch) return;
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      if (parsed.task) {
        await postJobToMarketplace(parsed);
      }
    } catch {
      // Not valid JSON, ignore
    }
  }, [postJobToMarketplace]);

  /* ── ElevenLabs ── */
  const conversation = useConversation({
    onConnect: () => {
      setOrbStatus("listening");
      showToast("Connected – start speaking", "success", 2000);
    },
    onDisconnect: () => {
      // Show feedback only on unexpected drops (user-initiated ends already have context)
      if (orbStatus === "listening" || orbStatus === "speaking") {
        showToast("Voice session ended. Tap the orb to reconnect.", "info");
      }
      setOrbStatus("idle");
    },
    onMessage: (msg: { message: string; source: string }) => {
      const role = msg.source === "user" ? "user" : "assistant";
      addLine(role as "user" | "assistant", msg.message);
      if (role === "assistant") {
        setOrbStatus("speaking");
        interceptJsonJob(msg.message);
      }
    },
    onModeChange: ({ mode }: { mode: string }) => {
      if (mode === "listening") setOrbStatus("listening");
      else if (mode === "speaking") setOrbStatus("speaking");
    },
    onError: (err: unknown, details?: unknown) => {
      console.error("ElevenLabs error:", err, "Details:", details);
      showToast("Voice connection error", "error");
      setOrbStatus("idle");
    },
    onUnhandledClientToolCall: (toolCall: any) => {
      console.error("UNHANDLED client tool call:", toolCall);
      showToast(`Unhandled tool: ${toolCall?.tool_name || toolCall?.name || "unknown"}`, "warning");
    },
    onDebug: (info: unknown) => {
      console.log("ElevenLabs debug:", info);
    },
  });

  const toggleVoice = async () => {
    if (orbStatus === "listening" || orbStatus === "speaking") {
      try {
        await conversation.endSession();
      } catch (err) {
        console.error("Failed to end voice session:", err);
      }
      setOrbStatus("idle");
    } else {
      // Mic permission — separate catch so errors are reported accurately
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        showToast("Microphone access denied", "warning");
        setOrbStatus("idle");
        return;
      }

      // Token fetch + session start
      setOrbStatus("thinking");
      try {
        const tokenRes = await fetch("/api/elevenlabs/token");
        if (!tokenRes.ok) throw new Error("Failed to fetch conversation token");
        const { token } = await tokenRes.json();
        if (!token) throw new Error("No conversation token received");

        await conversation.startSession({
          conversationToken: token,
          connectionType: "webrtc",
          clientTools: {
            /* ── Post job to marketplace ── */
            post_job: async (params: Record<string, any>) => {
              let jobData: Record<string, any>;
              if (typeof params.job_data === "string") {
                try {
                  jobData = JSON.parse(params.job_data);
                } catch {
                  return "Error: Invalid job data format";
                }
              } else if (params.job_data && typeof params.job_data === "object") {
                jobData = params.job_data;
              } else {
                jobData = params;
              }
              const result = await postJobToMarketplace(jobData);
              return result;
            },

            /* ── Bridge to Butler backend ── */
            query_butler: async ({ query }: { query: string }) => {
              try {
                const res = await fetch(`${BUTLER_URL}/chat`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ query, timestamp: Date.now() }),
                });
                if (!res.ok) throw new Error(`Butler error: ${res.statusText}`);
                const data = await res.json();

                // If Butler posted a job, trigger Stripe payment
                if (data.job_posted) {
                  triggerStripePayment(data.job_posted);
                }

                return data.response || data.message || "Request processed";
              } catch (err: any) {
                console.error("Butler Agent error:", err);
                return `I had trouble connecting to the butler agent. ${err.message}`;
              }
            },

            /* ── Marketplace job listings ── */
            get_job_listings: async ({ filters }: { filters?: any }) => {
              try {
                const res = await fetch(`${BUTLER_URL}/marketplace/jobs`);
                const data = await res.json();
                if (data.jobs && data.jobs.length > 0) {
                  const summary = data.jobs
                    .map(
                      (j: any) =>
                        `Job ${j.job_id}: ${j.description} (${j.status}, budget: ${j.budget_usdc ?? 0} USDC)`
                    )
                    .join("; ");
                  return `Found ${data.total} jobs on the marketplace: ${summary}`;
                }
                return "No jobs currently on the marketplace.";
              } catch (err) {
                return `Error fetching marketplace jobs: ${err}`;
              }
            },

            /* ── Wallet tools: transfer SOL ── */
            transferFunds: async ({ amount, to }: { amount: string; to: string }) => {
              try {
                if (!publicKey || !sendTransaction) {
                  return "Wallet not connected";
                }
                const amt = parseFloat(amount);
                if (isNaN(amt) || amt <= 0) {
                  return "Invalid amount";
                }
                const recipient = new PublicKey(to);
                const lamports = Math.round(amt * LAMPORTS_PER_SOL);
                const transaction = new Transaction().add(
                  SystemProgram.transfer({
                    fromPubkey: publicKey,
                    toPubkey: recipient,
                    lamports,
                  })
                );
                const signature = await sendTransaction(transaction, connection);
                showToast("Transaction sent!", "success");
                const explorerUrl = explorerLink(signature, "tx");
                return `Transaction sent: ${signature}\nExplorer: ${explorerUrl}`;
              } catch (e: any) {
                showToast("Transfer failed", "error");
                return `Transfer failed: ${e.message}`;
              }
            },
            getWalletAddress: async () => address ?? "No wallet connected",
          },
        });
      } catch (err: any) {
        console.error("Voice session error:", err);
        showToast("Failed to start voice session", "error");
        setOrbStatus("idle");
      }
    }
  };

  /* ── Send a typed message ── */
  const handleSendText = async () => {
    const msg = textInput.trim();
    if (!msg || isSending) return;
    setTextInput("");

    // If a voice session is active, route text through ElevenLabs so the
    // agent responds with voice and the message goes through the same pipeline.
    if (conversation.status === "connected") {
      addLine("user", msg);
      try {
        conversation.sendUserMessage(msg);
      } catch (err: any) {
        console.error("sendUserMessage error:", err);
        showToast("Failed to send message", "error");
      }
      return;
    }

    // Fallback: direct Butler API call when no voice session is active
    addLine("user", msg);
    setIsSending(true);
    setOrbStatus("thinking");
    try {
      const res = await fetch(`${BUTLER_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: msg, timestamp: Date.now() }),
      });
      if (!res.ok) throw new Error(`Butler error: ${res.statusText}`);
      const data = await res.json();
      addLine("assistant", data.response || data.message || "Request processed");

      // ── If a job was posted on-chain, trigger Stripe payment ──
      if (data.job_posted) {
        triggerStripePayment(data.job_posted);
      }
    } catch (err: any) {
      console.error("Butler text error:", err);
      addLine("assistant", `Sorry, I couldn't reach the butler. ${err.message}`);
      showToast("Backend connection error", "error");
    } finally {
      setIsSending(false);
      setOrbStatus("idle");
    }
  };

  return (
    <div className="chat-layout">
      {/* ─── Header bar (history + title + address) ─── */}
      <motion.header
        className="chat-header"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <motion.span
          className="chat-header-title"
          style={{ position: "relative", left: "auto", transform: "none" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
        >
          SOTA Butler
        </motion.span>
      </motion.header>

      {/* ─── Transcript area (always visible, scrollable) ─── */}
      <div className="transcript-area" ref={scrollRef}>
        {transcript.length === 0 ? (
          <div className="transcript-empty">
            <AnimatePresence>
              <motion.div
                className="transcript-empty-content"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.5 }}
              >
                <p className="transcript-empty-title">
                  Hello{user?.name ? `, ${user.name}` : ""}
                </p>
                <p className="transcript-empty-sub">
                  Your AI concierge is ready. Tap the orb or type below.
                </p>
              </motion.div>
            </AnimatePresence>
          </div>
        ) : (
          <div className="transcript-messages-list">
            {transcript.map((line, i) => (
              <motion.div
                key={line.id}
                className={`transcript-msg ${line.role}`}
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.3, delay: i > transcript.length - 3 ? 0.05 : 0 }}
              >
                <span className="transcript-msg-role">
                  {line.role === "user" ? "You" : "Butler"}
                </span>
                <p className="transcript-msg-text">{line.content}</p>
              </motion.div>
            ))}
            {/* Bid collection progress bar */}
            <AnimatePresence>
              {bidProgress?.active && (
                <BidProgressBar
                  duration={bidProgress.duration}
                  onComplete={() => { setBidProgress(null); bidActiveRef.current = false; }}
                />
              )}
            </AnimatePresence>
            {/* Task execution progress */}
            <AnimatePresence>
              {taskExecution?.active && (
                <TaskExecutionProgress message={taskExecution.message} />
              )}
            </AnimatePresence>
            {/* Stripe payment */}
            {stripePayment && (
              <StripePayment
                jobId={stripePayment.jobId}
                amount={stripePayment.amount}
                agentAddress={stripePayment.agentAddress}
                boardJobId={stripePayment.boardJobId}
                userId={stripePayment.userId}
                onSuccess={() => {
                  const payment = stripePayment;
                  setStripePayment(null);
                  showToast("Payment confirmed! Agent is working...", "success");
                  addLine("assistant", `Payment of ${payment.amount.toFixed(2)} USDC confirmed via Apple Pay. Escrow funded automatically!`);
                  if (payment.boardJobId) {
                    setTaskExecution({ active: true, message: "Generating your results..." });
                    fetch(`${BUTLER_URL}/marketplace/execute/${payment.boardJobId}`, { method: "POST" })
                      .then(res => res.json())
                      .then(data => {
                        setTaskExecution(null);
                        addLine("assistant", data.formatted_results || "Task completed.");
                      })
                      .catch(() => {
                        setTaskExecution(null);
                        addLine("assistant", "Task is being processed...");
                      });
                  }
                }}
                onError={(err) => {
                  setStripePayment(null);
                  showToast("Payment failed", "error");
                  addLine("assistant", `Payment failed: ${err}. You can try again or pay with crypto.`);
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* ─── Orb area (bottom) ─── */}
      <div className="orb-dock">
        <AgentOrb status={orbStatus} onClick={toggleVoice} />
      </div>

      {/* ─── Text input bar ─── */}
      <div className="text-input-bar">
        <input
          className="text-input-field"
          type="text"
          placeholder="Type a message..."
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSendText();
            }
          }}
          disabled={isSending}
        />
        <button
          className="text-input-send"
          onClick={handleSendText}
          disabled={isSending || !textInput.trim()}
        >
          <Send size={18} />
        </button>
      </div>

      {/* ─── History sidebar ─── */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              className="sidebar-overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)}
            />
            <motion.aside
              className="sidebar-panel"
              initial={{ x: -320, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -320, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 28 }}
            >
              <div className="sidebar-panel-header">
                <h3>Conversations</h3>
                <div className="sidebar-panel-actions">
                  <button
                    className="sidebar-panel-btn"
                    onClick={() => {
                      const id = newSessionId();
                      setSessionId(id);
                      sessionIdRef.current = id;
                      setTranscript([]);
                      setStripePayment(null);
                      setSidebarOpen(false);
                    }}
                  >
                    <Plus size={18} />
                  </button>
                  <button className="sidebar-panel-btn" onClick={() => setSidebarOpen(false)}>
                    <X size={18} />
                  </button>
                </div>
              </div>
              <div className="sidebar-panel-list">
                {conversations.length === 0 && (
                  <p className="sidebar-panel-empty">No conversations yet</p>
                )}
                {conversations.map((c, i) => (
                  <motion.button
                    key={c.id}
                    className={`sidebar-panel-item${c.id === sessionId ? " active" : ""}`}
                    onClick={async () => {
                      setSessionId(c.id);
                      sessionIdRef.current = c.id;
                      setSidebarOpen(false);
                      try {
                        const res = await fetch(`/api/chat?sessionId=${c.id}`);
                        const msgs = await res.json();
                        if (Array.isArray(msgs)) {
                          setTranscript(
                            msgs.map((m: any) => ({
                              id: m.id,
                              role: m.role as "user" | "assistant",
                              content: m.text,
                              timestamp: new Date(m.createdAt),
                            }))
                          );
                        }
                      } catch {
                        // If fetch fails, transcript stays empty for this session
                      }
                    }}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    whileHover={{ x: 4 }}
                  >
                    <MessageSquare size={14} />
                    <span>{c.title || "Untitled chat"}</span>
                  </motion.button>
                ))}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
