"use client";

import React from "react";
import { motion } from "framer-motion";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "interactive" | "feature";
  hoverGlow?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}

export function GlassCard({
  children,
  className = "",
  variant = "default",
  hoverGlow = true,
  onClick,
  style,
}: GlassCardProps) {
  const baseStyles =
    "relative rounded-2xl border border-[color:var(--border-subtle)] backdrop-blur-xl overflow-hidden";

  const bgStyles =
    "bg-[color:var(--surface-elevated)]";

  const shadowStyles = "shadow-[var(--shadow-card)]";

  const hoverStyles = hoverGlow
    ? "hover:shadow-[var(--shadow-card-hover)] hover:border-[color:var(--accent)] hover:-translate-y-1 transition-all duration-300 ease-out"
    : "transition-all duration-300";

  const interactiveStyles =
    variant === "interactive" ? "cursor-pointer active:scale-[0.98]" : "";

  return (
    <motion.div
      className={`${baseStyles} ${bgStyles} ${shadowStyles} ${hoverStyles} ${interactiveStyles} ${className}`}
      onClick={onClick}
      style={style}
      whileHover={variant === "interactive" ? { scale: 1.02 } : undefined}
    >
      {hoverGlow && (
        <div className="absolute inset-0 opacity-0 hover:opacity-100 transition-opacity duration-500 pointer-events-none bg-[radial-gradient(600px_at_var(--mouse-x,50%)_var(--mouse-y,50%),var(--glow-accent),transparent_70%)]" />
      )}
      {children}
    </motion.div>
  );
}
