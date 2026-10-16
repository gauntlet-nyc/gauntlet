import { FileWarning } from "lucide-react";

import { TONE_CLASSES } from "@/components/shared";
import { cn } from "@/lib/utils";

import { formatDateTime } from "./model";

const MS_PER_DAY = 86_400_000;

export function TriggerCard({
  trigger,
  kind,
  startAt,
  endAt,
  recallIds,
}: {
  trigger: string;
  kind: string;
  startAt: string;
  endAt: string;
  recallIds: readonly string[];
}) {
  const days = Math.round((Date.parse(endAt) - Date.parse(startAt)) / MS_PER_DAY);
  return (
    <div className="bg-card flex h-full flex-col rounded-xl border p-5">
      <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
        <FileWarning className={cn("size-4", TONE_CLASSES.bad.text)} aria-hidden />
        Trigger
      </div>
      <div className="mt-3 font-mono text-2xl font-semibold tracking-tight">{trigger}</div>
      <p className="text-muted-foreground mt-1 text-sm">
        Suspect knowledge-base chunk <span className="font-mono text-xs">({kind})</span>. Every decision that read it, directly
        or through memory, is replayed without it.
      </p>
      <dl className="mt-auto grid gap-2.5 border-t pt-4 text-xs [&>div]:flex [&>div]:justify-between [&>div]:gap-4">
        <div>
          <dt className="text-muted-foreground">Window</dt>
          <dd className="text-right tabular-nums">
            {formatDateTime(startAt)} to {formatDateTime(endAt)} <span className="text-muted-foreground">({days}d, UTC)</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Mode</dt>
          <dd className="text-right">Lineage, counterfactual replay, event audit</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Recall</dt>
          <dd className="text-right font-mono">{recallIds.join(" · ")}</dd>
        </div>
      </dl>
    </div>
  );
}
