"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

const DURATION_S = 0.9;

/** Counts from 0 to `value` once on mount; renders the final value directly under reduced motion. */
export function CountUp({ value, delay = 0 }: { value: number; delay?: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (reduce) {
      setShown(value);
      return;
    }
    setShown(0);
    const controls = animate(0, value, {
      duration: DURATION_S,
      delay,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setShown(Math.round(v)),
    });
    return () => controls.stop();
  }, [value, delay, reduce]);

  return <span className="tabular-nums">{shown}</span>;
}
