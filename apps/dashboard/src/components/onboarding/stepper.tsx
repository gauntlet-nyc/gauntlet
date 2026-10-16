import { Check } from "lucide-react";
import type { ReactNode } from "react";

import type { OnboardingView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

type Step = OnboardingView["steps"][number];

const MISSING_PREFIX = "missing: ";
/** Tokens that read as paths, env vars or identifiers render as code. */
const CODE_TOKEN = /[/=_]|\.py$|\.json$/;

function Detail({ text }: { text: string }) {
  if (text.startsWith(MISSING_PREFIX)) {
    const names = text.slice(MISSING_PREFIX.length).split(",").map((n) => n.trim());
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground text-xs">Missing</span>
        {names.map((n) => (
          <code key={n} className="bg-muted/60 text-foreground/80 rounded-md border px-1.5 py-0.5 font-mono text-[11px]">
            {n}
          </code>
        ))}
      </div>
    );
  }
  const parts: ReactNode[] = text.split(/(\s+)/).map((token, i) => {
    const trailing = token.match(/[;,]$/)?.[0] ?? "";
    const core = trailing ? token.slice(0, -1) : token;
    if (!CODE_TOKEN.test(core)) return token;
    return (
      <span key={i}>
        <code className="text-foreground/85 font-mono text-[12px]">{core}</code>
        {trailing}
      </span>
    );
  });
  return <p className="text-muted-foreground text-[13px] leading-relaxed">{parts}</p>;
}

export function OnboardingStepper({ steps }: { steps: Step[] }) {
  const done = steps.filter((s) => s.done).length;
  const pct = steps.length === 0 ? 0 : Math.round((done / steps.length) * 100);
  return (
    <div className="bg-card rounded-xl border">
      <div className="flex items-center gap-4 border-b px-5 py-4">
        <div className="text-sm">
          <span className="font-medium tabular-nums">
            {done} of {steps.length}
          </span>{" "}
          <span className="text-muted-foreground">steps done</span>
        </div>
        <div className="bg-foreground/10 h-1 flex-1 overflow-hidden rounded-full" aria-hidden>
          <div className="bg-foreground/70 h-full rounded-full" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <ol className="px-5 py-5">
        {steps.map((step, i) => {
          const last = i === steps.length - 1;
          return (
            <li key={step.step} className="relative flex gap-4 pb-6 last:pb-0">
              {!last && (
                <span
                  className={cn(
                    "absolute top-7 bottom-1 left-[11px] w-px",
                    step.done && steps[i + 1]?.done ? "bg-foreground/35" : "bg-border",
                  )}
                  aria-hidden
                />
              )}
              <span
                className={cn(
                  "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-medium tabular-nums",
                  step.done
                    ? "bg-foreground text-background"
                    : "text-muted-foreground bg-card border border-dashed border-foreground/30",
                )}
                aria-label={step.done ? "done" : "to do"}
              >
                {step.done ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden /> : i + 1}
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className={cn("text-sm font-medium", !step.done && "text-foreground/90")}>{step.step}</h3>
                  <span
                    className={cn(
                      "rounded-full border px-1.5 py-px text-[10px] font-medium tracking-wide uppercase",
                      step.done ? "text-muted-foreground" : "border-inconclusive/25 text-inconclusive",
                    )}
                  >
                    {step.done ? "Done" : "To do"}
                  </span>
                </div>
                <div className="mt-1.5">
                  <Detail text={step.detail} />
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
