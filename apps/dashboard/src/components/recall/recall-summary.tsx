import { TONE_CLASSES, type Tone } from "@/components/shared";
import { cn } from "@/lib/utils";

interface Figure {
  value: number;
  label: string;
  detail?: string;
  tone?: Tone;
}

/** One slim row of plain numbers. Color only where the number carries a verdict. */
export function RecallSummary({
  exposed,
  direct,
  tainted,
  cleared,
  notReplayable,
  audited,
  violations,
}: {
  exposed: number;
  direct: number;
  tainted: number;
  cleared: number;
  notReplayable: number;
  audited: number;
  violations: number;
}) {
  const figures: Figure[] = [
    { value: exposed, label: "exposed", detail: `${direct} direct · ${exposed - direct} second-order` },
    { value: tainted, label: "tainted", tone: "bad" },
    { value: cleared, label: "cleared", tone: "good" },
    { value: notReplayable, label: "not replayable", tone: "unknown" },
  ];
  return (
    <div className="flex flex-col gap-3 border-b pb-5 md:flex-row md:items-baseline md:justify-between">
      <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:flex sm:items-baseline sm:gap-0 sm:divide-x">
        {figures.map((f) => (
          <div key={f.label} className="flex items-baseline gap-2 sm:px-6 sm:first:pl-0">
            <span className={cn("text-2xl font-semibold tracking-tight tabular-nums", f.tone && TONE_CLASSES[f.tone].text)}>
              {f.value}
            </span>
            <span className="text-muted-foreground text-sm">
              {f.label}
              {f.detail && <span className="text-muted-foreground/80 block text-xs sm:ml-1.5 sm:inline">({f.detail})</span>}
            </span>
          </div>
        ))}
      </div>
      <p className="text-muted-foreground text-sm tabular-nums">
        <span className="text-foreground font-medium">{audited} operations audited</span> ·{" "}
        <span className={cn("font-medium", violations > 0 && TONE_CLASSES.bad.text)}>
          {violations} violation{violations === 1 ? "" : "s"}
        </span>
      </p>
    </div>
  );
}
