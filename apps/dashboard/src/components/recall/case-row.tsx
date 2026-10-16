"use client";

import { ArrowRight, ChevronRight } from "lucide-react";

import { StatusPill, TONE_CLASSES, toneOf } from "@/components/shared";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { CounterfactualCase } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

import { caseAnchor, EXPOSURE_LABEL, type Outcome } from "./model";

export interface CaseViewModel {
  c: CounterfactualCase;
  original: Outcome;
  counterfactual: Outcome;
}

function outcomeText(o: Outcome): string {
  return o.amount ? `${o.action} ${o.amount}` : o.action;
}

function yesNo(value: boolean | null | undefined): string {
  if (value == null) return "n/a";
  return value ? "yes" : "no";
}

function OutcomeColumn({ label, outcome, valueClass }: { label: string; outcome: Outcome; valueClass?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className={cn("mt-0.5 text-sm font-medium", !outcome.known && "text-muted-foreground", valueClass)}>{outcome.action}</div>
      {outcome.amount && <div className="text-muted-foreground text-xs tabular-nums">{outcome.amount}</div>}
    </div>
  );
}

export function CaseRow({
  vm,
  trigger,
  open,
  onOpenChange,
}: {
  vm: CaseViewModel;
  trigger: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { c, original, counterfactual } = vm;
  const cls = c.verdict.classification;
  const tone = TONE_CLASSES[toneOf(cls)];
  const changed = c.verdict.material_change === true;
  const result = !c.replayable
    ? "Not replayed: inputs missing"
    : changed
      ? `${outcomeText(original)} → ${outcomeText(counterfactual)}`
      : `${outcomeText(original)}, unchanged`;

  return (
    <Collapsible open={open} onOpenChange={onOpenChange} asChild>
      <li id={caseAnchor(c.decision_id)} className={cn("scroll-mt-24 transition-colors", open && "bg-accent/40")}>
        <CollapsibleTrigger className="hover:bg-accent/40 grid w-full grid-cols-[1rem_1fr_auto] items-center gap-x-3 px-4 py-3 text-left sm:grid-cols-[1rem_8.5rem_7rem_8.5rem_1fr] sm:gap-x-4">
          <ChevronRight
            className={cn("text-muted-foreground size-4 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <span className="font-mono text-sm">{c.decision_id}</span>
          <span className="text-muted-foreground hidden text-sm sm:block">
            {c.exposure.direct ? EXPOSURE_LABEL.direct : EXPOSURE_LABEL.secondOrder}
          </span>
          <span className="justify-self-end sm:justify-self-start">
            <StatusPill value={cls} />
          </span>
          <span className="text-muted-foreground col-start-2 col-end-4 truncate text-sm sm:col-auto">{result}</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="grid gap-5 px-4 pt-1 pb-5 pl-12 sm:grid-cols-[1fr_1fr_1.4fr]">
            <OutcomeColumn label="Original (recorded)" outcome={original} />
            <OutcomeColumn
              label={`Without ${trigger}`}
              outcome={counterfactual}
              valueClass={changed ? tone.text : undefined}
            />
            <div className="text-muted-foreground space-y-1.5 text-xs leading-relaxed">
              <p className="text-foreground/90 text-sm">{c.verdict.rationale}</p>
              <p className="flex flex-wrap items-center gap-1 font-mono">
                {c.exposure.path[0]?.source.node_id}
                {c.exposure.path.map((e) => (
                  <span key={e.edge_id} className="inline-flex items-center gap-1">
                    <ArrowRight className="size-3" aria-hidden />
                    {e.target.node_id}
                  </span>
                ))}
              </p>
              <p>
                Control matched {yesNo(c.verdict.control_matches)} · material change {yesNo(c.verdict.material_change)} ·{" "}
                {(c.verdict.replay_ids ?? []).length} replays
              </p>
              {c.missing_fields.length > 0 && (
                <p className={TONE_CLASSES.unknown.text}>Missing {c.missing_fields.join(", ")}, so never cleared.</p>
              )}
            </div>
          </div>
        </CollapsibleContent>
      </li>
    </Collapsible>
  );
}
