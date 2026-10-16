import { tallyLine, type RevisionTally, type RunTally } from "@/components/gate/copy";
import { TONE_CLASSES } from "@/components/shared";
import { cn } from "@/lib/utils";

function Counter({ label, tally }: { label: string; tally: RevisionTally }) {
  const tone = tally.failed > 0 ? TONE_CLASSES.bad : tally.total > 0 ? TONE_CLASSES.good : null;
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className={cn("text-3xl font-semibold tracking-tight tabular-nums", tone?.text)}>
          {tally.failed}/{tally.total}
        </span>
        <span className="text-muted-foreground text-sm">failed</span>
      </div>
    </div>
  );
}

/** Head vs base as two counters: the core evidence for attribution. */
export function RevisionCounters({ tally }: { tally: RunTally }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-6">
        <Counter label="Head (this PR)" tally={tally.head} />
        <Counter label="Base" tally={tally.base} />
      </div>
      <p className="text-muted-foreground mt-3 font-mono text-xs tabular-nums">{tallyLine(tally)}</p>
    </div>
  );
}
