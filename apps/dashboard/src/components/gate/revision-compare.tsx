import { Check, GitBranch, GitPullRequest, X, type LucideIcon } from "lucide-react";

import { tallyLine, type RevisionTally, type RunTally } from "@/components/gate/copy";
import { MonoId } from "@/components/gate/mono-id";
import { TONE_CLASSES } from "@/components/shared";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AttemptView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

function AttemptTile({ attempt }: { attempt: AttemptView }) {
  const failed = attempt.outcome === "fail";
  const passed = attempt.outcome === "pass";
  const tone = TONE_CLASSES[failed ? "bad" : passed ? "good" : "unknown"];
  const Icon = failed ? X : Check;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          tabIndex={0}
          className={cn("flex size-10 items-center justify-center rounded-md border transition-colors", tone.bg, tone.border)}
          aria-label={`Attempt ${attempt.attempt}: ${attempt.outcome}`}
        >
          {passed || failed ? <Icon className={cn("size-4", tone.text)} strokeWidth={2.5} aria-hidden /> : <span className={cn("size-1.5 rounded-full", tone.dot)} />}
        </div>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">
        Attempt {attempt.attempt} · {attempt.outcome}: {attempt.observed}
      </TooltipContent>
    </Tooltip>
  );
}

function RevisionPanel({
  label,
  icon: Icon,
  sha,
  tally,
  attempts,
  attackIds,
}: {
  label: string;
  icon: LucideIcon;
  sha: string;
  tally: RevisionTally;
  attempts: AttemptView[];
  attackIds: string[];
}) {
  const tone = tally.failed > 0 ? TONE_CLASSES.bad : tally.total > 0 ? TONE_CLASSES.good : null;
  return (
    <div className="bg-card min-w-0 rounded-xl border p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="text-muted-foreground size-4" aria-hidden />
          {label}
          <span className="text-muted-foreground text-xs font-normal">
            <MonoId value={sha} ellipsis={false} />
          </span>
        </div>
        <div className="text-right">
          <span className={cn("text-2xl font-semibold tracking-tight tabular-nums", tone?.text)}>
            {tally.failed}/{tally.total}
          </span>
          <span className="text-muted-foreground ml-1.5 text-xs">failed</span>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {attackIds.map((attackId) => {
          const rows = attempts.filter((a) => a.attack_id === attackId);
          if (rows.length === 0) return null;
          return (
            <div key={attackId} className="flex items-center justify-between gap-3">
              <code className="text-muted-foreground min-w-0 truncate font-mono text-xs">{attackId}</code>
              <div className="flex shrink-0 gap-1.5">
                {rows.map((a) => (
                  <AttemptTile key={`${a.attack_id}-${a.attempt}`} attempt={a} />
                ))}
              </div>
            </div>
          );
        })}
        {attempts.length === 0 && <p className="text-muted-foreground text-sm">No attempts on this revision.</p>}
      </div>
    </div>
  );
}

/** Head vs base, side by side: the core evidence for attribution. */
export function RevisionCompare({
  attempts,
  tally,
  headSha,
  baseSha,
}: {
  attempts: AttemptView[];
  tally: RunTally;
  headSha: string;
  baseSha: string;
}) {
  const attackIds = [...new Set(attempts.map((a) => a.attack_id))];
  const onlyHead = tally.head.failed > 0 && tally.base.failed === 0;
  const both = tally.head.failed > 0 && tally.base.failed > 0;
  return (
    <div>
      <div className="grid gap-3 md:grid-cols-2">
        <RevisionPanel label="Head" icon={GitPullRequest} sha={headSha} tally={tally.head} attempts={attempts.filter((a) => a.revision === "head")} attackIds={attackIds} />
        <RevisionPanel label="Base" icon={GitBranch} sha={baseSha} tally={tally.base} attempts={attempts.filter((a) => a.revision === "base")} attackIds={attackIds} />
      </div>
      <div className="text-muted-foreground mt-3 flex flex-col gap-1 text-xs sm:flex-row sm:items-center sm:justify-between">
        <span className="text-foreground font-mono tabular-nums">{tallyLine(tally)}</span>
        <span>
          {onlyHead
            ? "Fails only with this PR applied: attributed to the PR."
            : both
              ? "Fails on both revisions: the problem predates this PR."
              : tally.head.total > 0
                ? "No failures on either revision."
                : "Nothing executed."}
        </span>
      </div>
    </div>
  );
}
