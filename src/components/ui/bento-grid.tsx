"use client";

import React from "react";

interface BentoGridProps {
  children: React.ReactNode;
  className?: string;
  columns?: 2 | 3 | 4;
}

export function BentoGrid({ children, className = "", columns = 2 }: BentoGridProps) {
  const colsMap = {
    2: "grid-cols-1 md:grid-cols-2",
    3: "grid-cols-1 md:grid-cols-3",
    4: "grid-cols-1 md:grid-cols-2 lg:grid-cols-4",
  };

  return (
    <div className={`grid ${colsMap[columns]} gap-4 ${className}`}>
      {children}
    </div>
  );
}

interface BentoItemProps {
  children: React.ReactNode;
  className?: string;
  colSpan?: 1 | 2;
  rowSpan?: 1 | 2;
}

export function BentoItem({ children, className = "", colSpan = 1, rowSpan = 1 }: BentoItemProps) {
  const colClass = colSpan === 2 ? "md:col-span-2" : "";
  const rowClass = rowSpan === 2 ? "md:row-span-2" : "";

  return (
    <div className={`${colClass} ${rowClass} ${className}`}>
      {children}
    </div>
  );
}
