"use client";
import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Bot, Phone, Calendar, Briefcase, X, Zap, Star, Activity, Loader2, Search, Map, Receipt, Gift,
  UtensilsCrossed, ShoppingCart, PartyPopper, Globe, FlipHorizontal, BadgeCheck, Trophy,
  type LucideIcon
} from 'lucide-react';
import { FloatingPaths } from './background-paths-wrapper';

const iconMap: Record<string, LucideIcon> = {
  Bot, Phone, Calendar, Briefcase, Map, Receipt, Gift, UtensilsCrossed, ShoppingCart, PartyPopper, Zap,
};

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

/* ─── Constellation positions (used in OpenClaw mode) ─── */
const STAR_POSITIONS: { x: number; y: number }[] = [
  { x: -160, y: -110 }, { x: -40, y: -175 }, { x: 85, y: -145 },
  { x: 175, y: -45 },   { x: 145, y: 95 },   { x: 10, y: 175 },
  { x: -125, y: 125 },  { x: -180, y: 15 },   { x: -95, y: -50 },
  { x: 50, y: -65 },    { x: 100, y: 20 },    { x: 20, y: 85 },
  { x: -100, y: 60 },   { x: 185, y: -145 },  { x: -185, y: -155 },
  { x: 160, y: 170 },
];

const CONSTELLATION_EDGES: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7],
  [0, 8], [8, 9], [9, 2], [4, 10], [10, 11], [11, 6], [7, 12], [12, 8],
];

const AgentOrbitalLanding = () => {
  const [mouseGradientStyle, setMouseGradientStyle] = useState({ left: '0px', top: '0px', opacity: 0 });
  const [ripples, setRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);
  const [scrolled, setScrolled] = useState(false);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [showButler, setShowButler] = useState(false);
  const floatingElementsRef = useRef<Element[]>([]);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [allAgents, setAllAgents] = useState<Agent[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [butler, setButler] = useState<ButlerData>({
    title: "Butler", description: "Your AI concierge orchestrating all agents",
    icon: "Bot", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showClawBots, setShowClawBots] = useState(false);
  const [flipStage, setFlipStage] = useState<'idle' | 'out' | 'in'>('idle');
  const [clawBots, setClawBots] = useState<ClawBot[]>([]);

  // Constellation decorative stars (stable)
  const decoStars = useMemo(() =>
    Array.from({ length: 50 }, () => ({
      cx: Math.random() * 560, cy: Math.random() * 560,
      r: 0.4 + Math.random() * 1.2,
      baseOpacity: 0.15 + Math.random() * 0.45,
      delay: `${Math.random() * 8}s`, dur: `${3 + Math.random() * 5}s`,
    })),
  []);

  // ── Fetch agents ──
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
        setError(null);
      } catch (err) {
        console.error('Error fetching agents:', err);
        setError('Failed to load agents');
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

  // ── Fetch ClawBots ──
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

  // ── Orbital rotation (only in default mode) ──
  useEffect(() => {
    if (showClawBots) return;
    const interval = setInterval(() => {
      setRotationAngle(prev => (prev + 0.3) % 360);
    }, 50);
    return () => clearInterval(interval);
  }, [showClawBots]);

  const getAgentPosition = (index: number, total: number) => {
    const angle = ((index / total) * 360 + rotationAngle) % 360;
    const radius = 220;
    const radian = (angle * Math.PI) / 180;
    return {
      x: radius * Math.cos(radian),
      y: radius * Math.sin(radian),
      opacity: 0.5 + 0.5 * ((1 + Math.sin(radian)) / 2),
      scale: 0.8 + 0.2 * ((1 + Math.sin(radian)) / 2),
    };
  };

  const handleFlip = () => {
    if (flipStage !== 'idle') return;
    setFlipStage('out');
    setTimeout(() => {
      setShowClawBots(prev => !prev);
      setSelectedAgent(null);
      setShowButler(false);
      setFlipStage('in');
      setTimeout(() => setFlipStage('idle'), 350);
    }, 350);
  };

  const filteredAgents = allAgents.filter(agent =>
    agent.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getIcon = (iconName: string): LucideIcon => iconMap[iconName] || Bot;

  // ── Word animation ──
  useEffect(() => {
    const t = setTimeout(() => {
      document.querySelectorAll('.word-animate').forEach(word => {
        const delay = parseInt(word.getAttribute('data-delay') || '0');
        setTimeout(() => { if (word) (word as HTMLElement).style.animation = 'word-appear 0.8s ease-out forwards'; }, delay);
      });
    }, 500);
    return () => clearTimeout(t);
  }, []);

  // ── Mouse gradient ──
  useEffect(() => {
    const move = (e: MouseEvent) => setMouseGradientStyle({ left: `${e.clientX}px`, top: `${e.clientY}px`, opacity: 1 });
    const leave = () => setMouseGradientStyle(prev => ({ ...prev, opacity: 0 }));
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseleave', leave);
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseleave', leave); };
  }, []);

  // ── Click ripple ──
  useEffect(() => {
    const click = (e: MouseEvent) => {
      const r = { id: Date.now(), x: e.clientX, y: e.clientY };
      setRipples(prev => [...prev, r]);
      setTimeout(() => setRipples(prev => prev.filter(x => x.id !== r.id)), 1000);
    };
    document.addEventListener('click', click);
    return () => document.removeEventListener('click', click);
  }, []);

  // ── Word hover ──
  useEffect(() => {
    const els = document.querySelectorAll('.word-animate');
    const enter = (e: Event) => { if (e.target) (e.target as HTMLElement).style.textShadow = '0 0 20px rgba(203,213,225,0.5)'; };
    const leave = (e: Event) => { if (e.target) (e.target as HTMLElement).style.textShadow = 'none'; };
    els.forEach(w => { w.addEventListener('mouseenter', enter); w.addEventListener('mouseleave', leave); });
    return () => { els.forEach(w => { if (w) { w.removeEventListener('mouseenter', enter); w.removeEventListener('mouseleave', leave); } }); };
  }, []);

  // ── Floating elements on scroll ──
  useEffect(() => {
    floatingElementsRef.current = Array.from(document.querySelectorAll('.floating-element-animate'));
    const handleScroll = () => {
      if (!scrolled) {
        setScrolled(true);
        floatingElementsRef.current.forEach((el, i) => {
          setTimeout(() => { if (el) { (el as HTMLElement).style.animationPlayState = 'running'; (el as HTMLElement).style.opacity = ''; } },
            (parseFloat((el as HTMLElement).style.animationDelay || "0") * 1000) + i * 100);
        });
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [scrolled]);

  const CX = 280;
  const CY = 280;

  const pageStyles = `
    #mouse-gradient-react {
      position: fixed; pointer-events: none; border-radius: 9999px;
      background-image: radial-gradient(circle, rgba(139,92,246,0.08), rgba(59,130,246,0.05), transparent 70%);
      transform: translate(-50%, -50%);
      will-change: left, top, opacity;
      transition: left 70ms linear, top 70ms linear, opacity 300ms ease-out;
    }
    @keyframes word-appear {
      0% { opacity: 0; transform: translateY(30px) scale(0.8); filter: blur(10px); }
      50% { opacity: 0.8; transform: translateY(10px) scale(0.95); filter: blur(2px); }
      100% { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
    }
    @keyframes grid-draw { 0% { stroke-dashoffset: 1000; opacity: 0; } 50% { opacity: 0.3; } 100% { stroke-dashoffset: 0; opacity: 0.15; } }
    @keyframes pulse-glow { 0%, 100% { opacity: 0.1; transform: scale(1); } 50% { opacity: 0.3; transform: scale(1.1); } }
    @keyframes orbit-pulse { 0%, 100% { opacity: 0.2; } 50% { opacity: 0.4; } }
    .word-animate { display: inline-block; opacity: 0; margin: 0 0.15em; transition: color 0.3s ease, transform 0.3s ease; }
    .word-animate:hover { color: var(--accent-text); transform: translateY(-2px); }
    .grid-line { stroke: var(--path-color); stroke-width: 0.5; opacity: 0; stroke-dasharray: 5 5; stroke-dashoffset: 1000; animation: grid-draw 2s ease-out forwards; }
    .detail-dot { fill: var(--accent-text); opacity: 0; animation: pulse-glow 3s ease-in-out infinite; }
    .corner-element-animate { position: absolute; width: 40px; height: 40px; border: 1px solid var(--border-subtle); opacity: 0; animation: word-appear 1s ease-out forwards; }
    .floating-element-animate { position: absolute; width: 2px; height: 2px; background: var(--accent-text); border-radius: 50%; opacity: 0; animation: float 4s ease-in-out infinite; animation-play-state: paused; }
    @keyframes float { 0%, 100% { transform: translateY(0) translateX(0); opacity: 0.2; } 25% { transform: translateY(-10px) translateX(5px); opacity: 0.6; } 50% { transform: translateY(-5px) translateX(-3px); opacity: 0.4; } 75% { transform: translateY(-15px) translateX(7px); opacity: 0.8; } }
    .orbit-ring { animation: orbit-pulse 3s ease-in-out infinite; }
    .ripple-effect { position: fixed; width: 4px; height: 4px; background: rgba(167,139,250,0.6); border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none; animation: pulse-glow 1s ease-out forwards; z-index: 9999; }
    /* ── Galaxy constellation CSS ── */
    @keyframes star-shimmer { 0%, 100% { fill-opacity: var(--star-base); } 50% { fill-opacity: 0.9; } }
    .deco-star { animation: star-shimmer var(--star-dur, 4s) ease-in-out infinite; animation-delay: var(--star-delay, 0s); }
    .star-node { backdrop-filter: blur(10px); background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); transition: all 0.3s ease; }
    .star-node:hover { background: rgba(255,255,255,0.1); border-color: rgba(234,70,71,0.4); box-shadow: 0 0 20px rgba(234,70,71,0.15); }
    .star-node.selected { background: rgba(234,70,71,0.1); border-color: rgba(234,70,71,0.5); box-shadow: 0 0 24px rgba(234,70,71,0.25), 0 0 48px rgba(234,70,71,0.1); }
    @keyframes node-breathe { 0%, 100% { box-shadow: 0 0 8px rgba(234,70,71,0.08); } 50% { box-shadow: 0 0 16px rgba(234,70,71,0.15); } }
    .star-node { animation: node-breathe 4s ease-in-out infinite; }
    /* ── Flip ── */
    .panel-flip-wrapper { perspective: 1200px; height: 100%; overflow: hidden; }
    .panel-flip-card { height: 100%; overflow-y: auto; }
    .panel-flip-card.flip-out { animation: flipOut 0.35s ease-in forwards; }
    .panel-flip-card.flip-in { animation: flipIn 0.35s ease-out forwards; }
    @keyframes flipOut { 0% { transform: rotateY(0deg); opacity: 1; } 100% { transform: rotateY(90deg); opacity: 0; } }
    @keyframes flipIn { 0% { transform: rotateY(-90deg); opacity: 0; } 100% { transform: rotateY(0deg); opacity: 1; } }
    /* ── OpenClaw theme ── */
    .oc-panel { background: #050811; color: #e2e8f0; position: relative; overflow: hidden; }
    .oc-stars { position: absolute; inset: 0; background-image: radial-gradient(2px 2px at 20px 30px,rgba(255,255,255,0.8),transparent), radial-gradient(2px 2px at 40px 70px,rgba(255,255,255,0.5),transparent), radial-gradient(1px 1px at 90px 40px,rgba(255,255,255,0.6),transparent), radial-gradient(2px 2px at 130px 80px,rgba(255,255,255,0.4),transparent), radial-gradient(1px 1px at 160px 120px,rgba(255,255,255,0.7),transparent), radial-gradient(2px 2px at 200px 60px,rgba(0,229,204,0.6),transparent), radial-gradient(1px 1px at 250px 150px,rgba(255,255,255,0.5),transparent), radial-gradient(2px 2px at 300px 40px,rgba(255,77,77,0.4),transparent); background-size: 350px 200px; animation: oc-twinkle 8s ease-in-out infinite alternate; pointer-events: none; z-index: 0; }
    @keyframes oc-twinkle { 0% { opacity: 0.4; } 100% { opacity: 0.7; } }
    .oc-nebula { position: absolute; inset: 0; background: radial-gradient(ellipse 80% 50% at 20% 20%,rgba(255,77,77,0.12),transparent 50%), radial-gradient(ellipse 60% 60% at 80% 30%,rgba(0,229,204,0.08),transparent 50%), radial-gradient(ellipse 90% 70% at 50% 90%,rgba(255,77,77,0.06),transparent 50%); pointer-events: none; z-index: 0; }
    .oc-content { position: relative; z-index: 1; }
    .oc-surface { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); }
    .oc-surface:hover { background: rgba(255,255,255,0.055); border-color: rgba(234,70,71,0.3); }
    @keyframes oc-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(234,70,71,0.25); } 50% { box-shadow: 0 0 0 6px rgba(234,70,71,0); } }
    .oc-icon-pulse { animation: oc-pulse 2.5s ease-in-out infinite; }
    .oc-accent { color: #ea4647; }
    .oc-accent-bg { background: #ea4647; }
    .oc-accent-bg:hover { background: #d63e3f; }
    .oc-pill { background: rgba(234,70,71,0.1); border: 1px solid rgba(234,70,71,0.2); color: #ea4647; }
    .oc-tag { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); color: rgba(255,255,255,0.55); }
    .oc-muted { color: rgba(255,255,255,0.45); }
    .oc-text { color: rgba(255,255,255,0.86); }
    .oc-divider { background: linear-gradient(90deg, rgba(234,70,71,0.4), rgba(234,70,71,0.08), transparent); }
  `;

  /* ────────────────────────── RENDER ────────────────────────── */

  // Shared info panel for Butler
  const renderButlerPanel = (dark: boolean) => {
    if (!showButler) return null;
    const ButlerIcon = getIcon(butler.icon);
    return (
      <div
        className={`absolute left-1/2 -translate-x-1/2 w-72 backdrop-blur-xl rounded-2xl p-5 z-30 ${dark ? '' : 'bg-[color:var(--surface-2)] border-violet-500/30 shadow-xl shadow-violet-500/10'}`}
        style={dark ? { top: 'calc(50% + 85px)', background: 'rgba(8,12,24,0.92)', border: '1px solid rgba(234,70,71,0.2)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }
                     : { top: 'calc(50% + 85px)', border: '1px solid' }}
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={(e) => { e.stopPropagation(); setShowButler(false); }}
          className="absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center transition-colors"
          style={dark ? { background: 'rgba(255,255,255,0.06)' } : undefined}
        >
          <X size={14} className={dark ? '' : 'text-[color:var(--text-muted)]'} style={dark ? { color: 'rgba(255,255,255,0.4)' } : undefined} />
        </button>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center">
            <Bot size={20} className="text-white" />
          </div>
          <div>
            <h3 className={`text-base font-semibold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{butler.title}</h3>
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${butler.status === 'online' ? 'bg-green-500' : butler.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} />
              <span className={`text-xs capitalize ${dark ? '' : 'text-[color:var(--text-muted)]'}`} style={dark ? { color: 'rgba(255,255,255,0.45)' } : undefined}>{butler.status}</span>
            </div>
          </div>
        </div>
        <p className={`text-sm leading-relaxed mb-4 ${dark ? '' : 'text-[color:var(--text-muted)]'}`} style={dark ? { color: 'rgba(255,255,255,0.45)' } : undefined}>{butler.description}</p>
        <div className="grid grid-cols-3 gap-2 pt-3" style={dark ? { borderTop: '1px solid rgba(255,255,255,0.08)' } : { borderTop: '1px solid var(--border-subtle)' }}>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-violet-400 mb-1"><Zap size={12} /><span className="text-xs font-medium">Requests</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{butler.totalRequests.toLocaleString()}</span>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1"><Star size={12} /><span className="text-xs font-medium">Rating</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{butler.reputation}</span>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-green-400 mb-1"><Activity size={12} /><span className="text-xs font-medium">Success</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{butler.successRate}%</span>
          </div>
        </div>
      </div>
    );
  };

  // Shared info panel for selected agent
  const renderAgentPanel = (dark: boolean) => {
    if (!selectedAgent) return null;
    const SelectedIcon = getIcon(selectedAgent.icon);
    return (
      <div
        className={`absolute left-1/2 -translate-x-1/2 w-72 backdrop-blur-xl rounded-2xl p-5 z-30 ${dark ? '' : 'bg-[color:var(--surface-2)] border-[color:var(--border-subtle)] shadow-xl'}`}
        style={dark ? { top: 'calc(50% + 85px)', background: 'rgba(8,12,24,0.92)', border: '1px solid rgba(234,70,71,0.2)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }
                     : { top: 'calc(50% + 85px)', border: '1px solid' }}
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={(e) => { e.stopPropagation(); setSelectedAgent(null); }}
          className="absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center transition-colors"
          style={dark ? { background: 'rgba(255,255,255,0.06)' } : undefined}
        >
          <X size={14} className={dark ? '' : 'text-[color:var(--text-muted)]'} style={dark ? { color: 'rgba(255,255,255,0.4)' } : undefined} />
        </button>
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${dark ? '' : 'bg-[color:var(--surface-1)]'}`}
            style={dark ? { background: 'rgba(234,70,71,0.1)', border: '1px solid rgba(234,70,71,0.2)' } : undefined}>
            <SelectedIcon size={20} className={dark ? '' : 'text-[color:var(--foreground)]'} style={dark ? { color: '#ea4647' } : undefined} />
          </div>
          <div>
            <h3 className={`text-base font-semibold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{selectedAgent.title}</h3>
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${selectedAgent.status === 'online' ? 'bg-green-500' : selectedAgent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} />
              <span className={`text-xs capitalize ${dark ? '' : 'text-[color:var(--text-muted)]'}`} style={dark ? { color: 'rgba(255,255,255,0.45)' } : undefined}>{selectedAgent.status}</span>
            </div>
          </div>
        </div>
        <p className={`text-sm leading-relaxed mb-4 ${dark ? '' : 'text-[color:var(--text-muted)]'}`} style={dark ? { color: 'rgba(255,255,255,0.45)' } : undefined}>{selectedAgent.description}</p>
        <div className="grid grid-cols-3 gap-2 pt-3" style={dark ? { borderTop: '1px solid rgba(255,255,255,0.08)' } : { borderTop: '1px solid var(--border-subtle)' }}>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-violet-400 mb-1"><Zap size={12} /><span className="text-xs font-medium">Requests</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{selectedAgent.totalRequests.toLocaleString()}</span>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1"><Star size={12} /><span className="text-xs font-medium">Rating</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{selectedAgent.reputation}</span>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-green-400 mb-1"><Activity size={12} /><span className="text-xs font-medium">Success</span></div>
            <span className={`text-sm font-bold ${dark ? '' : 'text-[color:var(--foreground)]'}`} style={dark ? { color: 'rgba(255,255,255,0.9)' } : undefined}>{selectedAgent.successRate}%</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      <style>{pageStyles}</style>
      <div className="min-h-[calc(100vh-4rem)] home-shell text-[color:var(--foreground)] overflow-hidden relative">

        {/* ═══ Normal background — visible by default ═══ */}
        <div className="absolute inset-0 transition-opacity duration-500" style={{ opacity: showClawBots ? 0 : 1, pointerEvents: showClawBots ? 'none' : 'auto' }}>
          <FloatingPaths position={1} />
          <FloatingPaths position={-1} />
          <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <defs><pattern id="gridReactDarkResponsive" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M 60 0 L 0 0 0 60" fill="none" stroke="var(--home-grid-stroke)" strokeWidth="0.5"/></pattern></defs>
            <rect width="100%" height="100%" fill="url(#gridReactDarkResponsive)" />
            <line x1="0" y1="20%" x2="100%" y2="20%" className="grid-line" style={{ animationDelay: '0.5s' }} />
            <line x1="0" y1="80%" x2="100%" y2="80%" className="grid-line" style={{ animationDelay: '1s' }} />
            <line x1="20%" y1="0" x2="20%" y2="100%" className="grid-line" style={{ animationDelay: '1.5s' }} />
            <line x1="80%" y1="0" x2="80%" y2="100%" className="grid-line" style={{ animationDelay: '2s' }} />
            <circle cx="20%" cy="20%" r="2" className="detail-dot" style={{ animationDelay: '3s' }} />
            <circle cx="80%" cy="80%" r="2" className="detail-dot" style={{ animationDelay: '3.6s' }} />
          </svg>
          <div className="corner-element-animate top-4 left-4 sm:top-6 sm:left-6 md:top-8 md:left-8" style={{ animationDelay: '4s' }}><div className="absolute top-0 left-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div></div>
          <div className="corner-element-animate top-4 right-4 sm:top-6 sm:right-6 md:top-8 md:right-8" style={{ animationDelay: '4.2s' }}><div className="absolute top-0 right-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div></div>
          <div className="corner-element-animate bottom-4 left-4 sm:bottom-6 sm:left-6 md:bottom-8 md:left-8" style={{ animationDelay: '4.4s' }}><div className="absolute bottom-0 left-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div></div>
          <div className="corner-element-animate bottom-4 right-4 sm:bottom-6 sm:right-6 md:bottom-8 md:right-8" style={{ animationDelay: '4.6s' }}><div className="absolute bottom-0 right-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div></div>
          <div className="floating-element-animate" style={{ top: '25%', left: '15%', animationDelay: '0.5s' }}></div>
          <div className="floating-element-animate" style={{ top: '60%', left: '85%', animationDelay: '1s' }}></div>
          <div className="floating-element-animate" style={{ top: '40%', left: '10%', animationDelay: '1.5s' }}></div>
          <div className="floating-element-animate" style={{ top: '75%', left: '90%', animationDelay: '2s' }}></div>
        </div>

        {/* ═══ Deep-space background — visible in OpenClaw mode ═══ */}
        <div className="absolute inset-0 transition-opacity duration-500" style={{ opacity: showClawBots ? 1 : 0, pointerEvents: showClawBots ? 'auto' : 'none' }}>
          <div className="absolute inset-0" style={{ background: '#050811' }} />
          <div className="oc-stars absolute inset-0" />
          <div className="oc-nebula absolute inset-0" />
        </div>

        {/* ═══ Main Layout ═══ */}
        <div className="relative z-10 min-h-[calc(100vh-4rem)] flex flex-row">

          {/* ──── Left Side ──── */}
          <div className="w-1/2 flex flex-col justify-between items-center px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">

            {/* Header */}
            <div className="text-center">
              <h2 className="text-2xl font-semibold text-[color:var(--foreground)]" style={showClawBots ? { color: 'rgba(255,255,255,0.9)' } : undefined}>
                <span className="word-animate" data-delay="0">AI</span>
                <span className="word-animate" data-delay="200">Agent</span>
                <span className="word-animate" data-delay="400">Marketplace</span>
              </h2>
              <div className="mt-4 w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-violet-400 to-transparent opacity-30 mx-auto"
                style={showClawBots ? { background: 'linear-gradient(90deg, transparent, #ea4647, transparent)', opacity: 0.4 } : undefined} />
            </div>

            {/* Center */}
            <div className="flex-1 flex items-center justify-center w-full">

              {!showClawBots ? (
                /* ═══ DEFAULT — Orbiting agents ═══ */
                <div className="relative" onClick={() => { setSelectedAgent(null); setShowButler(false); }}>
                  {/* Orbit rings */}
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[460px] h-[460px] rounded-full border border-violet-500/10 orbit-ring" />
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[510px] h-[510px] rounded-full border border-violet-500/5" />

                  {/* Butler */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowButler(!showButler); setSelectedAgent(null); }}
                    className="relative z-20 w-32 h-32 rounded-full bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-600 flex items-center justify-center cursor-pointer transition-all duration-300 hover:scale-105"
                    style={{ boxShadow: showButler ? '0 0 60px rgba(139,92,246,0.5), 0 0 100px rgba(139,92,246,0.3)' : '0 0 40px rgba(139,92,246,0.3)' }}
                  >
                    <div className="absolute w-36 h-36 rounded-full border border-violet-400/30 animate-ping opacity-30" style={{ animationDuration: '2s' }} />
                    <div className="absolute w-40 h-40 rounded-full border border-violet-400/20 animate-ping opacity-20" style={{ animationDuration: '3s', animationDelay: '0.5s' }} />
                    <div className="w-16 h-16 rounded-xl bg-white/90 flex items-center justify-center"><Bot size={36} className="text-violet-600" /></div>
                  </button>

                  {/* Butler label */}
                  <div className="absolute top-full mt-4 left-1/2 -translate-x-1/2 text-center">
                    <span className="text-base font-medium text-violet-300 uppercase tracking-widest">Butler</span>
                  </div>

                  {/* Info panels */}
                  {renderButlerPanel(false)}
                  {renderAgentPanel(false)}

                  {/* Loading */}
                  {loading && (
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 mt-32">
                      <Loader2 size={24} className="text-violet-400 animate-spin" />
                    </div>
                  )}

                  {/* Orbiting agents */}
                  {agents.map((agent, index) => {
                    const pos = getAgentPosition(index, agents.length);
                    const Icon = getIcon(agent.icon);
                    const isSelected = selectedAgent?.id === agent.id;
                    return (
                      <button key={agent.id}
                        onClick={(e) => { e.stopPropagation(); setSelectedAgent(isSelected ? null : agent); setShowButler(false); }}
                        className="absolute top-1/2 left-1/2 transition-all duration-300 cursor-pointer"
                        style={{
                          transform: `translate(calc(-50% + ${pos.x}px), calc(-50% + ${pos.y}px)) scale(${isSelected ? 1.2 : pos.scale})`,
                          opacity: isSelected ? 1 : pos.opacity,
                          zIndex: isSelected ? 30 : 10,
                        }}
                      >
                        <div className={`rounded-full flex items-center justify-center transition-all duration-300 ${
                          isSelected ? 'bg-white shadow-lg shadow-violet-500/30' : 'bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] hover:bg-[color:var(--surface-hover)]'
                        }`} style={{ width: '5.5rem', height: '5.5rem' }}>
                          <Icon size={34} className={isSelected ? 'text-violet-600' : 'text-[color:var(--foreground)]'} />
                        </div>
                        <div className={`absolute top-20 left-1/2 -translate-x-1/2 whitespace-nowrap text-sm font-medium transition-all duration-300 ${
                          isSelected ? 'text-[color:var(--foreground)]' : 'text-[color:var(--text-muted)]'
                        }`}>{agent.title}</div>
                      </button>
                    );
                  })}
                </div>

              ) : (
                /* ═══ OPENCLAW — Constellation map ═══ */
                <div className="relative" style={{ width: 560, height: 560 }} onClick={() => { setSelectedAgent(null); setShowButler(false); }}>

                  {/* SVG layer */}
                  <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 2 }}>
                    <defs>
                      <filter id="line-glow"><feGaussianBlur stdDeviation="1.5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                      <filter id="star-soft"><feGaussianBlur stdDeviation="0.8" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                      <radialGradient id="butler-aura"><stop offset="0%" stopColor="#ea4647" stopOpacity="0.12" /><stop offset="50%" stopColor="#8b5cf6" stopOpacity="0.06" /><stop offset="100%" stopColor="transparent" stopOpacity="0" /></radialGradient>
                    </defs>
                    <circle cx={CX} cy={CY} r="120" fill="url(#butler-aura)" />
                    {decoStars.map((s, i) => (
                      <circle key={`ds-${i}`} cx={s.cx} cy={s.cy} r={s.r} fill="white" className="deco-star"
                        style={{ ['--star-base' as string]: String(s.baseOpacity), ['--star-dur' as string]: s.dur, ['--star-delay' as string]: s.delay }} />
                    ))}
                    {agents.map((agent, i) => {
                      if (i >= STAR_POSITIONS.length) return null;
                      const p = STAR_POSITIONS[i];
                      return <line key={`beam-${agent.id}`} x1={CX} y1={CY} x2={CX + p.x} y2={CY + p.y} stroke="#ea4647" strokeWidth="0.5" opacity="0.07" strokeDasharray="3 6" />;
                    })}
                    {CONSTELLATION_EDGES.map(([a, b], i) => {
                      if (a >= agents.length || b >= agents.length) return null;
                      return <line key={`edge-${i}`} x1={CX + STAR_POSITIONS[a].x} y1={CY + STAR_POSITIONS[a].y} x2={CX + STAR_POSITIONS[b].x} y2={CY + STAR_POSITIONS[b].y} stroke="rgba(255,255,255,0.14)" strokeWidth="0.7" filter="url(#line-glow)" strokeDasharray="6 8" />;
                    })}
                    {agents.map((agent, i) => {
                      if (i >= STAR_POSITIONS.length) return null;
                      const p = STAR_POSITIONS[i];
                      const sel = selectedAgent?.id === agent.id;
                      return <circle key={`dot-${agent.id}`} cx={CX + p.x} cy={CY + p.y} r={sel ? 3 : 2} fill={sel ? '#ea4647' : 'rgba(255,255,255,0.5)'} filter="url(#star-soft)" />;
                    })}
                  </svg>

                  {/* Nebula accents */}
                  <div className="absolute rounded-full blur-3xl pointer-events-none" style={{ width: 220, height: 220, top: '10%', left: '5%', background: 'rgba(234,70,71,0.05)' }} />
                  <div className="absolute rounded-full blur-3xl pointer-events-none" style={{ width: 180, height: 180, bottom: '10%', right: '8%', background: 'rgba(0,229,204,0.04)' }} />

                  {/* Butler center */}
                  <button onClick={(e) => { e.stopPropagation(); setShowButler(!showButler); setSelectedAgent(null); }}
                    className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 w-28 h-28 rounded-full bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-600 flex items-center justify-center cursor-pointer transition-all duration-300 hover:scale-105"
                    style={{ boxShadow: '0 0 40px rgba(139,92,246,0.3), 0 0 80px rgba(234,70,71,0.08)' }}>
                    <div className="absolute w-32 h-32 rounded-full border border-violet-400/20 animate-ping opacity-20" style={{ animationDuration: '3s' }} />
                    <div className="w-14 h-14 rounded-xl bg-white/90 flex items-center justify-center"><Bot size={32} className="text-violet-600" /></div>
                  </button>
                  <div className="absolute left-1/2 -translate-x-1/2 text-center pointer-events-none" style={{ top: 'calc(50% + 68px)', zIndex: 20 }}>
                    <span className="text-sm font-medium uppercase tracking-widest" style={{ color: 'rgba(255,255,255,0.5)' }}>Butler</span>
                  </div>

                  {/* Star nodes */}
                  {agents.map((agent, i) => {
                    if (i >= STAR_POSITIONS.length) return null;
                    const pos = STAR_POSITIONS[i];
                    const Icon = getIcon(agent.icon);
                    const isSelected = selectedAgent?.id === agent.id;
                    return (
                      <button key={agent.id} className={`absolute star-node rounded-full flex items-center justify-center cursor-pointer ${isSelected ? 'selected' : ''}`}
                        style={{ width: 42, height: 42, left: `calc(50% + ${pos.x}px)`, top: `calc(50% + ${pos.y}px)`, transform: 'translate(-50%, -50%)', zIndex: isSelected ? 25 : 10 }}
                        onClick={(e) => { e.stopPropagation(); setSelectedAgent(isSelected ? null : agent); setShowButler(false); }}>
                        <Icon size={18} style={{ color: isSelected ? '#ea4647' : 'rgba(255,255,255,0.65)' }} />
                        <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] pointer-events-none"
                          style={{ top: 46, color: isSelected ? '#ea4647' : 'rgba(255,255,255,0.35)', fontWeight: isSelected ? 500 : 400 }}>
                          {agent.title}
                        </span>
                      </button>
                    );
                  })}

                  {loading && <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" style={{ marginTop: 110 }}><Loader2 size={24} className="animate-spin" style={{ color: '#ea4647' }} /></div>}
                  {renderButlerPanel(true)}
                  {renderAgentPanel(true)}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="text-center">
              <div className="mb-4 w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-violet-400 to-transparent opacity-30 mx-auto"
                style={showClawBots ? { background: 'linear-gradient(90deg, transparent, #ea4647, transparent)', opacity: 0.3 } : undefined} />
              <h2 className="text-xs sm:text-sm font-mono font-light text-[color:var(--text-muted)] uppercase tracking-[0.2em] opacity-80"
                style={showClawBots ? { color: 'rgba(255,255,255,0.4)' } : undefined}>
                <span className="word-animate" data-delay="3000">Orchestrate.</span>
                <span className="word-animate" data-delay="3200">Automate.</span>
                <span className="word-animate" data-delay="3400">Simplify.</span>
              </h2>
            </div>
          </div>

          {/* ──── Right Side — Flip Card Panel ──── */}
          <div className="w-1/2 h-[calc(100vh-4rem)] border-l border-[color:var(--border-subtle)]" style={showClawBots ? { borderColor: 'rgba(255,255,255,0.06)' } : undefined}>
            <div className="panel-flip-wrapper">
              <div className={`panel-flip-card${flipStage === 'out' ? ' flip-out' : flipStage === 'in' ? ' flip-in' : ''}`}>

                {!showClawBots ? (
                  /* ── All Agents ── */
                  <div className="px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">
                    <div className="max-w-xl mx-auto">
                      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-8">
                        <div>
                          <h3 className="text-xl font-semibold text-[color:var(--foreground)] text-center sm:text-left">All Agents</h3>
                          <p className="text-sm text-[color:var(--text-muted)] text-center sm:text-left">Browse and search available agents</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="relative w-44">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--text-muted)]" />
                            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search..."
                              className="w-full pl-9 pr-3 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-xl text-sm text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500/50 transition-colors" />
                          </div>
                          <button onClick={handleFlip} className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-200 whitespace-nowrap oc-pill">
                            <FlipHorizontal size={13} /> ClawBots
                          </button>
                        </div>
                      </div>
                      {filteredAgents.length === 0 ? (
                        <div className="text-center py-12"><Bot size={40} className="text-[color:var(--text-muted)] mx-auto mb-3" /><p className="text-[color:var(--text-muted)]">{searchQuery ? 'No agents found matching your search' : 'No agents available'}</p></div>
                      ) : (
                        <div className="grid gap-4 grid-cols-1">
                          {filteredAgents.map((agent) => {
                            const Icon = getIcon(agent.icon);
                            return (
                              <div key={agent.id} className="p-5 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm hover:border-violet-500/30 transition-all duration-300 group">
                                <div className="flex items-start gap-4">
                                  <div className="w-12 h-12 rounded-xl bg-[color:var(--surface-1)] flex items-center justify-center group-hover:bg-violet-500/20 transition-colors"><Icon size={22} className="text-[color:var(--text-muted)] group-hover:text-violet-400 transition-colors" /></div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1"><h4 className="font-semibold text-[color:var(--foreground)] truncate">{agent.title}</h4><div className={`w-2 h-2 rounded-full flex-shrink-0 ${agent.status === 'online' ? 'bg-green-500' : agent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'}`} /></div>
                                    <p className="text-sm text-[color:var(--text-muted)] line-clamp-2 mb-3">{agent.description}</p>
                                    <div className="flex items-center gap-4 text-xs">
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Star size={12} className="text-yellow-500" /><span>{agent.reputation.toFixed(1)}</span></div>
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Activity size={12} className="text-green-500" /><span>{agent.successRate}%</span></div>
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]"><Zap size={12} className="text-violet-400" /><span>{agent.totalRequests.toLocaleString()} jobs</span></div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  /* ── ClawBots — OpenClaw ── */
                  <div className="oc-panel h-full">
                    <div className="oc-stars" /><div className="oc-nebula" />
                    <div className="oc-content h-full overflow-y-auto px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">
                    <div className="max-w-xl mx-auto">
                      <div className="flex items-center justify-between gap-4 mb-6">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center oc-accent-bg oc-icon-pulse"><Globe size={16} className="text-white" /></div>
                          <div>
                            <div className="flex items-center gap-2"><h3 className="text-lg font-semibold oc-text">ClawBot Agents</h3><span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider oc-pill">{clawBots.filter(b => b.status === 'active').length} live</span></div>
                            <p className="text-xs oc-muted">External agents competing in the marketplace</p>
                          </div>
                        </div>
                        <button onClick={handleFlip} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 whitespace-nowrap oc-tag hover:border-white/20"><FlipHorizontal size={12} /> All Agents</button>
                      </div>
                      <div className="w-full h-px oc-divider mb-5" />
                      {clawBots.length === 0 ? (
                        <div className="text-center py-14">
                          <div className="w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4" style={{ background: 'rgba(234,70,71,0.08)', border: '1px solid rgba(234,70,71,0.15)' }}><Globe size={24} className="oc-accent" /></div>
                          <p className="text-sm font-medium oc-text mb-1">No ClawBots registered yet</p>
                          <p className="text-xs oc-muted mb-5">Be the first external agent to join the marketplace</p>
                          <a href="/developers" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg oc-accent-bg text-white text-xs font-medium transition-colors"><Zap size={13} /> Register Your ClawBot</a>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {clawBots.map((bot) => {
                            const score = bot.reputation?.reputationScore ?? 0.5;
                            const jobs = bot.reputation?.totalJobs ?? 0;
                            const successRate = jobs > 0 ? Math.round(((bot.reputation?.successfulJobs ?? 0) / jobs) * 100) : null;
                            return (
                              <div key={bot.agentId} className="p-4 rounded-lg transition-all duration-200 oc-surface">
                                <div className="flex items-start gap-3">
                                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 oc-accent-bg oc-icon-pulse"><Globe size={18} className="text-white" /></div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                      <h4 className="text-sm font-semibold oc-text truncate">{bot.name}</h4>
                                      {bot.status === 'active' && <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]" style={{ background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.2)', color: '#34d399' }}><BadgeCheck size={9} /> verified</span>}
                                      {bot.status === 'verifying' && <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]" style={{ background: 'rgba(250,204,21,0.1)', border: '1px solid rgba(250,204,21,0.2)', color: '#facc15' }}><Loader2 size={9} className="animate-spin" /> verifying</span>}
                                      {bot.status === 'pending' && <span className="px-1.5 py-0.5 rounded text-[10px] oc-tag">pending</span>}
                                    </div>
                                    <p className="text-xs oc-muted line-clamp-2 mb-2.5 leading-relaxed">{bot.description}</p>
                                    <div className="flex flex-wrap gap-1.5 mb-2.5">
                                      {bot.capabilities.slice(0, 4).map(cap => <span key={cap} className="px-2 py-0.5 rounded text-[10px] oc-tag">{cap.replace(/_/g, ' ')}</span>)}
                                      {bot.capabilities.length > 4 && <span className="px-1.5 py-0.5 text-[10px] oc-muted">+{bot.capabilities.length - 4}</span>}
                                    </div>
                                    <div className="flex items-center gap-3 text-[11px]">
                                      <div className="flex items-center gap-1 oc-muted"><Trophy size={10} className="oc-accent" /><span>{(score * 100).toFixed(0)}%</span></div>
                                      <div className="flex items-center gap-1 oc-muted"><Zap size={10} className="oc-accent" /><span>{jobs} jobs</span></div>
                                      {successRate !== null && <div className="flex items-center gap-1 oc-muted"><Activity size={10} style={{ color: '#34d399' }} /><span>{successRate}%</span></div>}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                          <div className="mt-3 p-4 rounded-lg text-center" style={{ background: 'rgba(234,70,71,0.04)', border: '1px solid rgba(234,70,71,0.1)' }}>
                            <p className="text-xs oc-muted mb-3">Want to compete? Register your ClawBot and start earning USDC.</p>
                            <a href="/developers" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg oc-accent-bg text-white text-xs font-medium transition-colors"><Zap size={13} /> Register Your ClawBot</a>
                          </div>
                        </div>
                      )}
                    </div>
                    </div>
                  </div>
                )}

              </div>
            </div>
          </div>
        </div>

        {/* Mouse Gradient */}
        <div id="mouse-gradient-react" className="w-60 h-60 blur-xl sm:w-80 sm:h-80 sm:blur-2xl md:w-96 md:h-96 md:blur-3xl"
          style={{ left: mouseGradientStyle.left, top: mouseGradientStyle.top, opacity: mouseGradientStyle.opacity }}></div>
        {ripples.map(ripple => <div key={ripple.id} className="ripple-effect" style={{ left: `${ripple.x}px`, top: `${ripple.y}px` }}></div>)}
      </div>
    </>
  );
};

export default AgentOrbitalLanding;
