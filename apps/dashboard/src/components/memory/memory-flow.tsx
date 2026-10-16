"use client";

import { ArrowDown, Brain, FlaskConical, Gavel, ListChecks } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPill } from "@/components/shared";
import { cn } from "@/lib/utils";

export interface FlowStep {
  icon: "run" | "fact" | "plan" | "oracle";
  eyebrow: string;
  title: ReactNode;
  detail: ReactNode;
  status?: string;
  emphasis?: boolean;
}

const ICONS: Record<FlowStep["icon"], LucideIcon> = { run: FlaskConical, fact: Brain, plan: ListChecks, oracle: Gavel };
const STEP_DELAY_S = 0.18;

function Connector({ index, label }: { index: number; label: string }) {
  const reduce = useReducedMotion();
  return (
    <div className="text-muted-foreground flex shrink-0 items-center justify-center gap-2 py-1 md:w-24 md:flex-col md:gap-1 md:py-0">
      <ArrowDown className="size-3.5 md:hidden" aria-hidden />
      <svg className="hidden h-3 w-full md:block" viewBox="0 0 80 12" preserveAspectRatio="none" aria-hidden>
        <motion.path
          d="M2 6 H74"
          stroke="currentColor"
          strokeWidth="1.25"
          fill="none"
          initial={reduce ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.45, delay: (index + 1) * STEP_DELAY_S }}
        />
        <path d="M70 2 L76 6 L70 10" stroke="currentColor" strokeWidth="1.25" fill="none" />
      </svg>
      <span className="text-[10px] font-medium tracking-wide whitespace-nowrap uppercase">{label}</span>
    </div>
  );
}

export function MemoryFlow({ steps, links }: { steps: readonly FlowStep[]; links: readonly string[] }) {
  const reduce = useReducedMotion();
  return (
    <div className="flex flex-col items-stretch md:flex-row">
      {steps.map((s, i) => {
        const Icon = ICONS[s.icon];
        return (
          <div key={i} className="contents">
            {i > 0 && <Connector index={i - 1} label={links[i - 1] ?? ""} />}
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * STEP_DELAY_S, ease: [0.16, 1, 0.3, 1] }}
              className={cn(
                "bg-card min-w-0 flex-1 rounded-lg border px-3.5 py-3",
                s.emphasis && "border-info/35",
              )}
            >
              <div className="text-muted-foreground flex items-center justify-between gap-2 text-[10px] font-medium tracking-wide uppercase">
                <span className="flex items-center gap-1.5">
                  <Icon className={cn("size-3.5", s.emphasis && "text-info")} aria-hidden />
                  {s.eyebrow}
                </span>
              </div>
              <div className="mt-1.5 truncate font-mono text-sm font-medium">{s.title}</div>
              <div className="text-muted-foreground mt-0.5 text-xs">{s.detail}</div>
              {s.status && (
                <div className="mt-2">
                  <StatusPill value={s.status} />
                </div>
              )}
            </motion.div>
          </div>
        );
      })}
    </div>
  );
}
