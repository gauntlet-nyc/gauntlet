import { ArrowRight, GitBranch, GitCommitHorizontal } from "lucide-react";

import { StatusPill, TONE_CLASSES, toneOf } from "@/components/shared";
import type { CounterfactualCase } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

import { caseAnchor, EXPOSURE_LABEL, type Outcome } from "./model";

export interface CaseViewModel {
  c: CounterfactualCase;
  original: Outcome;
  counterfactual: Outcome;
}

function YesNo({ value }: { value: boolean | null | undefined }) {
  if (value == null) return <span className="text-muted-foreground">n/a</span>;
  return <span className="text-foreground font-medium">{value ? "Yes" : "No"}</span>;
}

function OutcomeBox({ label, outcome, emphasize }: { label: string; outcome: Outcome; emphasize?: string }) {
  return (
    <div className={cn("rounded-md border px-3 py-2.5", emphasize)}>
      <div className="text-muted-foreground text-[11px] font-medium">{label}</div>
      <div className={cn("mt-1 text-sm font-medium", !outcome.known && "text-muted-foreground")}>{outcome.action}</div>
      <div className="text-muted-foreground mt-0.5 font-mono text-xs tabular-nums">{outcome.amount ?? (outcome.known ? "no amount" : "n/a")}</div>
    </div>
  );
}

export function CaseCard({ vm, trigger, selected }: { vm: CaseViewModel; trigger: string; selected: boolean }) {
  const { c, original, counterfactual } = vm;
  const cls = c.verdict.classification;
  const tone = TONE_CLASSES[toneOf(cls)];
  const first = c.exposure.path[0];
  const changed = c.verdict.material_change === true;
  const ExposureIcon = c.exposure.direct ? GitCommitHorizontal : GitBranch;

  return (
    <article
      id={caseAnchor(c.decision_id)}
      className={cn(
        "bg-card scroll-mt-24 rounded-xl border p-5 transition-[box-shadow,border-color] duration-300",
        selected ? "border-foreground/50 ring-foreground/15 ring-4" : "border-border",
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className={cn("size-2 rounded-full", tone.dot)} aria-hidden />
          <h3 className="font-mono text-sm font-medium">{c.decision_id}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground inline-flex h-5 items-center gap-1 rounded-full border px-2 text-xs">
            <ExposureIcon className="size-3" aria-hidden />
            {c.exposure.direct ? EXPOSURE_LABEL.direct : EXPOSURE_LABEL.secondOrder}
          </span>
          <StatusPill value={cls} />
        </div>
      </header>

      {first && (
        <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-xs">
          <span className="text-foreground">{first.source.node_id}</span>
          {c.exposure.path.map((e) => (
            <span key={e.edge_id} className="inline-flex items-center gap-1.5">
              <ArrowRight className="size-3 opacity-60" aria-hidden />
              <span className="font-sans text-[11px] italic">{e.relation.replaceAll("_", " ")}</span>
              <ArrowRight className="size-3 opacity-60" aria-hidden />
              <span className="text-foreground">{e.target.node_id}</span>
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2">
        <OutcomeBox label="Original (recorded)" outcome={original} />
        <OutcomeBox
          label={`Counterfactual (without ${trigger})`}
          outcome={counterfactual}
          emphasize={changed ? cn(tone.border, tone.bg) : undefined}
        />
      </div>

      <p className="text-muted-foreground mt-4 text-sm leading-relaxed">{c.verdict.rationale}</p>

      <dl className="mt-4 grid grid-cols-3 gap-2 border-t pt-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Control matched?</dt>
          <dd className="mt-0.5">
            <YesNo value={c.verdict.control_matches} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Material change?</dt>
          <dd className="mt-0.5">
            <YesNo value={c.verdict.material_change} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Replays</dt>
          <dd className="mt-0.5 font-medium tabular-nums">{(c.verdict.replay_ids ?? []).length}</dd>
        </div>
      </dl>
      {c.missing_fields.length > 0 && (
        <p className={cn("mt-3 text-xs", TONE_CLASSES.unknown.text)}>
          Missing: <code className="font-mono">{c.missing_fields.join(", ")}</code>. Exposed but undetermined, never cleared.
        </p>
      )}
    </article>
  );
}
