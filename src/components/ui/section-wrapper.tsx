"use client";

import React, { useRef } from "react";
import { motion, useInView } from "framer-motion";

interface SectionWrapperProps {
  children: React.ReactNode;
  className?: string;
  alt?: boolean;
  id?: string;
  maxWidth?: string;
  padding?: string;
}

export function SectionWrapper({
  children,
  className = "",
  alt = false,
  id,
  maxWidth = "max-w-7xl",
  padding = "py-24 px-6",
}: SectionWrapperProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section
      id={id}
      ref={ref}
      className={`relative ${alt ? "bg-[image:var(--gradient-section-alt)]" : ""} ${className}`}
    >
      <motion.div
        className={`${maxWidth} mx-auto ${padding}`}
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 40 }}
        transition={{ duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        {children}
      </motion.div>
    </section>
  );
}
