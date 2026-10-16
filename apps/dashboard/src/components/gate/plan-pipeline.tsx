import {
  Camera,
  FileCode2,
  Keyboard,
  MessageSquare,
  Monitor,
  MousePointerClick,
  Navigation,
  ScanSearch,
  ScrollText,
  Send,
  Target,
  Type,
  type LucideIcon,
} from "lucide-react";

import { humanize } from "@/components/gate/copy";
import { Badge } from "@/components/ui/badge";
import type { GateRunView } from "@/lib/gauntlet";

type Attack = GateRunView["attacks"][number];
type Step = Attack["steps"][number];

const STEP_ICON: Record<Step["action"], LucideIcon> = {
  navigate: Navigation,
  resize: Monitor,
  click: MousePointerClick,
  scroll: ScrollText,
  type: Type,
  press: Keyboard,
  inspect: ScanSearch,
  capture: Camera,
  test_api: Send,
  chat: MessageSquare,
};

function stepDetail(step: Step): string {
  switch (step.action) {
    case "navigate":
      return step.path;
    case "resize":
      return `${step.width}×${step.height}`;
    case "click":
    case "inspect":
      return step.target;
    case "scroll":
      return `${step.delta_y > 0 ? "+" : ""}${step.delta_y}px${step.target ? ` on ${step.target}` : ""}`;
    case "type":
      return `${step.target} ← "${step.value}"`;
    case "press":
      return step.key;
    case "capture":
      return step.label ?? "screenshot";
    case "test_api":
      return `${step.method} ${step.path} as ${step.actor_id}`;
    case "chat":
      return `${step.actor_id} → ${step.agent_id}`;
  }
}

function StepNode({ step, index }: { step: Step; index: number }) {
  const Icon = STEP_ICON[step.action];
  return (
    <li className="group relative flex min-w-0 gap-3 pb-4 last:pb-0 md:flex-1 md:flex-col md:gap-2 md:pb-0">
      <div className="bg-border absolute top-9 bottom-0 left-[17px] w-px md:top-[17px] md:right-0 md:left-9 md:h-px md:w-auto group-last:hidden" aria-hidden />
      <div className="bg-background relative z-10 flex size-9 shrink-0 items-center justify-center rounded-lg border">
        <Icon className="size-4" aria-hidden />
      </div>
      <div className="min-w-0 pt-0.5 md:pt-0 md:pr-3">
        <div className="text-muted-foreground text-[11px] font-medium tabular-nums">
          {String(index + 1).padStart(2, "0")} · {step.action === "test_api" ? "API request" : humanize(step.action)}
        </div>
        <div className="mt-0.5 truncate font-mono text-xs" title={stepDetail(step)}>
          {stepDetail(step)}
        </div>
        {step.action === "chat" && <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">&ldquo;{step.message}&rdquo;</p>}
      </div>
    </li>
  );
}

/** One frozen attack: what it suspects, the exact steps, and how it will be judged. */
export function AttackCard({ attack }: { attack: Attack }) {
  return (
    <article className="bg-card overflow-hidden rounded-xl border">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
        <code className="min-w-0 truncate font-mono text-xs">{attack.attack_id}</code>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
            {attack.worker_kind.replaceAll("_", " ")} worker
          </Badge>
          <span className="text-muted-foreground text-[11px] tabular-nums">
            ≤{attack.max_actions} actions · ≤{attack.max_runtime_seconds}s
          </span>
        </div>
      </header>
      <div className="p-5">
        <p className="text-[15px] leading-relaxed font-medium">{attack.hypothesis}</p>
        <ol className="mt-5 flex flex-col md:flex-row" aria-label="Attack steps">
          {attack.steps.map((s, i) => (
            <StepNode key={i} step={s} index={i} />
          ))}
        </ol>
        <dl className="mt-6 grid gap-4 border-t pt-4 text-sm md:grid-cols-3">
          <div className="min-w-0">
            <dt className="text-muted-foreground text-xs font-medium">Why this change</dt>
            <dd className="mt-1 leading-relaxed">{attack.why_this_change}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
              <Target className="size-3" aria-hidden />
              Oracle expects
            </dt>
            <dd className="mt-1 leading-relaxed">{attack.expected_observation}</dd>
            <dd className="mt-1.5 flex flex-wrap gap-1">
              {attack.oracle_ids.map((o) => (
                <code key={o} className="bg-muted rounded px-1.5 py-0.5 font-mono text-[11px]">
                  {o}
                </code>
              ))}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground text-xs font-medium">Cited lines</dt>
            {(attack.source_refs ?? []).map((r) => (
              <dd key={`${r.path}:${r.start_line}`} className="mt-1 flex min-w-0 items-center gap-1.5 font-mono text-xs">
                <FileCode2 className="text-muted-foreground size-3 shrink-0" aria-hidden />
                <span className="truncate" title={r.path}>
                  {r.path}
                </span>
                <span className="text-muted-foreground shrink-0">
                  :{r.start_line}
                  {r.end_line !== r.start_line && `–${r.end_line}`}
                </span>
              </dd>
            ))}
          </div>
        </dl>
      </div>
    </article>
  );
}
