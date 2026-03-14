"use client";

import React from "react";

type BadgeStatus = "open" | "bidding" | "executing" | "completed" | "failed" | "queued" | "collecting_bids" | "in_progress";

interface StatusBadgeProps {
  status: BadgeStatus | string;
  className?: string;
  size?: "sm" | "md";
}

const statusConfig: Record<string, { bg: string; text: string; dot: string; pulse?: boolean; label?: string }> = {
  open: { bg: "bg-slate-500/15", text: "text-slate-400", dot: "bg-slate-400" },
  queued: { bg: "bg-slate-500/15", text: "text-slate-400", dot: "bg-slate-400" },
  bidding: { bg: "bg-blue-500/15", text: "text-blue-400", dot: "bg-blue-400" },
  executing: { bg: "bg-violet-500/15", text: "text-violet-400", dot: "bg-violet-400", pulse: true },
  completed: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400", label: "Completed" },
  failed: { bg: "bg-red-500/15", text: "text-red-400", dot: "bg-red-400", label: "Failed" },
  active: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400" },
  inactive: { bg: "bg-slate-500/15", text: "text-slate-400", dot: "bg-slate-400" },
  collecting_bids: { bg: "bg-indigo-500/15", text: "text-indigo-400", dot: "bg-indigo-400", label: "Collecting Bids" },
  in_progress: { bg: "bg-amber-500/15", text: "text-amber-400", dot: "bg-amber-400", pulse: true, label: "In Progress" },
};

export function StatusBadge({ status, className = "", size = "sm" }: StatusBadgeProps) {
  const config = statusConfig[status.toLowerCase()] || statusConfig.open;
  const sizeClasses = size === "sm" ? "px-2.5 py-0.5 text-xs" : "px-3 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${config.bg} ${config.text} ${sizeClasses} ${className}`}
    >
      <span className="relative flex h-2 w-2">
        {config.pulse && (
          <span className={`absolute inset-0 rounded-full ${config.dot} animate-ping opacity-75`} />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${config.dot}`} />
      </span>
      {config.label || status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
