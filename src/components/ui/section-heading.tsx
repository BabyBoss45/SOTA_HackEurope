"use client";

import React from "react";

interface SectionHeadingProps {
  title: string;
  subtitle?: string;
  gradient?: boolean;
  align?: "left" | "center";
  size?: "default" | "large" | "display";
  className?: string;
  children?: React.ReactNode;
}

export function SectionHeading({
  title,
  subtitle,
  gradient = false,
  align = "left",
  size = "default",
  className = "",
  children,
}: SectionHeadingProps) {
  const alignClass = align === "center" ? "text-center" : "text-left";
  const sizeClasses = {
    default: "text-2xl sm:text-3xl",
    large: "text-3xl sm:text-4xl md:text-5xl",
    display: "text-4xl sm:text-5xl md:text-6xl lg:text-7xl",
  };

  return (
    <div className={`${alignClass} ${className}`}>
      <h2
        className={`font-display ${sizeClasses[size]} font-bold tracking-tight ${
          gradient
            ? "text-transparent bg-clip-text bg-gradient-to-r from-[color:var(--hero-title-start)] via-[color:var(--hero-title-mid)] to-[color:var(--hero-title-end)]"
            : "text-[color:var(--foreground)]"
        }`}
      >
        {title}
      </h2>
      {subtitle && (
        <p className="mt-4 text-lg text-[color:var(--text-muted)] max-w-2xl leading-relaxed"
          style={align === "center" ? { marginLeft: "auto", marginRight: "auto" } : undefined}
        >
          {subtitle}
        </p>
      )}
      {children}
    </div>
  );
}
