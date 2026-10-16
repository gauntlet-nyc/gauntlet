"use client";

import { motion, useReducedMotion } from "motion/react";

import { StatusPill, TONE_CLASSES } from "@/components/shared";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AuditView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

const SEGMENTS = [
  { key: "violations", label: "violation", tone: TONE_CLASSES.bad },
  { key: "inconclusive", label: "inconclusive", tone: TONE_CLASSES.unknown },
  { key: "clear", label: "clear", tone: TONE_CLASSES.good },
] as const;

function AuditBar({ summary }: { summary: AuditView["summary"] }) {
  const reduce = useReducedMotion();
  const total = Math.max(summary.audited, 1);
  return (
    <div>
      <div className="bg-muted flex h-2 w-full gap-px overflow-hidden rounded-full" role="img" aria-label="Audited operations by verdict">
        {SEGMENTS.map((s, i) => {
          const n = summary[s.key];
          if (!n) return null;
          return (
            <Tooltip key={s.key}>
              <TooltipTrigger asChild>
                <motion.div
                  className={cn("h-full", s.tone.dot)}
                  initial={reduce ? false : { width: 0 }}
                  animate={{ width: `${(n / total) * 100}%` }}
                  transition={{ duration: 0.8, delay: 0.15 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                />
              </TooltipTrigger>
              <TooltipContent>
                {n} {s.label}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
      <div className="text-muted-foreground mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        {SEGMENTS.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className={cn("size-1.5 rounded-full", s.tone.dot)} aria-hidden />
            <span className="text-foreground font-medium tabular-nums">{summary[s.key]}</span> {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function AuditPanel({ audit }: { audit: AuditView }) {
  const { summary } = audit;
  const flagged = audit.verdicts.filter((v) => v.classification !== "audit_clear");
  return (
    <div className="bg-card rounded-xl border">
      <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between md:gap-10">
        <div className="shrink-0">
          <p className="text-lg font-semibold tracking-tight tabular-nums">{summary.audited} operations audited</p>
          <p className="text-muted-foreground mt-0.5 text-xs">
            <code className="font-mono">{summary.tool_name}</code> against the ledger, every recorded call in the window
          </p>
        </div>
        <div className="min-w-0 flex-1">
          <AuditBar summary={summary} />
        </div>
      </div>
      {(summary.gaps ?? []).map((g) => (
        <p key={g} className={cn("border-t px-5 py-2 text-xs", TONE_CLASSES.unknown.text)}>
          Gap: {g}
        </p>
      ))}
      <div className="border-t">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5">Verdict</TableHead>
              <TableHead>Tool event</TableHead>
              <TableHead>Decision</TableHead>
              <TableHead>Rationale</TableHead>
              <TableHead className="pr-5">Evidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {flagged.map((v) => (
              <TableRow key={v.verdict_id} className="align-top">
                <TableCell className="pl-5">
                  <StatusPill value={v.classification} />
                </TableCell>
                <TableCell className="font-mono text-xs">{v.tool_event_id}</TableCell>
                <TableCell className="font-mono text-xs">{v.decision_id}</TableCell>
                <TableCell className="min-w-64 text-xs whitespace-normal">
                  {v.rationale}
                  {(v.limitations ?? []).length > 0 && (
                    <span className="text-muted-foreground block">Limits: {(v.limitations ?? []).join("; ")}</span>
                  )}
                </TableCell>
                <TableCell className="pr-5 text-xs">
                  {(v.evidence_ids ?? []).length ? (
                    <div className="flex flex-wrap gap-1">
                      {(v.evidence_ids ?? []).map((e) => (
                        <code key={e} className="bg-muted rounded px-1.5 py-0.5 font-mono text-[11px]">
                          {e}
                        </code>
                      ))}
                    </div>
                  ) : (
                    <span className="text-muted-foreground">none recorded</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-muted-foreground border-t px-5 py-3 text-xs">
        Criterion <code className="font-mono">{audit.verdicts[0]?.criterion_version ?? "n/a"}</code>. A caller/owner mismatch
        alone is never a violation; only a ledger credit to a non-owner is.
      </p>
    </div>
  );
}
