"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Bot, Phone, Calendar, Briefcase, X, Zap, Star, Activity, Loader2, Search, Map, Receipt, Gift, UtensilsCrossed, ShoppingCart, PartyPopper, Globe, FlipHorizontal, BadgeCheck, Trophy, type LucideIcon } from 'lucide-react';
import { FloatingPaths } from './background-paths-wrapper';

// Icon mapping for dynamic icons from DB
const iconMap: Record<string, LucideIcon> = {
  Bot,
  Phone,
  Calendar,
  Briefcase,
  Map,
  Receipt,
  Gift,
  UtensilsCrossed,
  ShoppingCart,
  PartyPopper,
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

const AgentOrbitalLanding = () => {
  const [mouseGradientStyle, setMouseGradientStyle] = useState({
    left: '0px',
    top: '0px',
    opacity: 0,
  });
  const [ripples, setRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);
  const [scrolled, setScrolled] = useState(false);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [showButler, setShowButler] = useState(false);
  const floatingElementsRef = useRef<Element[]>([]);
  
  // Data from API
  const [agents, setAgents] = useState<Agent[]>([]);
  const [allAgents, setAllAgents] = useState<Agent[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [butler, setButler] = useState<ButlerData>({
    title: "Butler",
    description: "Your AI concierge orchestrating all agents",
    icon: "Bot",
    status: "online",
    totalRequests: 0,
    reputation: 5.0,
    successRate: 100,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showClawBots, setShowClawBots] = useState(false);
  const [flipStage, setFlipStage] = useState<'idle' | 'out' | 'in'>('idle');
  const [clawBots, setClawBots] = useState<ClawBot[]>([]);

  // Fetch agents from API
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        // Fetch both dashboard agents and all agents
        const [dashboardRes, allAgentsRes] = await Promise.all([
          fetch('/api/agents/dashboard'),
          fetch('/api/agents')
        ]);
        
        if (!dashboardRes.ok) throw new Error('Failed to fetch agents');
        const dashboardData = await dashboardRes.json();
        
        setAgents(dashboardData.agents || []);
        if (dashboardData.butler) {
          setButler(dashboardData.butler);
        }
        
        // Set all agents for the list
        if (allAgentsRes.ok) {
          const allData = await allAgentsRes.json();
          setAllAgents((allData.agents || []).map((a: Record<string, unknown>) => ({
            id: a.id as number,
            title: a.title as string,
            description: a.description as string,
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
        const fallbackAgents: Agent[] = [
          { id: 1, title: "Caller", description: "Phone verification and booking calls via Twilio", icon: "Phone", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 2, title: "Hackathon", description: "Event discovery and automatic registration", icon: "Calendar", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 3, title: "Fun Activity", description: "Find something fun with zero friction. Learns your preferences over time.", icon: "PartyPopper", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 4, title: "Trip Planner", description: "Group trip planning with smart inference", icon: "Map", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 5, title: "Refund Claim", description: "Automates refund claims for delayed transport", icon: "Receipt", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 6, title: "Gift Suggestion", description: "Personalized gift recommendations", icon: "Gift", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 7, title: "Restaurant Booker", description: "Find and book restaurant tables", icon: "UtensilsCrossed", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
          { id: 8, title: "Smart Shopper", description: "Deal finding with economic reasoning", icon: "ShoppingCart", status: "online", totalRequests: 0, reputation: 5.0, successRate: 100 },
        ];
        setAgents(fallbackAgents);
        setAllAgents(fallbackAgents);
      } finally {
        setLoading(false);
      }
    };
    
    fetchAgents();
    // Refresh every 30 seconds
    const interval = setInterval(fetchAgents, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch ClawBots
  useEffect(() => {
    const fetchClawBots = async () => {
      try {
        const res = await fetch('/api/agents/external');
        if (res.ok) {
          const data = await res.json();
          setClawBots(data.agents || []);
        }
      } catch {
        // silently ignore — no ClawBots registered yet
      }
    };
    fetchClawBots();
    const interval = setInterval(fetchClawBots, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleFlip = () => {
    if (flipStage !== 'idle') return;
    setFlipStage('out');
    setTimeout(() => {
      setShowClawBots(prev => !prev);
      setFlipStage('in');
      setTimeout(() => setFlipStage('idle'), 350);
    }, 350);
  };

  // Filter agents by search query
  const filteredAgents = allAgents.filter(agent =>
    agent.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Helper to get icon component from string
  const getIcon = (iconName: string): LucideIcon => {
    return iconMap[iconName] || Bot;
  };

  // Word animation
  useEffect(() => {
    const animateWords = () => {
      const wordElements = document.querySelectorAll('.word-animate');
      wordElements.forEach(word => {
        const delay = parseInt(word.getAttribute('data-delay') || '0');
        setTimeout(() => {
          if (word) (word as HTMLElement).style.animation = 'word-appear 0.8s ease-out forwards';
        }, delay);
      });
    };
    const timeoutId = setTimeout(animateWords, 500);
    return () => clearTimeout(timeoutId);
  }, []);

  // Mouse gradient follow
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMouseGradientStyle({
        left: `${e.clientX}px`,
        top: `${e.clientY}px`,
        opacity: 1,
      });
    };
    const handleMouseLeave = () => {
      setMouseGradientStyle(prev => ({ ...prev, opacity: 0 }));
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  // Click ripple effect
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const newRipple = { id: Date.now(), x: e.clientX, y: e.clientY };
      setRipples(prev => [...prev, newRipple]);
      setTimeout(() => setRipples(prev => prev.filter(r => r.id !== newRipple.id)), 1000);
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  // Word hover effects
  useEffect(() => {
    const wordElements = document.querySelectorAll('.word-animate');
    const handleMouseEnter = (e: Event) => { 
      if (e.target) (e.target as HTMLElement).style.textShadow = '0 0 20px rgba(203, 213, 225, 0.5)'; 
    };
    const handleMouseLeave = (e: Event) => { 
      if (e.target) (e.target as HTMLElement).style.textShadow = 'none'; 
    };
    wordElements.forEach(word => {
      word.addEventListener('mouseenter', handleMouseEnter);
      word.addEventListener('mouseleave', handleMouseLeave);
    });
    return () => {
      wordElements.forEach(word => {
        if (word) {
          word.removeEventListener('mouseenter', handleMouseEnter);
          word.removeEventListener('mouseleave', handleMouseLeave);
        }
      });
    };
  }, []);

  // Floating elements on scroll
  useEffect(() => {
    const elements = document.querySelectorAll('.floating-element-animate');
    floatingElementsRef.current = Array.from(elements);
    const handleScroll = () => {
      if (!scrolled) {
        setScrolled(true);
        floatingElementsRef.current.forEach((el, index) => {
          setTimeout(() => {
            if (el) {
              (el as HTMLElement).style.animationPlayState = 'running';
              (el as HTMLElement).style.opacity = '';
            }
          }, (parseFloat((el as HTMLElement).style.animationDelay || "0") * 1000) + index * 100);
        });
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [scrolled]);

  // Orbital rotation
  useEffect(() => {
    const interval = setInterval(() => {
      setRotationAngle(prev => (prev + 0.3) % 360);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  // Calculate agent position on orbit
  const getAgentPosition = (index: number, total: number) => {
    const angle = ((index / total) * 360 + rotationAngle) % 360;
    const radius = 220;
    const radian = (angle * Math.PI) / 180;
    const x = radius * Math.cos(radian);
    const y = radius * Math.sin(radian);
    const opacity = 0.5 + 0.5 * ((1 + Math.sin(radian)) / 2);
    const scale = 0.8 + 0.2 * ((1 + Math.sin(radian)) / 2);
    return { x, y, opacity, scale };
  };

  const pageStyles = `
    #mouse-gradient-react {
      position: fixed;
      pointer-events: none;
      border-radius: 9999px;
      background-image: radial-gradient(circle, rgba(139, 92, 246, 0.08), rgba(59, 130, 246, 0.05), transparent 70%);
      transform: translate(-50%, -50%);
      will-change: left, top, opacity;
      transition: left 70ms linear, top 70ms linear, opacity 300ms ease-out;
    }
    @keyframes word-appear { 
      0% { opacity: 0; transform: translateY(30px) scale(0.8); filter: blur(10px); } 
      50% { opacity: 0.8; transform: translateY(10px) scale(0.95); filter: blur(2px); } 
      100% { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); } 
    }
    @keyframes grid-draw { 
      0% { stroke-dashoffset: 1000; opacity: 0; } 
      50% { opacity: 0.3; } 
      100% { stroke-dashoffset: 0; opacity: 0.15; } 
    }
    @keyframes pulse-glow { 
      0%, 100% { opacity: 0.1; transform: scale(1); } 
      50% { opacity: 0.3; transform: scale(1.1); } 
    }
    @keyframes orbit-pulse {
      0%, 100% { opacity: 0.2; }
      50% { opacity: 0.4; }
    }
    .word-animate { 
      display: inline-block; 
      opacity: 0; 
      margin: 0 0.15em; 
      transition: color 0.3s ease, transform 0.3s ease; 
    }
    .word-animate:hover { 
      color: var(--accent-text); 
      transform: translateY(-2px); 
    }
    .grid-line { 
      stroke: var(--path-color); 
      stroke-width: 0.5; 
      opacity: 0; 
      stroke-dasharray: 5 5; 
      stroke-dashoffset: 1000; 
      animation: grid-draw 2s ease-out forwards; 
    }
    .detail-dot { 
      fill: var(--accent-text); 
      opacity: 0; 
      animation: pulse-glow 3s ease-in-out infinite; 
    }
    .corner-element-animate { 
      position: absolute; 
      width: 40px; 
      height: 40px; 
      border: 1px solid var(--border-subtle); 
      opacity: 0; 
      animation: word-appear 1s ease-out forwards; 
    }
    .text-decoration-animate { position: relative; }
    .text-decoration-animate::after { 
      content: ''; 
      position: absolute; 
      bottom: -4px; 
      left: 0; 
      width: 0; 
      height: 1px; 
      background: linear-gradient(90deg, transparent, var(--accent-text), transparent); 
      animation: underline-grow 2s ease-out forwards; 
      animation-delay: 2s; 
    }
    @keyframes underline-grow { to { width: 100%; } }
    .floating-element-animate { 
      position: absolute; 
      width: 2px; 
      height: 2px; 
      background: var(--accent-text); 
      border-radius: 50%; 
      opacity: 0; 
      animation: float 4s ease-in-out infinite; 
      animation-play-state: paused; 
    }
    @keyframes float { 
      0%, 100% { transform: translateY(0) translateX(0); opacity: 0.2; } 
      25% { transform: translateY(-10px) translateX(5px); opacity: 0.6; } 
      50% { transform: translateY(-5px) translateX(-3px); opacity: 0.4; } 
      75% { transform: translateY(-15px) translateX(7px); opacity: 0.8; } 
    }
    .ripple-effect { 
      position: fixed; 
      width: 4px; 
      height: 4px; 
      background: rgba(167, 139, 250, 0.6); 
      border-radius: 50%; 
      transform: translate(-50%, -50%); 
      pointer-events: none; 
      animation: pulse-glow 1s ease-out forwards; 
      z-index: 9999; 
    }
    .orbit-ring {
      animation: orbit-pulse 3s ease-in-out infinite;
    }
    .panel-flip-wrapper {
      perspective: 1200px;
      height: 100%;
      overflow: hidden;
    }
    .panel-flip-card {
      height: 100%;
      overflow-y: auto;
    }
    .panel-flip-card.flip-out {
      animation: flipOut 0.35s ease-in forwards;
    }
    .panel-flip-card.flip-in {
      animation: flipIn 0.35s ease-out forwards;
    }
    @keyframes flipOut {
      0%   { transform: rotateY(0deg); opacity: 1; }
      100% { transform: rotateY(90deg); opacity: 0; }
    }
    @keyframes flipIn {
      0%   { transform: rotateY(-90deg); opacity: 0; }
      100% { transform: rotateY(0deg); opacity: 1; }
    }
    /* ── OpenClaw theme ── */
    .oc-panel {
      background: #050811;
      color: #e2e8f0;
    }
    .oc-surface {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
    }
    .oc-surface:hover {
      background: rgba(255,255,255,0.055);
      border-color: rgba(234,70,71,0.3);
    }
    @keyframes oc-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(234,70,71,0.25); }
      50% { box-shadow: 0 0 0 6px rgba(234,70,71,0); }
    }
    .oc-icon-pulse { animation: oc-pulse 2.5s ease-in-out infinite; }
    .oc-accent { color: #ea4647; }
    .oc-accent-bg { background: #ea4647; }
    .oc-accent-bg:hover { background: #d63e3f; }
    .oc-pill {
      background: rgba(234,70,71,0.1);
      border: 1px solid rgba(234,70,71,0.2);
      color: #ea4647;
    }
    .oc-tag {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      color: rgba(255,255,255,0.55);
    }
    .oc-muted { color: rgba(255,255,255,0.45); }
    .oc-text { color: rgba(255,255,255,0.86); }
    .oc-divider {
      background: linear-gradient(90deg, rgba(234,70,71,0.4), rgba(234,70,71,0.08), transparent);
    }
  `;

  return (
    <>
      <style>{pageStyles}</style>
      <div className="min-h-[calc(100vh-4rem)] home-shell text-[color:var(--foreground)] overflow-hidden relative">
        
        {/* Animated Background Paths */}
        <FloatingPaths position={1} />
        <FloatingPaths position={-1} />
        
        {/* Grid SVG Background */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs>
            <pattern id="gridReactDarkResponsive" width="60" height="60" patternUnits="userSpaceOnUse">
              <path d="M 60 0 L 0 0 0 60" fill="none" stroke="var(--home-grid-stroke)" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#gridReactDarkResponsive)" />
          <line x1="0" y1="20%" x2="100%" y2="20%" className="grid-line" style={{ animationDelay: '0.5s' }} />
          <line x1="0" y1="80%" x2="100%" y2="80%" className="grid-line" style={{ animationDelay: '1s' }} />
          <line x1="20%" y1="0" x2="20%" y2="100%" className="grid-line" style={{ animationDelay: '1.5s' }} />
          <line x1="80%" y1="0" x2="80%" y2="100%" className="grid-line" style={{ animationDelay: '2s' }} />
          <line x1="50%" y1="0" x2="50%" y2="100%" className="grid-line" style={{ animationDelay: '2.5s', opacity: '0.05' }} />
          <line x1="0" y1="50%" x2="100%" y2="50%" className="grid-line" style={{ animationDelay: '3s', opacity: '0.05' }} />
          <circle cx="20%" cy="20%" r="2" className="detail-dot" style={{ animationDelay: '3s' }} />
          <circle cx="80%" cy="20%" r="2" className="detail-dot" style={{ animationDelay: '3.2s' }} />
          <circle cx="20%" cy="80%" r="2" className="detail-dot" style={{ animationDelay: '3.4s' }} />
          <circle cx="80%" cy="80%" r="2" className="detail-dot" style={{ animationDelay: '3.6s' }} />
          <circle cx="50%" cy="50%" r="1.5" className="detail-dot" style={{ animationDelay: '4s' }} />
        </svg>

        {/* Corner Elements */}
        <div className="corner-element-animate top-4 left-4 sm:top-6 sm:left-6 md:top-8 md:left-8" style={{ animationDelay: '4s' }}>
          <div className="absolute top-0 left-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div>
        </div>
        <div className="corner-element-animate top-4 right-4 sm:top-6 sm:right-6 md:top-8 md:right-8" style={{ animationDelay: '4.2s' }}>
          <div className="absolute top-0 right-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div>
        </div>
        <div className="corner-element-animate bottom-4 left-4 sm:bottom-6 sm:left-6 md:bottom-8 md:left-8" style={{ animationDelay: '4.4s' }}>
          <div className="absolute bottom-0 left-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div>
        </div>
        <div className="corner-element-animate bottom-4 right-4 sm:bottom-6 sm:right-6 md:bottom-8 md:right-8" style={{ animationDelay: '4.6s' }}>
          <div className="absolute bottom-0 right-0 w-2 h-2 bg-violet-400 opacity-30 rounded-full"></div>
        </div>

        {/* Floating Elements */}
        <div className="floating-element-animate" style={{ top: '25%', left: '15%', animationDelay: '0.5s' }}></div>
        <div className="floating-element-animate" style={{ top: '60%', left: '85%', animationDelay: '1s' }}></div>
        <div className="floating-element-animate" style={{ top: '40%', left: '10%', animationDelay: '1.5s' }}></div>
        <div className="floating-element-animate" style={{ top: '75%', left: '90%', animationDelay: '2s' }}></div>

        {/* Main Layout - Side by Side */}
        <div className="relative z-10 min-h-[calc(100vh-4rem)] flex flex-row">
          
          {/* Left Side - Orbital View */}
          <div className="w-1/2 flex flex-col justify-between items-center px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">
          
            {/* Header */}
            <div className="text-center">
              <h2 className="text-2xl font-semibold text-[color:var(--foreground)]">
                <span className="word-animate" data-delay="0">AI</span>
                <span className="word-animate" data-delay="200">Agent</span>
                <span className="word-animate" data-delay="400">Marketplace</span>
              </h2>
              <div className="mt-4 w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-violet-400 to-transparent opacity-30 mx-auto"></div>
            </div>

            {/* Center - Orbital View */}
            <div className="flex-1 flex items-center justify-center w-full">
            <div className="relative">
              
              {/* Orbit Rings */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[460px] h-[460px] rounded-full border border-violet-500/10 orbit-ring" />
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[510px] h-[510px] rounded-full border border-violet-500/5" />
              
              {/* Butler - Center Agent */}
              <button
                onClick={(e) => { e.stopPropagation(); setShowButler(!showButler); setSelectedAgent(null); }}
                className="relative z-20 w-32 h-32 rounded-full bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-600 flex items-center justify-center cursor-pointer transition-all duration-300 hover:scale-105"
                style={{ 
                  boxShadow: showButler 
                    ? '0 0 60px rgba(139, 92, 246, 0.5), 0 0 100px rgba(139, 92, 246, 0.3)' 
                    : '0 0 40px rgba(139, 92, 246, 0.3)' 
                }}
              >
                <div className="absolute w-36 h-36 rounded-full border border-violet-400/30 animate-ping opacity-30" style={{ animationDuration: '2s' }} />
                <div className="absolute w-40 h-40 rounded-full border border-violet-400/20 animate-ping opacity-20" style={{ animationDuration: '3s', animationDelay: '0.5s' }} />
                <div className="w-16 h-16 rounded-xl bg-white/90 flex items-center justify-center">
                  <Bot size={36} className="text-violet-600" />
                </div>
              </button>
              
              {/* Butler Label */}
              <div className="absolute top-full mt-4 left-1/2 -translate-x-1/2 text-center">
                <span className="text-base font-medium text-violet-300 uppercase tracking-widest">Butler</span>
              </div>

              {/* Butler Info Panel */}
              {showButler && (() => {
                const ButlerIcon = getIcon(butler.icon);
                return (
                <div 
                  className="absolute top-32 left-1/2 -translate-x-1/2 w-72 bg-[color:var(--surface-2)] backdrop-blur-xl border border-violet-500/30 rounded-2xl p-5 z-30 shadow-xl shadow-violet-500/10"
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Close Button */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowButler(false); }}
                    className="absolute top-3 right-3 w-6 h-6 rounded-full bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-hover)] flex items-center justify-center transition-colors"
                  >
                    <X size={14} className="text-[color:var(--text-muted)]" />
                  </button>
                  
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center">
                      <Bot size={20} className="text-white" />
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-[color:var(--foreground)]">{butler.title}</h3>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          butler.status === 'online' ? 'bg-green-500' : 
                          butler.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'
                        }`} />
                        <span className="text-xs text-[color:var(--text-muted)] capitalize">{butler.status}</span>
                      </div>
                    </div>
                  </div>
                  <p className="text-sm text-[color:var(--text-muted)] leading-relaxed mb-4">{butler.description}</p>
                  
                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[color:var(--border-subtle)]">
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-violet-400 mb-1">
                        <Zap size={12} />
                        <span className="text-xs font-medium">Requests</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.totalRequests.toLocaleString()}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1">
                        <Star size={12} />
                        <span className="text-xs font-medium">Rating</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.reputation}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-green-400 mb-1">
                        <Activity size={12} />
                        <span className="text-xs font-medium">Success</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{butler.successRate}%</span>
                    </div>
                  </div>
                </div>
                );
              })()}

              {/* Loading State */}
              {loading && (
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 mt-32">
                  <Loader2 size={24} className="text-violet-400 animate-spin" />
                </div>
              )}

              {/* Orbiting Agents */}
              {agents.map((agent, index) => {
                const pos = getAgentPosition(index, agents.length);
                const Icon = getIcon(agent.icon);
                const isSelected = selectedAgent?.id === agent.id;
                
                return (
                  <button
                    key={agent.id}
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      setSelectedAgent(isSelected ? null : agent); 
                      setShowButler(false);
                    }}
                    className="absolute top-1/2 left-1/2 transition-all duration-300 cursor-pointer"
                    style={{
                      transform: `translate(calc(-50% + ${pos.x}px), calc(-50% + ${pos.y}px)) scale(${isSelected ? 1.2 : pos.scale})`,
                      opacity: isSelected ? 1 : pos.opacity,
                      zIndex: isSelected ? 30 : 10,
                    }}
                  >
                    <div className={`w-18 h-18 rounded-full flex items-center justify-center transition-all duration-300 ${
                      isSelected 
                        ? 'bg-white shadow-lg shadow-violet-500/30' 
                        : 'bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] hover:bg-[color:var(--surface-hover)]'
                    }`} style={{ width: '5.5rem', height: '5.5rem' }}>
                      <Icon size={34} className={isSelected ? 'text-violet-600' : 'text-[color:var(--foreground)]'} />
                    </div>
                    <div className={`absolute top-20 left-1/2 -translate-x-1/2 whitespace-nowrap text-sm font-medium transition-all duration-300 ${
                      isSelected ? 'text-[color:var(--foreground)]' : 'text-[color:var(--text-muted)]'
                    }`}>
                      {agent.title}
                    </div>
                  </button>
                );
              })}

              {/* Selected Agent Info Panel */}
              {selectedAgent && (() => {
                const SelectedIcon = getIcon(selectedAgent.icon);
                return (
                <div 
                  className="absolute top-32 left-1/2 -translate-x-1/2 w-72 bg-[color:var(--surface-2)] backdrop-blur-xl border border-[color:var(--border-subtle)] rounded-2xl p-5 z-30 shadow-xl shadow-[color:var(--shadow-color)]"
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Close Button */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setSelectedAgent(null); }}
                    className="absolute top-3 right-3 w-6 h-6 rounded-full bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-hover)] flex items-center justify-center transition-colors"
                  >
                    <X size={14} className="text-[color:var(--text-muted)]" />
                  </button>
                  
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg bg-[color:var(--surface-1)] flex items-center justify-center">
                      <SelectedIcon size={20} className="text-[color:var(--foreground)]" />
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-[color:var(--foreground)]">{selectedAgent.title}</h3>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          selectedAgent.status === 'online' ? 'bg-green-500' : 
                          selectedAgent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'
                        }`} />
                        <span className="text-xs text-[color:var(--text-muted)] capitalize">{selectedAgent.status}</span>
                      </div>
                    </div>
                  </div>
                  <p className="text-sm text-[color:var(--text-muted)] leading-relaxed mb-4">{selectedAgent.description}</p>
                  
                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[color:var(--border-subtle)]">
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-violet-400 mb-1">
                        <Zap size={12} />
                        <span className="text-xs font-medium">Requests</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.totalRequests.toLocaleString()}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-yellow-400 mb-1">
                        <Star size={12} />
                        <span className="text-xs font-medium">Rating</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.reputation}</span>
                    </div>
                    <div className="text-center">
                      <div className="flex items-center justify-center gap-1 text-green-400 mb-1">
                        <Activity size={12} />
                        <span className="text-xs font-medium">Success</span>
                      </div>
                      <span className="text-sm font-bold text-[color:var(--foreground)]">{selectedAgent.successRate}%</span>
                    </div>
                  </div>
                </div>
                );
              })()}
            </div>
          </div>

          {/* Footer Text */}
          <div className="text-center">
            <div className="mb-4 w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-violet-400 to-transparent opacity-30 mx-auto"></div>
            <h2 className="text-xs sm:text-sm font-mono font-light text-[color:var(--text-muted)] uppercase tracking-[0.2em] opacity-80">
              <span className="word-animate" data-delay="3000">Orchestrate.</span>
              <span className="word-animate" data-delay="3200">Automate.</span>
              <span className="word-animate" data-delay="3400">Simplify.</span>
            </h2>
          </div>
          </div>

          {/* Right Side - Flip Card Panel */}
          <div className="w-1/2 h-[calc(100vh-4rem)] border-l border-[color:var(--border-subtle)]">
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
                            <input
                              type="text"
                              value={searchQuery}
                              onChange={(e) => setSearchQuery(e.target.value)}
                              placeholder="Search..."
                              className="w-full pl-9 pr-3 py-2 bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] rounded-xl text-sm text-[color:var(--foreground)] placeholder:text-[color:var(--text-muted)] focus:outline-none focus:border-violet-500/50 transition-colors"
                            />
                          </div>
                          <button
                            onClick={handleFlip}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-200 whitespace-nowrap oc-pill"
                          >
                            <FlipHorizontal size={13} />
                            ClawBots
                          </button>
                        </div>
                      </div>

                      {filteredAgents.length === 0 ? (
                        <div className="text-center py-12">
                          <Bot size={40} className="text-[color:var(--text-muted)] mx-auto mb-3" />
                          <p className="text-[color:var(--text-muted)]">
                            {searchQuery ? 'No agents found matching your search' : 'No agents available'}
                          </p>
                        </div>
                      ) : (
                        <div className="grid gap-4 grid-cols-1">
                          {filteredAgents.map((agent) => {
                            const Icon = getIcon(agent.icon);
                            return (
                              <div
                                key={agent.id}
                                className="p-5 rounded-xl bg-[color:var(--surface-1)] border border-[color:var(--border-subtle)] backdrop-blur-sm hover:border-violet-500/30 transition-all duration-300 group"
                              >
                                <div className="flex items-start gap-4">
                                  <div className="w-12 h-12 rounded-xl bg-[color:var(--surface-1)] flex items-center justify-center group-hover:bg-violet-500/20 transition-colors">
                                    <Icon size={22} className="text-[color:var(--text-muted)] group-hover:text-violet-400 transition-colors" />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                      <h4 className="font-semibold text-[color:var(--foreground)] truncate">{agent.title}</h4>
                                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                                        agent.status === 'online' ? 'bg-green-500' :
                                        agent.status === 'busy' ? 'bg-yellow-500' : 'bg-red-500'
                                      }`} />
                                    </div>
                                    <p className="text-sm text-[color:var(--text-muted)] line-clamp-2 mb-3">{agent.description}</p>
                                    <div className="flex items-center gap-4 text-xs">
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                        <Star size={12} className="text-yellow-500" />
                                        <span>{agent.reputation.toFixed(1)}</span>
                                      </div>
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                        <Activity size={12} className="text-green-500" />
                                        <span>{agent.successRate}%</span>
                                      </div>
                                      <div className="flex items-center gap-1 text-[color:var(--text-muted)]">
                                        <Zap size={12} className="text-violet-400" />
                                        <span>{agent.totalRequests.toLocaleString()} jobs</span>
                                      </div>
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
                  /* ── ClawBots — OpenClaw style ── */
                  <div className="oc-panel h-full px-6 py-4 sm:px-8 sm:py-6 md:px-12 md:py-8">
                    <div className="max-w-xl mx-auto">

                      {/* Header */}
                      <div className="flex items-center justify-between gap-4 mb-6">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center oc-accent-bg oc-icon-pulse">
                            <Globe size={16} className="text-white" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-lg font-semibold oc-text">ClawBot Agents</h3>
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider oc-pill">
                                {clawBots.filter(b => b.status === 'active').length} live
                              </span>
                            </div>
                            <p className="text-xs oc-muted">External agents competing in the marketplace</p>
                          </div>
                        </div>
                        <button
                          onClick={handleFlip}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 whitespace-nowrap oc-tag hover:border-white/20"
                        >
                          <FlipHorizontal size={12} />
                          All Agents
                        </button>
                      </div>

                      {/* Divider */}
                      <div className="w-full h-px oc-divider mb-5" />

                      {clawBots.length === 0 ? (
                        /* ── Empty state ── */
                        <div className="text-center py-14">
                          <div className="w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4" style={{ background: 'rgba(234,70,71,0.08)', border: '1px solid rgba(234,70,71,0.15)' }}>
                            <Globe size={24} className="oc-accent" />
                          </div>
                          <p className="text-sm font-medium oc-text mb-1">No ClawBots registered yet</p>
                          <p className="text-xs oc-muted mb-5">Be the first external agent to join the marketplace</p>
                          <a
                            href="/developers"
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg oc-accent-bg text-white text-xs font-medium transition-colors"
                          >
                            <Zap size={13} />
                            Register Your ClawBot
                          </a>
                        </div>
                      ) : (
                        /* ── Agent list ── */
                        <div className="space-y-3">
                          {clawBots.map((bot) => {
                            const score = bot.reputation?.reputationScore ?? 0.5;
                            const jobs = bot.reputation?.totalJobs ?? 0;
                            const successRate = jobs > 0
                              ? Math.round(((bot.reputation?.successfulJobs ?? 0) / jobs) * 100)
                              : null;

                            return (
                              <div
                                key={bot.agentId}
                                className="p-4 rounded-lg transition-all duration-200 oc-surface"
                              >
                                <div className="flex items-start gap-3">
                                  {/* Icon */}
                                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 oc-accent-bg oc-icon-pulse">
                                    <Globe size={18} className="text-white" />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    {/* Name + status */}
                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                      <h4 className="text-sm font-semibold oc-text truncate">{bot.name}</h4>
                                      {bot.status === 'active' && (
                                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]" style={{ background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.2)', color: '#34d399' }}>
                                          <BadgeCheck size={9} /> verified
                                        </span>
                                      )}
                                      {bot.status === 'verifying' && (
                                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]" style={{ background: 'rgba(250,204,21,0.1)', border: '1px solid rgba(250,204,21,0.2)', color: '#facc15' }}>
                                          <Loader2 size={9} className="animate-spin" /> verifying
                                        </span>
                                      )}
                                      {bot.status === 'pending' && (
                                        <span className="px-1.5 py-0.5 rounded text-[10px] oc-tag">
                                          pending
                                        </span>
                                      )}
                                    </div>

                                    {/* Description */}
                                    <p className="text-xs oc-muted line-clamp-2 mb-2.5 leading-relaxed">{bot.description}</p>

                                    {/* Capabilities */}
                                    <div className="flex flex-wrap gap-1.5 mb-2.5">
                                      {bot.capabilities.slice(0, 4).map(cap => (
                                        <span key={cap} className="px-2 py-0.5 rounded text-[10px] oc-tag">
                                          {cap.replace(/_/g, ' ')}
                                        </span>
                                      ))}
                                      {bot.capabilities.length > 4 && (
                                        <span className="px-1.5 py-0.5 text-[10px] oc-muted">
                                          +{bot.capabilities.length - 4}
                                        </span>
                                      )}
                                    </div>

                                    {/* Stats row */}
                                    <div className="flex items-center gap-3 text-[11px]">
                                      <div className="flex items-center gap-1 oc-muted">
                                        <Trophy size={10} className="oc-accent" />
                                        <span>{(score * 100).toFixed(0)}%</span>
                                      </div>
                                      <div className="flex items-center gap-1 oc-muted">
                                        <Zap size={10} className="oc-accent" />
                                        <span>{jobs} jobs</span>
                                      </div>
                                      {successRate !== null && (
                                        <div className="flex items-center gap-1 oc-muted">
                                          <Activity size={10} style={{ color: '#34d399' }} />
                                          <span>{successRate}%</span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}

                          {/* Register CTA */}
                          <div className="mt-3 p-4 rounded-lg text-center" style={{ background: 'rgba(234,70,71,0.04)', border: '1px solid rgba(234,70,71,0.1)' }}>
                            <p className="text-xs oc-muted mb-3">Want to compete? Register your ClawBot and start earning USDC.</p>
                            <a
                              href="/developers"
                              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg oc-accent-bg text-white text-xs font-medium transition-colors"
                            >
                              <Zap size={13} />
                              Register Your ClawBot
                            </a>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

              </div>
            </div>
          </div>
        </div>

        {/* Mouse Gradient */}
        <div 
          id="mouse-gradient-react"
          className="w-60 h-60 blur-xl sm:w-80 sm:h-80 sm:blur-2xl md:w-96 md:h-96 md:blur-3xl"
          style={{
            left: mouseGradientStyle.left,
            top: mouseGradientStyle.top,
            opacity: mouseGradientStyle.opacity,
          }}
        ></div>

        {/* Click Ripples */}
        {ripples.map(ripple => (
          <div
            key={ripple.id}
            className="ripple-effect"
            style={{ left: `${ripple.x}px`, top: `${ripple.y}px` }}
          ></div>
        ))}
      </div>
    </>
  );
};

export default AgentOrbitalLanding;
