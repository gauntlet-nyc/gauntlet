"use client";

import { MousePointerClick } from "lucide-react";
import { useCallback, useState } from "react";

import { Reveal } from "@/components/motion/reveal";
import { TONE_CLASSES } from "@/components/shared";
import { cn } from "@/lib/utils";

import { CaseCard, type CaseViewModel } from "./case-card";
import { LineageGraph } from "./lineage-graph";
import { caseAnchor } from "./model";

const LEGEND = [
  { label: "tainted", dot: TONE_CLASSES.bad.dot },
  { label: "cleared", dot: TONE_CLASSES.good.dot },
  { label: "not replayable", dot: TONE_CLASSES.unknown.dot },
] as const;

/** The lineage graph and the counterfactual case cards share one selection. */
export function LineageExplorer({ cases, trigger }: { cases: readonly CaseViewModel[]; trigger: string }) {
  const [selected, setSelected] = useState<string | null>(null);

  const select = useCallback((decisionId: string) => {
    setSelected(decisionId);
    document.getElementById(caseAnchor(decisionId))?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  return (
    <>
      <div className="bg-card overflow-hidden rounded-xl border">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5 text-xs">
          <div className="text-muted-foreground flex flex-wrap items-center gap-4">
            {LEGEND.map((l) => (
              <span key={l.label} className="inline-flex items-center gap-1.5">
                <span className={cn("size-1.5 rounded-full", l.dot)} aria-hidden />
                {l.label}
              </span>
            ))}
            <span className="inline-flex items-center gap-1.5">
              <svg width="18" height="6" aria-hidden>
                <line x1="0" y1="3" x2="18" y2="3" stroke="var(--regression)" strokeWidth="1.5" strokeDasharray="4 3" />
              </svg>
              tainted path
            </span>
          </div>
          <span className="text-muted-foreground text-xs sm:hidden">Swipe sideways to see every decision</span>
          <span className="text-muted-foreground hidden items-center gap-1.5 sm:inline-flex">
            <MousePointerClick className="size-3.5" aria-hidden />
            Click a decision to open its case
          </span>
        </div>
        <div className="overflow-x-auto">
          <LineageGraph cases={cases.map((v) => v.c)} trigger={trigger} selected={selected} onSelect={select} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {cases.map((vm, i) => (
          <Reveal key={vm.c.decision_id} index={i}>
            <CaseCard vm={vm} trigger={trigger} selected={selected === vm.c.decision_id} />
          </Reveal>
        ))}
      </div>
    </>
  );
}
