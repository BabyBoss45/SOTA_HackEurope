"use client";

import React from "react";
import Link from "next/link";
import { Bot, Hexagon, Database, CreditCard, WalletCards } from "lucide-react";

const footerLinks = {
  Product: [
    { label: "Marketplace", href: "/marketplace" },
    { label: "Agents", href: "/agents" },
    { label: "Pricing", href: "/marketplace" },
  ],
  Developers: [
    { label: "Dashboard", href: "/developers" },
    { label: "Deploy Agent", href: "/developers/deploy" },
    { label: "SDK Docs", href: "/developers/docs" },
    { label: "Payout", href: "/developers/payout" },
  ],
  Resources: [
    { label: "Documentation", href: "/developers/docs" },
    { label: "API Reference", href: "/developers/docs" },
    { label: "GitHub", href: "https://github.com" },
  ],
  Company: [
    { label: "About", href: "/" },
    { label: "Blog", href: "/" },
    { label: "Careers", href: "/" },
  ],
};

export function Footer() {
  return (
    <footer className="relative border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
      <div className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2.5 mb-4 group">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
                <Bot size={16} className="text-white" />
              </div>
              <span className="font-display text-lg font-bold text-[color:var(--foreground)] tracking-tight">
                SOTA
              </span>
            </Link>
            <p className="text-sm text-[color:var(--text-muted)] leading-relaxed max-w-xs">
              The decentralized marketplace for AI agents. Deploy, hire, and earn on-chain.
            </p>
          </div>

          {/* Link Columns */}
          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title}>
              <h3 className="text-sm font-semibold text-[color:var(--foreground)] mb-4 tracking-wide uppercase">
                {title}
              </h3>
              <ul className="space-y-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-sm text-[color:var(--text-muted)] hover:text-[color:var(--foreground)] transition-colors"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="mt-12 pt-6 border-t border-[color:var(--border-subtle)] flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-[color:var(--text-muted)]">
            &copy; {new Date().getFullYear()} SOTA. All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-xs text-[color:var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              Powered by
            </span>
            <span className="flex items-center gap-1 font-semibold text-blue-400">
              <Hexagon size={12} /> Base
            </span>
            <span className="flex items-center gap-1 font-semibold" style={{ color: "#3ECF8E" }}>
              <Database size={12} /> Supabase
            </span>
            <span className="flex items-center gap-1 font-semibold" style={{ color: "#635BFF" }}>
              <WalletCards size={12} /> Stripe
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
