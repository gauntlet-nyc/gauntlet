"use client";

import { CheckCircle2, CircleDashed, XCircle, type LucideIcon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { TONE_CLASSES, type Tone } from "@/components/shared";
import { cn } from "@/lib/utils";

const ICONS: Record<Tone, LucideIcon> = { bad: XCircle, good: CheckCircle2, unknown: CircleDashed };
const EASE = [0.16, 1, 0.3, 1] as const;

/** The answer to the page: verdict, why, and head vs base. */
export function VerdictHero({
  tone,
  headline,
  explanation,
  verdictLine,
  aside,
}: {
  tone: Tone;
  headline: string;
  explanation: string;
  verdictLine: ReactNode;
  aside?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const Icon = ICONS[tone];
  const t = TONE_CLASSES[tone];
  return (
    <motion.section
      aria-label="Verdict"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: EASE }}
      className={cn("bg-card grid gap-6 rounded-xl border p-6 md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:gap-10", t.border)}
    >
      <div className="flex min-w-0 items-start gap-4">
        <motion.div
          initial={reduce ? false : { scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.4, ease: EASE, delay: 0.08 }}
          className={cn("mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-full", t.bg)}
        >
          <Icon className={cn("size-5", t.text)} aria-hidden />
        </motion.div>
        <div className="min-w-0">
          <h2 className={cn("text-2xl font-semibold tracking-tight", t.text)}>{headline}</h2>
          <p className="text-muted-foreground mt-1 max-w-xl text-sm leading-relaxed">{explanation}</p>
          <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">{verdictLine}</div>
        </div>
      </div>
      {aside && <div className="md:border-l md:pl-10">{aside}</div>}
    </motion.section>
  );
}
