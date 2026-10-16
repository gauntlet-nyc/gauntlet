"use client";

import { useCallback, useState } from "react";

import { TONE_CLASSES } from "@/components/shared";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AuditView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

import { AuditPanel } from "./audit-panel";
import { CaseRow, type CaseViewModel } from "./case-row";
import { DecisionTimeline, type TimelineRow } from "./decision-timeline";
import { LineageGraph } from "./lineage-graph";
import { caseAnchor } from "./model";

const TAB = { cases: "cases", audit: "audit", timeline: "timeline" } as const;
type Tab = (typeof TAB)[keyof typeof TAB];

const LEGEND = [
  { label: "tainted", dot: TONE_CLASSES.bad.dot },
  { label: "cleared", dot: TONE_CLASSES.good.dot },
  { label: "not replayable", dot: TONE_CLASSES.unknown.dot },
] as const;

/** The lineage graph is the hero; cases, audit and timeline sit one click away and share the graph's selection. */
export function LineageExplorer({
  cases,
  trigger,
  audit,
  rows,
  highlight,
}: {
  cases: readonly CaseViewModel[];
  trigger: string;
  audit: AuditView;
  rows: readonly TimelineRow[];
  highlight: readonly string[];
}) {
  const [tab, setTab] = useState<Tab>(TAB.cases);
  const [open, setOpen] = useState<string | null>(null);

  const select = useCallback((decisionId: string) => {
    setTab(TAB.cases);
    setOpen(decisionId);
    requestAnimationFrame(() =>
      document.getElementById(caseAnchor(decisionId))?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  }, []);

  return (
    <>
      <div className="text-muted-foreground mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs">
        <span>
          How {trigger} reached each decision. <span className="hidden sm:inline">Click a decision to open its case.</span>
          <span className="sm:hidden">Swipe to see every decision.</span>
        </span>
        <span className="flex items-center gap-4">
          {LEGEND.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5">
              <span className={cn("size-1.5 rounded-full", l.dot)} aria-hidden />
              {l.label}
            </span>
          ))}
        </span>
      </div>
      <div className="overflow-x-auto rounded-xl border">
        <LineageGraph cases={cases.map((v) => v.c)} trigger={trigger} selected={open} onSelect={select} />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-10 gap-4">
        <TabsList variant="line" className="h-9 gap-4 border-b w-full justify-start rounded-none p-0">
          <TabsTrigger value={TAB.cases} className="flex-none px-0">
            Cases <span className="text-muted-foreground tabular-nums">{cases.length}</span>
          </TabsTrigger>
          <TabsTrigger value={TAB.audit} className="flex-none px-0">
            Audit <span className="text-muted-foreground tabular-nums">{audit.summary.audited}</span>
          </TabsTrigger>
          <TabsTrigger value={TAB.timeline} className="flex-none px-0">
            Timeline <span className="text-muted-foreground tabular-nums">{rows.length}</span>
          </TabsTrigger>
        </TabsList>
        <TabsContent value={TAB.cases}>
          <ul className="divide-y rounded-xl border">
            {cases.map((vm) => (
              <CaseRow
                key={vm.c.decision_id}
                vm={vm}
                trigger={trigger}
                open={open === vm.c.decision_id}
                onOpenChange={(o) => setOpen(o ? vm.c.decision_id : null)}
              />
            ))}
          </ul>
        </TabsContent>
        <TabsContent value={TAB.audit}>
          <AuditPanel audit={audit} />
        </TabsContent>
        <TabsContent value={TAB.timeline}>
          <DecisionTimeline rows={rows} trigger={trigger} highlight={highlight} />
        </TabsContent>
      </Tabs>
    </>
  );
}
