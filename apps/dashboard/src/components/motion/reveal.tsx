"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/** Fade-and-rise entrance. `index` staggers siblings by 50 ms. */
export function Reveal({
  children,
  index = 0,
  className,
  y = 8,
}: {
  children: ReactNode;
  index?: number;
  className?: string;
  y?: number;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: index * 0.05 }}
    >
      {children}
    </motion.div>
  );
}
