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
  return (
    <ol>
      {steps.map((step, i) => {
        const last = i === steps.length - 1;
        return (
          <li key={step.step} className={cn("relative flex gap-4", !last && "pb-5")}>
            {!last && <span className="bg-border absolute top-7 bottom-1 left-[11px] w-px" aria-hidden />}
            <span
              className={cn(
                "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-medium tabular-nums",
                step.done
                  ? "bg-foreground text-background"
                  : "text-muted-foreground bg-background border-foreground/30 border border-dashed",
              )}
              aria-label={step.done ? "done" : "to do"}
            >
              {step.done ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden /> : i + 1}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <h3 className={cn("text-sm", step.done ? "text-muted-foreground" : "font-medium")}>{step.step}</h3>
              {!step.done && (
                <div className="mt-1">
                  <Detail text={step.detail} />
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
