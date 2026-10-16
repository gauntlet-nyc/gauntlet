"use client";

import { CheckCircle2, CircleDashed, XCircle, type LucideIcon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { TONE_CLASSES, type Tone } from "@/components/shared";
import { cn } from "@/lib/utils";

const ICONS: Record<Tone, LucideIcon> = { bad: XCircle, good: CheckCircle2, unknown: CircleDashed };
const EASE = [0.16, 1, 0.3, 1] as const;

/** The first thing a reviewer reads: the verdict, why, and the facts it rests on. */
export function VerdictHero({
  tone,
  headline,
  explanation,
  verdictLine,
  facts,
  aside,
}: {
  tone: Tone;
  headline: string;
  explanation: string;
  verdictLine: ReactNode;
  facts: ReactNode;
  aside?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const Icon = ICONS[tone];
  const t = TONE_CLASSES[tone];
  return (
    <motion.section
      aria-label="Verdict"
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
      className={cn("bg-card relative overflow-hidden rounded-xl border", t.border)}
    >
      <div className={cn("pointer-events-none absolute inset-x-0 top-0 h-px", t.dot, "opacity-60")} aria-hidden />
      <div
        className={cn("pointer-events-none absolute -top-24 -left-24 size-72 rounded-full blur-3xl", t.bg)}
        aria-hidden
      />
      <div className="relative grid gap-6 p-5 md:p-7 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <div className="flex items-start gap-4">
            <motion.div
              initial={reduce ? false : { scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.45, ease: EASE, delay: 0.1 }}
              className={cn("flex size-12 shrink-0 items-center justify-center rounded-full border", t.bg, t.border)}
            >
              <Icon className={cn("size-6", t.text)} aria-hidden />
            </motion.div>
            <div className="min-w-0">
              <motion.h2
                initial={reduce ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.45, ease: EASE, delay: 0.15 }}
                className={cn("text-2xl font-semibold tracking-tight md:text-[28px]", t.text)}
              >
                {headline}
              </motion.h2>
              <p className="text-muted-foreground mt-1.5 max-w-2xl text-[15px] leading-relaxed">{explanation}</p>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">{verdictLine}</div>
          <div className="mt-5 border-t pt-5">{facts}</div>
        </div>
        {aside && <div className="min-w-0">{aside}</div>}
      </div>
    </motion.section>
  );
}
