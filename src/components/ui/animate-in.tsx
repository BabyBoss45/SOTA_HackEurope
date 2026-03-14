"use client";

import React from "react";
import { motion, useInView, type Variants } from "framer-motion";
import { useRef } from "react";

type AnimationPreset = "fade-up" | "scale-up" | "slide-left" | "slide-right" | "bounce";

const presets: Record<AnimationPreset, Variants> = {
  "fade-up": {
    hidden: { opacity: 0, y: 40 },
    visible: { opacity: 1, y: 0 },
  },
  "scale-up": {
    hidden: { opacity: 0, scale: 0.85 },
    visible: { opacity: 1, scale: 1 },
  },
  "slide-left": {
    hidden: { opacity: 0, x: -60 },
    visible: { opacity: 1, x: 0 },
  },
  "slide-right": {
    hidden: { opacity: 0, x: 60 },
    visible: { opacity: 1, x: 0 },
  },
  bounce: {
    hidden: { opacity: 0, y: 60, scale: 0.9 },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { type: "spring", stiffness: 300, damping: 20 },
    },
  },
};

interface AnimateInProps {
  children: React.ReactNode;
  preset?: AnimationPreset;
  delay?: number;
  duration?: number;
  className?: string;
  once?: boolean;
}

export function AnimateIn({
  children,
  preset = "fade-up",
  delay = 0,
  duration = 0.6,
  className = "",
  once = true,
}: AnimateInProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once, margin: "-60px" });

  const variants = presets[preset];

  return (
    <motion.div
      ref={ref}
      className={className}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={variants}
      transition={
        preset === "bounce"
          ? { delay }
          : { duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }
      }
    >
      {children}
    </motion.div>
  );
}

interface StaggerContainerProps {
  children: React.ReactNode;
  className?: string;
  staggerDelay?: number;
  once?: boolean;
}

export function StaggerContainer({
  children,
  className = "",
  staggerDelay = 0.1,
  once = true,
}: StaggerContainerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once, margin: "-60px" });

  return (
    <motion.div
      ref={ref}
      className={className}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: staggerDelay } },
      }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className = "",
  preset = "fade-up",
}: {
  children: React.ReactNode;
  className?: string;
  preset?: AnimationPreset;
}) {
  return (
    <motion.div className={className} variants={presets[preset]}>
      {children}
    </motion.div>
  );
}
