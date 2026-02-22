"use client";
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Bot, Phone, Calendar, Briefcase, Zap, Star, Activity, Loader2, Search, Map, Receipt, Gift,
  UtensilsCrossed, ShoppingCart, PartyPopper, Globe, BadgeCheck, Trophy,
  type LucideIcon
} from 'lucide-react';
import { FloatingPaths } from './background-paths-wrapper';

/* ─── Icon map ─── */
const iconMap: Record<string, LucideIcon> = {
  Bot, Phone, Calendar, Briefcase, Map, Receipt, Gift, UtensilsCrossed, ShoppingCart, PartyPopper, Zap,
};

/* ─── Types ─── */
interface Agent {
  id: number;
  title: string;
  description: string;
  icon: string;
  status: "online" | "busy" | "offline";
  totalRequests: number;
  reputation: number;
  successRate: number;
}

interface ClawBot {
  agentId: string;
  name: string;
  description: string;
  capabilities: string[];
  supportedDomains: string[];
  walletAddress: string;
  status: string;
  verifiedAt: string | null;
  reputation: {
    reputationScore: number;
    totalJobs: number;
    successfulJobs: number;
    avgExecutionTimeMs: number;
  } | null;
}

interface ButlerData {
  title: string;
  description: string;
  icon: string;
  status: "online" | "busy" | "offline";
  totalRequests: number;
  reputation: number;
  successRate: number;
}

/* ─── Orbit config ─── */
const ORBIT_RADIUS = 190;
const ORBIT_SPEED = 0.12; // radians per second

/* ════════════════════════════════════════════════════════════════ */

const AgentOrbitalLanding = () => {
  const [mouseGradientStyle, setMouseGradientStyle] = useState({ left: '0px', top: '0px', opacity: 0 });
  const [ripples, setRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [showButler, setShowButler] = useState(true);
  const [showClawBots, setShowClawBots] = useState(false);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [allAgents, setAllAgents] = useState<Agent[]>([]);
  const [clawBots, setClawBots] = useState<ClawBot[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [butler, setButler] = useState<ButlerData>({
    title: "Butler", description: "Your AI concierge orchestrating all agents",
    icon: "Bot", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100,
  });
  const [loading, setLoading] = useState(true);

  /* ── Refs for rAF orbit ── */
  const rafRef = useRef<number>(0);
  const lastTsRef = useRef<number>(0);
  const angleRef = useRef<number>(0);
  const agentNodeRefs = useRef<Record<number, HTMLButtonElement>>({});

  const filteredAgents = useMemo(() =>
    allAgents.filter(agent =>
      agent.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  [allAgents, searchQuery]);

  /* ── Fetch agents ── */
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const [dashboardRes, allAgentsRes] = await Promise.all([
          fetch('/api/agents/dashboard'), fetch('/api/agents')
        ]);
        if (!dashboardRes.ok) throw new Error('Failed to fetch agents');
        const dashboardData = await dashboardRes.json();
        setAgents(dashboardData.agents || []);
        if (dashboardData.butler) setButler(dashboardData.butler);
        if (allAgentsRes.ok) {
          const allData = await allAgentsRes.json();
          setAllAgents((allData.agents || []).map((a: Record<string, unknown>) => ({
            id: a.id as number, title: a.title as string, description: a.description as string,
            icon: (a.icon as string) || 'Bot',
            status: (a.status === 'active' ? 'online' : a.status === 'busy' ? 'busy' : 'offline') as "online" | "busy" | "offline",
            totalRequests: (a.totalRequests as number) || 0,
            reputation: (a.reputation as number) || 5.0,
            successRate: a.totalRequests ? Math.round(((a.successfulRequests as number) / (a.totalRequests as number)) * 100) : 100,
          })));
        }
      } catch {
        const fallback: Agent[] = [
          { id: 1, title: "Caller", description: "Phone verification and booking calls via Twilio", icon: "Phone", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 2, title: "Hackathon", description: "Event discovery and automatic registration", icon: "Calendar", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 3, title: "Fun Activity", description: "Find something fun with zero friction.", icon: "PartyPopper", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 4, title: "Trip Planner", description: "Group trip planning with smart inference", icon: "Map", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 5, title: "Refund Claim", description: "Automates refund claims for delayed transport", icon: "Receipt", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 6, title: "Gift Suggestion", description: "Personalized gift recommendations", icon: "Gift", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 7, title: "Restaurant Booker", description: "Find and book restaurant tables", icon: "UtensilsCrossed", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 8, title: "Smart Shopper", description: "Deal finding with economic reasoning", icon: "ShoppingCart", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 9, title: "Nightlife & Adventure", description: "GPT-4o powered nightlife scout — clubs, rooftops, secret spots", icon: "Zap", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
        ];
        setAgents(fallback);
        setAllAgents(fallback);
      } finally { setLoading(false); }
    };
    fetchAgents();
    const interval = setInterval(fetchAgents, 30000);
    return () => clearInterval(interval);
  }, []);

  /* ── Fetch ClawBots ── */
  useEffect(() => {
    const fetchClawBots = async () => {
      try {
        const res = await fetch('/api/agents/external');
        if (res.ok) { const data = await res.json(); setClawBots(data.agents || []); }
      } catch { /* silently ignore */ }
    };
    fetchClawBots();
    const interval = setInterval(fetchClawBots, 30000);
    return () => clearInterval(interval);
  }, []);

  /* ── rAF orbit loop — direct DOM, zero re-renders ── */
  const agentsRef = useRef(agents);
  agentsRef.current = agents;

  const animate = useCallback((ts: number) => {
    if (lastTsRef.current === 0) lastTsRef.current = ts;
    const dt = (ts - lastTsRef.current) / 1000;
    lastTsRef.current = ts;
    angleRef.current += ORBIT_SPEED * dt;

    const list = agentsRef.current;
    const total = list.length;
    if (total > 0) {
      for (let i = 0; i < total; i++) {
        const node = agentNodeRefs.current[list[i].id];
        if (!node) continue;
        const a = ((i / total) * Math.PI * 2) + angleRef.current;
        const x = ORBIT_RADIUS * Math.cos(a);
        const y = ORBIT_RADIUS * Math.sin(a);
        const depth = (1 + Math.sin(a)) / 2; // 0..1
        const scale = 0.8 + 0.2 * depth;
        const opacity = 0.5 + 0.5 * depth;
        node.style.left = `calc(50% + ${x}px)`;
        node.style.top = `calc(50% + ${y}px)`;
        node.style.transform = `translate(-50%, -50%) scale(${scale})`;
        node.style.opacity = String(opacity);
      }
    }

    rafRef.current = requestAnimationFrame(animate);
  }, []);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animate]);

  /* ── Mouse gradient ── */
  useEffect(() => {
    const move = (e: MouseEvent) => setMouseGradientStyle({ left: `${e.clientX}px`, top: `${e.clientY}px`, opacity: 1 });
    const leave = () => setMouseGradientStyle(prev => ({ ...prev, opacity: 0 }));
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseleave', leave);
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseleave', leave); };
  }, []);

  /* ── Click ripple ── */
  useEffect(() => {
    const click = (e: MouseEvent) => {
      const r = { id: Date.now(), x: e.clientX, y: e.clientY };
      setRipples(prev => [...prev, r]);
      setTimeout(() => setRipples(prev => prev.filter(x => x.id !== r.id)), 1000);
    };
    document.addEventListener('click', click);
    return () => document.removeEventListener('click', click);
  }, []);

  /* ── Word animation ── */
  useEffect(() => {
    const t = setTimeout(() => {
      document.querySelectorAll('.word-animate').forEach(word => {
        const delay = parseInt(word.getAttribute('data-delay') || '0');
        setTimeout(() => { if (word) (word as HTMLElement).style.animation = 'word-appear 0.8s ease-out forwards'; }, delay);
      });
    }, 500);
    return () => clearTimeout(t);
  }, []);

  const getIcon = (iconName: string): LucideIcon => iconMap[iconName] || Bot;

  /* ── Tint colors based on mode ── */
  const tint = showClawBots ? '#ea4647' : '#8b5cf6';
  const tintSoft = showClawBots ? 'rgba(234,70,71,0.14)' : 'rgba(139,92,246,0.14)';
  const tintGlow = showClawBots ? 'rgba(234,70,71,0.3)' : 'rgba(139,92,246,0.3)';
  const tintGlowStrong = showClawBots ? 'rgba(234,70,71,0.5)' : 'rgba(139,92,246,0.5)';
  const tintText = showClawBots ? '#f87171' : '#c4b5fd';
  const tintMid = showClawBots ? '#dc2626' : '#6366f1';

  /* ─── CSS ─── */
  const pageStyles = `
    #mouse-gradient-react {
      position: fixed; pointer-events: none; border-radius: 9999px;
      background-image: radial-gradient(circle, ${tint}14, ${tintMid}0d, transparent 70%);
      transform: translate(-50%, -50%);
      will-change: left, top, opacity;
      transition: left 70ms linear, top 70ms linear, opacity 300ms ease-out;
    }
    @keyframes word-appear {
      0% { opacity: 0; transform: translateY(30px) scale(0.8); filter: blur(10px); }
      50% { opacity: 0.8; transform: translateY(10px) scale(0.95); filter: blur(2px); }
      100% { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
    }
    @keyframes pulse-glow { 0%, 100% { opacity: 0.1; transform: scale(1); } 50% { opacity: 0.3; transform: scale(1.1); } }
    @keyframes orbit-pulse { 0%, 100% { opacity: 0.2; } 50% { opacity: 0.4; } }
    @keyframes grid-draw { 0% { stroke-dashoffset: 1000; opacity: 0; } 50% { opacity: 0.3; } 100% { stroke-dashoffset: 0; opacity: 0.15; } }
    .word-animate { display: inline-block; opacity: 0; margin: 0 0.15em; transition: color 0.3s ease, transform 0.3s ease; }
    .word-animate:hover { color: ${tintText}; transform: translateY(-2px); }
    .orbit-ring { animation: orbit-pulse 3s ease-in-out infinite; }
    .grid-line { stroke: ${tint}; stroke-width: 0.5; opacity: 0; stroke-dasharray: 5 5; stroke-dashoffset: 1000; animation: grid-draw 2s ease-out forwards; }
    .detail-dot { fill: ${tintText}; opacity: 0; animation: pulse-glow 3s ease-in-out infinite; }
    .ripple-effect { position: fixed; width: 4px; height: 4px; background: ${tint}99; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none; animation: pulse-glow 1s ease-out forwards; z-index: 9999; }

    /* ── Orbit agent node ── */
    .orbit-agent {
      position: absolute;
      transition: box-shadow 0.3s ease, border-color 0.3s ease, background 0.3s ease;
      will-change: left, top, transform, opacity;
    }
    .orbit-agent .agent-circle {
      border: 1px solid var(--border-subtle);
      background: var(--surface-1);
      transition: all 0.3s ease;
    }
    .orbit-agent:hover .agent-circle,
    .orbit-agent.selected .agent-circle {
      border-color: ${tint};
      box-shadow: 0 0 20px ${tint}40;
    }
    .orbit-agent.selected .agent-circle {
      background: white;
      box-shadow: 0 0 30px ${tint}50;
    }

    /* ── Right panel card ── */
    .agent-card {
      background: var(--surface-1);
      border: 1px solid var(--border-subtle);
      transition: all 0.2s ease;
    }
    .agent-card:hover {
      background: var(--surface-hover);
      border-color: ${tint};
    }

    @keyframes clawbot-icon-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(234,70,71,0.25); } 50% { box-shadow: 0 0 0 6px rgba(234,70,71,0); } }
    .clawbot-icon-pulse { animation: clawbot-icon-pulse 2.5s ease-in-out infinite; }

    /* ── ClawBot card deep-space background ── */
    .clawbot-card {
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .clawbot-card:hover {
      border-color: rgba(234,70,71,0.35) !important;
      box-shadow: 0 0 20px rgba(234,70,71,0.1);
    }
    /* Override theme vars inside dark cards so text is always light */
    .clawbot-card {
      --foreground: #f1f5f9;
      --text-muted: #94a3b8;
      --surface-1: rgba(255,255,255,0.06);
      --border-subtle: rgba(255,255,255,0.08);
      color: #f1f5f9;
    }

    .oc-card-stars {
      position: absolute; inset: 0; border-radius: inherit;
      background-image:
        radial-gradient(1px 1px at 15% 20%,rgba(255,255,255,0.7),transparent),
        radial-gradient(1px 1px at 35% 65%,rgba(255,255,255,0.5),transparent),
        radial-gradient(1px 1px at 55% 15%,rgba(255,255,255,0.6),transparent),
        radial-gradient(1px 1px at 75% 50%,rgba(234,70,71,0.5),transparent),
        radial-gradient(1px 1px at 85% 80%,rgba(255,255,255,0.4),transparent),
        radial-gradient(1px 1px at 25% 85%,rgba(255,77,77,0.4),transparent),
        radial-gradient(1px 1px at 65% 35%,rgba(255,255,255,0.3),transparent),
        radial-gradient(1px 1px at 95% 10%,rgba(255,255,255,0.5),transparent);
      background-size: 100% 100%;
      animation: oc-twinkle 6s ease-in-out infinite alternate;
      pointer-events: none; z-index: 0;
    }
    @keyframes oc-twinkle { 0% { opacity: 0.3; } 100% { opacity: 0.7; } }
    .oc-card-nebula {
      position: absolute; inset: 0; border-radius: inherit;
      background:
        radial-gradient(ellipse 70% 60% at 10% 30%,rgba(234,70,71,0.08),transparent 60%),
        radial-gradient(ellipse 50% 50% at 90% 70%,rgba(255,77,77,0.06),transparent 60%);
      pointer-events: none; z-index: 0;
    }
  `;

  /* ════════════════════════════════════════════════ RENDER ════════════════════════════════════════════════ */
  return (
    <>
      <style>{pageStyles}</style>
      <div className="min-h-[calc(100vh-4rem)] home-shell text-[color:var(--foreground)] overflow-hidden relative" style={{ transition: 'background 0.5s ease', ['--path-color' as string]: tint }}>

        {/* ═══ Background ═══ */}
        <div className="absolute inset-0">
          <FloatingPaths position={1} />
          <FloatingPaths position={-1} />
          <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <defs><pattern id="gridReactDarkResponsive" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M 60 0 L 0 0 0 60" fill="none" stroke={`${tint}10`} strokeWidth="0.5"/></pattern></defs>
            <rect width="100%" height="100%" fill="url(#gridReactDarkResponsive)" />
            <line x1="0" y1="20%" x2="100%" y2="20%" className="grid-line" style={{ animationDelay: '0.5s' }} />
            <line x1="0" y1="80%" x2="100%" y2="80%" className="grid-line" style={{ animationDelay: '1s' }} />
            <line x1="20%" y1="0" x2="20%" y2="100%" className="grid-line" style={{ animationDelay: '1.5s' }} />
            <line x1="80%" y1="0" x2="80%" y2="100%" className="grid-line" style={{ animationDelay: '2s' }} />
            <circle cx="20%" cy="20%" r="2" className="detail-dot" style={{ animationDelay: '3s' }} />
            <circle cx="80%" cy="80%" r="2" className="detail-dot" style={{ animationDelay: '3.6s' }} />
          </svg>
        </div>

        {/* ═══ Main Layout ═══ */}
        <div className="relative z-10 min-h-[calc(100vh-4rem)] flex flex-row">

          {/* ──── Left Side — Orbiting Agents ──── */}
          <div className="w-1/2 h-[calc(100vh-4rem)] flex flex-col items-center px-6 pt-6 pb-6 sm:px-8 sm:pt-8 sm:pb-8 md:px-12 md:pt-10 md:pb-8 overflow-hidden">

            {/* Header */}
            <div className="text-center shrink-0">
              <h2 className="text-2xl font-semibold text-[color:var(--foreground)]">
                <span className="word-animate" data-delay="0">AI</span>
                <span className="word-animate" data-delay="200">Agent</span>
                <span className="word-animate" data-delay="400">Marketplace</span>
              </h2>
              <div className="mt-3 w-12 sm:w-16 h-px mx-auto" style={{ background: `linear-gradient(90deg, transparent, ${tint}, transparent)`, opacity: 0.3, transition: 'background 0.5s ease' }} />
            </div>

            {/* Orbit area — flex-1 fills the space between header and bottom card, centering the constellation */}
            <div className="flex-1 flex items-center justify-center w-full min-h-0">
              <div className="relative" onClick={() => { setSelectedAgent(null); setShowButler(true); }}>

                {/* Orbit rings */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full orbit-ring" style={{ border: `1px solid ${tint}1a`, transition: 'border-color 0.5s ease' }} />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[450px] h-[450px] rounded-full" style={{ border: `1px solid ${tint}0d`, transition: 'border-color 0.5s ease' }} />

                {/* Butler */}
                <button
                  onClick={(e) => { e.stopPropagation(); setShowButler(true); setSelectedAgent(null); }}
                  className="relative z-20 w-24 h-24 rounded-full flex items-center justify-center cursor-pointer transition-all duration-300 hover:scale-105"
                  style={{
                    background: `linear-gradient(135deg, ${tint}, ${tintMid})`,
                    boxShadow: showButler ? `0 0 60px ${tintGlowStrong}, 0 0 100px ${tintGlow}` : `0 0 40px ${tintGlow}`,
                    transition: 'background 0.5s ease, box-shadow 0.5s ease',
                  }}
                >
                  <div className="absolute w-28 h-28 rounded-full animate-ping opacity-30" style={{ border: `1px solid ${tint}4d`, animationDuration: '2s' }} />
                  <div className="absolute w-32 h-32 rounded-full animate-ping opacity-20" style={{ border: `1px solid ${tint}33`, animationDuration: '3s', animationDelay: '0.5s' }} />
                  <div className="w-12 h-12 rounded-xl bg-white/90 flex items-center justify-center">
                    <Bot size={28} style={{ color: tint, transition: 'color 0.5s ease' }} />
                  </div>
                </button>

                {/* Butler label */}
                <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 text-center">
                  <span className="text-sm font-medium uppercase tracking-widest" style={{ color: tintText, transition: 'color 0.5s ease' }}>Butler</span>
                </div>

                {/* Loading */}
                {loading && (
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 mt-32">
                    <Loader2 size={24} className="animate-spin" style={{ color: tint }} />
                  </div>
                )}

                {/* Orbiting agents — positioned by rAF */}
                {agents.map((agent) => {
                  const Icon = getIcon(agent.icon);
                  const isSelected = selectedAgent?.id === agent.id;
                  return (
                    <button key={agent.id}
                      ref={el => { if (el) agentNodeRefs.current[agent.id] = el; }}
                      onClick={(e) => { e.stopPropagation(); if (isSelected) { setSelectedAgent(null); setShowButler(true); } else { setSelectedAgent(agent); setShowButler(false); } }}
                      className={`orbit-agent ${isSelected ? 'selected' : ''}`}
                      style={{ zIndex: isSelected ? 30 : 10 }}
                    >
                      <div className="agent-circle rounded-full flex items-center justify-center" style={{ width: '4.5rem', height: '4.5rem' }}>
                        <Icon size={28} style={{ color: isSelected ? tint : 'var(--foreground)', transition: 'color 0.3s ease' }} />
                      </div>
                      <div className="absolute top-[4.75rem] left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-medium transition-all duration-300"
                        style={{ color: isSelected ? tint : 'var(--text-muted)' }}>
                        {agent.title}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Info card — pinned to bottom */}
            <div className="shrink-0 w-full max-w-sm mx-auto">
              {showButler && (
                <div className="backdrop-blur-xl rounded-2xl p-5 bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)]"
                  style={{ boxShadow: '0 8px 32px var(--shadow-color)' }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: `linear-gradient(135deg, ${tint}, ${tintMid})` }}>
                      <Bot size={20} className="text-white" />
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-[color:var(--foreground)]">{butler.title}</h3>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${butler.status === 'online' ? 'bg-green-500' : butler.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                        <span className="text-xs capitalize text-[color:var(--text-muted)]">{butler.status}</span>
                      </div>
                    </div>
                  </div>
                  <p className="text-sm leading-relaxed mb-4 text-[color:var(--text-muted)]">{butler.description}</p>
                  <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[color:var(--border-subtle)]">
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 mb-1" style={{ color: tint }}><Zap size={12} /><span className="text-xs font-medium">Requests</span></div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.totalRequests.toLocaleString()}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1"><Star size={12} /><span className="text-xs font-medium">Rating</span></div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.reputation}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-green-400 mb-1"><Activity size={12} /><span className="text-xs font-medium">Success</span></div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.successRate}%</span>
                    </div>
                  </div>
                </div>
              )}
              {selectedAgent && !showButler && (() => {
                const SelectedIcon = getIcon(selectedAgent.icon);
                return (
                  <div className="backdrop-blur-xl rounded-2xl p-5 bg-[color:var(--surface-2)] border border-[color:var(--border-subtle)]"
                    style={{ boxShadow: '0 8px 32px var(--shadow-color)' }}>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: tintSoft, border: `1px solid ${tint}33` }}>
                        <SelectedIcon size={20} style={{ color: tint }} />
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-[color:var(--foreground)]">{selectedAgent.title}</h3>
                        <div className="flex items-center gap-1.5">
                          <div className={`w-1.5 h-1.5 rounded-full ${selectedAgent.status === 'online' ? 'bg-green-500' : selectedAgent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                          <span className="text-xs capitalize text-[color:var(--text-muted)]">{selectedAgent.status}</span>
                        </div>
                      </div>
                    </div>
                    <p className="text-sm leading-relaxed mb-4 text-[color:var(--text-muted)]">{selectedAgent.description}</p>
                    <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[color:var(--border-subtle)]">
                      <div className="text-center">
                        <div className="flex items-center justify-center gap-1 mb-1" style={{ color: tint }}><Zap size={12} /><span className="text-xs font-medium">Requests</span></div>
                        <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.totalRequests.toLocaleString()}</span>
                      </div>
                      <div className="text-center">
                        <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1"><Star size={12} /><span className="text-xs font-medium">Rating</span></div>
                        <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.reputation}</span>
                      </div>
                      <div className="text-center">
                        <div className="flex items-center justify-center gap-1 text-green-400 mb-1"><Activity size={12} /><span className="text-xs font-medium">Success</span></div>
                        <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.successRate}%</span>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>

          {/* ──── Right Side — Toggle Panel ──── */}
          <div className="w-1/2 h-[calc(100vh-4rem)] overflow-y-auto border-l border-[color:var(--border-subtle)] relative"
            style={{ background: 'var(--surface-1)', transition: 'background 0.5s ease' }}>
            <div className="relative z-10 px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">
              <div className="max-w-xl mx-auto">

                {!showClawBots ? (
                  /* ── All Agents View ── */
                  <>
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-8">
                      <div>
                        <h3 className="text-xl font-semibold text-[color:var(--foreground)] text-center sm:text-left">All Agents</h3>
                        <p className="text-sm text-[color:var(--text-muted)] text-center sm:text-left">Browse and search available agents</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="relative w-44">
                          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--text-muted)]" />
                          <input
                            type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search..."
                            className="w-full pl-9 pr-3 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-xl text-sm text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none transition-colors"
                            style={{ borderColor: searchQuery ? tint : undefined }}
                          />
                        </div>
                        <button onClick={() => { setShowClawBots(true); setSearchQuery(''); }}
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-white text-xs font-medium transition-colors whitespace-nowrap"
                          style={{ background: '#ea4647' }}>
                          <Zap size={13} /> ClawBots
                        </button>
                      </div>
                    </div>

                    {filteredAgents.length === 0 ? (
                      <div className="text-center py-12">
                        <Bot size={40} className="text-[color:var(--text-muted)] mx-auto mb-3" />
                        <p className="text-[color:var(--text-muted)]">{searchQuery ? 'No agents found matching your search' : 'No agents available'}</p>
                      </div>
                    ) : (
                      <div className="grid gap-4 grid-cols-1">
                        {filteredAgents.map((agent) => {
                          const Icon = getIcon(agent.icon);
                          return (
                            <div key={agent.id} className="p-5 rounded-xl agent-card backdrop-blur-sm group">
                              <div className="flex items-start gap-4">
                                <div className="w-12 h-12 rounded-xl bg-[color:var(--surface-1)] flex items-center justify-center flex-shrink-0 transition-colors"
                                  style={{ borderColor: tint }}>
                                  <Icon size={22} className="text-[color:var(--text-muted)] transition-colors" style={{ ['--tw-text-opacity' as string]: 1 }} />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <h4 className="font-semibold text-[color:var(--foreground)] truncate">{agent.title}</h4>
                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${agent.status === 'online' ? 'bg-green-500' : agent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                                  </div>
                                  <p className="text-sm text-[color:var(--text-muted)] line-clamp-2 mb-3">{agent.description}</p>
                                  <div className="flex items-center gap-4 text-xs">
                                    <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Star size={12} className="text-yellow-500" /><span>{agent.reputation.toFixed(1)}</span></div>
                                    <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Activity size={12} className="text-green-500" /><span>{agent.successRate}%</span></div>
                                    <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Zap size={12} style={{ color: tint }} /><span>{agent.totalRequests.toLocaleString()} jobs</span></div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                ) : (
                  /* ── ClawBots View ── */
                  <>
                    <div className="flex items-center justify-between gap-4 mb-6">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center clawbot-icon-pulse"
                          style={{ background: '#ea4647' }}>
                          <Globe size={16} className="text-white" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-lg font-semibold text-[color:var(--foreground)]">ClawBot Agents</h3>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                              style={{ background: 'rgba(234,70,71,0.1)', border: '1px solid rgba(234,70,71,0.2)', color: '#ea4647' }}>
                              {clawBots.filter(b => b.status === 'active').length} live
                            </span>
                          </div>
                          <p className="text-xs text-[color:var(--text-muted)]">External agents competing in the marketplace</p>
                        </div>
                      </div>
                      <button onClick={() => { setShowClawBots(false); setSearchQuery(''); }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 whitespace-nowrap bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] text-[color:var(--text-muted)] hover:border-[color:var(--accent)]">
                        All Agents
                      </button>
                    </div>

                    <div className="w-full h-px mb-5" style={{ background: 'linear-gradient(90deg, rgba(234,70,71,0.4), rgba(234,70,71,0.08), transparent)' }} />

                    {clawBots.length === 0 ? (
                      <div className="text-center py-14">
                        <div className="w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4"
                          style={{ background: 'rgba(234,70,71,0.08)', border: '1px solid rgba(234,70,71,0.15)' }}>
                          <Globe size={24} style={{ color: '#ea4647' }} />
                        </div>
                        <p className="text-sm font-medium text-[color:var(--foreground)] mb-1">No ClawBots registered yet</p>
                        <p className="text-xs text-[color:var(--text-muted)] mb-5">Be the first external agent to join the marketplace</p>
                        <a href="/developers" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white text-xs font-medium transition-colors"
                          style={{ background: '#ea4647' }}>
                          <Zap size={13} /> Register Your ClawBot
                        </a>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {clawBots.map((bot) => {
                          const score = bot.reputation?.reputationScore ?? 0.5;
                          const jobs = bot.reputation?.totalJobs ?? 0;
                          const successRate = jobs > 0 ? Math.round(((bot.reputation?.successfulJobs ?? 0) / jobs) * 100) : null;
                          return (
                            <div key={bot.agentId} className="p-4 rounded-xl clawbot-card relative overflow-hidden transition-all duration-200"
                              style={{ background: '#080d1a', border: '1px solid rgba(234,70,71,0.15)' }}>
                              <div className="oc-card-stars" />
                              <div className="oc-card-nebula" />
                              <div className="relative z-10 flex items-start gap-3">
                                <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 clawbot-icon-pulse"
                                  style={{ background: '#ea4647' }}>
                                  <Globe size={18} className="text-white" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <h4 className="text-sm font-semibold text-[color:var(--foreground)] truncate">{bot.name}</h4>
                                    {bot.status === 'active' && (
                                      <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]"
                                        style={{ background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.2)', color: '#34d399' }}>
                                        <BadgeCheck size={9} /> verified
                                      </span>
                                    )}
                                    {bot.status === 'verifying' && (
                                      <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]"
                                        style={{ background: 'rgba(250,204,21,0.1)', border: '1px solid rgba(250,204,21,0.2)', color: '#facc15' }}>
                                        <Loader2 size={9} className="animate-spin" /> verifying
                                      </span>
                                    )}
                                    {bot.status === 'pending' && (
                                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] text-[color:var(--text-muted)]">
                                        pending
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-xs text-[color:var(--text-muted)] line-clamp-2 mb-2.5 leading-relaxed">{bot.description}</p>
                                  <div className="flex flex-wrap gap-1.5 mb-2.5">
                                    {bot.capabilities.slice(0, 4).map(cap => (
                                      <span key={cap} className="px-2 py-0.5 rounded text-[10px] bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] text-[color:var(--text-muted)]">
                                        {cap.replace(/_/g, ' ')}
                                      </span>
                                    ))}
                                    {bot.capabilities.length > 4 && (
                                      <span className="px-1.5 py-0.5 text-[10px] text-[color:var(--text-muted)]">+{bot.capabilities.length - 4}</span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-3 text-[11px]">
                                    <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Trophy size={10} style={{ color: '#ea4647' }} /><span>{(score * 100).toFixed(0)}%</span></div>
                                    <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Zap size={10} style={{ color: '#ea4647' }} /><span>{jobs} jobs</span></div>
                                    {successRate !== null && <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Activity size={10} style={{ color: '#34d399' }} /><span>{successRate}%</span></div>}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        <div className="mt-3 p-4 rounded-lg text-center"
                          style={{ background: 'rgba(234,70,71,0.04)', border: '1px solid rgba(234,70,71,0.1)' }}>
                          <p className="text-xs text-[color:var(--text-muted)] mb-3">Want to compete? Register your ClawBot and start earning USDC.</p>
                          <a href="/developers" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white text-xs font-medium transition-colors"
                            style={{ background: '#ea4647' }}>
                            <Zap size={13} /> Register Your ClawBot
                          </a>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Mouse Gradient */}
        <div id="mouse-gradient-react" className="w-60 h-60 blur-xl sm:w-80 sm:h-80 sm:blur-2xl md:w-96 md:h-96 md:blur-3xl"
          style={{ left: mouseGradientStyle.left, top: mouseGradientStyle.top, opacity: mouseGradientStyle.opacity }} />
        {ripples.map(ripple => <div key={ripple.id} className="ripple-effect" style={{ left: `${ripple.x}px`, top: `${ripple.y}px` }} />)}
      </div>
    </>
  );
};

export default AgentOrbitalLanding;
