import { ArrowUpRight, History, ShieldCheck, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { CountUp } from "@/components/overview/count-up";
import { StatusPill } from "@/components/shared";
import type { AuditView, GateRunSummary } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

const LATEST_RUNS = 4;

function ProductCard({
  href,
  icon: Icon,
  name,
  tagline,
  description,
  cta,
  children,
}: {
  href: string;
  icon: LucideIcon;
  name: string;
  tagline: string;
  description: string;
  cta: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group bg-card hover:border-foreground/20 w-full focus-visible:ring-ring/50 relative flex flex-col rounded-xl border transition-colors outline-none focus-visible:ring-[3px]"
    >
      <div className="flex items-start justify-between gap-4 px-5 pt-5">
        <div className="flex items-center gap-3">
          <div className="bg-foreground/[0.04] flex size-9 items-center justify-center rounded-lg border">
            <Icon className="size-4.5" aria-hidden />
          </div>
          <div>
            <h3 className="text-[15px] leading-tight font-semibold tracking-tight">{name}</h3>
            <p className="text-muted-foreground text-xs">{tagline}</p>
          </div>
        </div>
        <ArrowUpRight
          className="text-muted-foreground group-hover:text-foreground size-4 transition-[color,transform] group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          aria-hidden
        />
      </div>
      <p className="text-muted-foreground mt-3 px-5 text-sm leading-relaxed">{description}</p>
      <div className="mt-5 flex-1 border-t px-5 py-4">{children}</div>
      <div className="text-muted-foreground group-hover:text-foreground border-t px-5 py-3 text-xs font-medium transition-colors">
        {cta}
      </div>
    </Link>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="min-w-0">
      <div className={cn("text-2xl font-semibold tracking-tight tabular-nums", tone)}>
        <CountUp value={value} />
      </div>
      <div className="text-muted-foreground mt-0.5 truncate text-xs">{label}</div>
    </div>
  );
}

function Unavailable({ what }: { what: string }) {
  return (
    <p className="text-muted-foreground flex h-full min-h-24 items-center text-xs">
      Live {what} unavailable. Start the Gauntlet API to see them here.
    </p>
  );
}

export function GateCard({ runs }: { runs: GateRunSummary[] | null }) {
  const regressions = runs?.filter((r) => r.attribution === "introduced").length ?? 0;
  const passed = runs?.filter((r) => r.status === "passed").length ?? 0;
  return (
    <ProductCard
      href="/gate"
      icon={ShieldCheck}
      name="Gate"
      tagline="Before merge"
      description="Reads the PR diff, plans attacks against what changed, runs each one on base and head, and lets independent oracles decide."
      cta="Open Gate"
    >
      {runs === null ? (
        <Unavailable what="run numbers" />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Runs" value={runs.length} />
            <Metric label="Regressions" value={regressions} tone={regressions > 0 ? "text-regression" : undefined} />
            <Metric label="Passed" value={passed} />
          </div>
          {runs.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {runs.slice(0, LATEST_RUNS).map((run) => (
                <li key={run.run_id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="truncate font-mono text-xs" title={run.run_id}>
                    {run.run_id}
                  </span>
                  <StatusPill value={run.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-xs">No runs yet. Start one to see verdicts here.</p>
          )}
        </div>
      )}
    </ProductCard>
  );
}

export function RecallCard({ audit }: { audit: AuditView | null }) {
  const s = audit?.summary;
  const segments = s
    ? [
        { key: "violations", value: s.violations, className: "bg-regression" },
        { key: "inconclusive", value: s.inconclusive, className: "bg-inconclusive" },
        { key: "clear", value: s.clear, className: "bg-foreground/25" },
      ]
    : [];
  return (
    <ProductCard
      href="/recall"
      icon={History}
      name="Recall"
      tagline="After it shipped"
      description="Audits past AI-agent decisions from recorded history, traces what a bad source touched, and replays them with it removed."
      cta="Open Recall"
    >
      {!s ? (
        <Unavailable what="audit numbers" />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Audited" value={s.audited} />
            <Metric label="Violations" value={s.violations} tone={s.violations > 0 ? "text-regression" : undefined} />
            <Metric label="Clear" value={s.clear} />
          </div>
          <div>
            <div className="flex h-2 gap-0.5 overflow-hidden rounded-full" aria-hidden>
              {segments
                .filter((seg) => seg.value > 0)
                .map((seg) => (
                  <div key={seg.key} className={seg.className} style={{ flexGrow: seg.value }} />
                ))}
            </div>
            <div className="text-muted-foreground mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {segments.map((seg) => (
                <span key={seg.key} className="inline-flex items-center gap-1.5">
                  <span className={cn("size-1.5 rounded-full", seg.className)} aria-hidden />
                  <span className="text-foreground tabular-nums">{seg.value}</span> {seg.key}
                </span>
              ))}
            </div>
          </div>
          <dl className="divide-y rounded-lg border text-xs">
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <dt className="text-muted-foreground">Audited tool</dt>
              <dd className="font-mono">{s.tool_name}</dd>
            </div>
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <dt className="text-muted-foreground">Window</dt>
              <dd className="font-mono tabular-nums">
                {s.start_at.slice(0, 10)} → {s.end_at.slice(0, 10)}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <dt className="text-muted-foreground">Proposals</dt>
              <dd className="tabular-nums">{audit?.proposals.length ?? 0} drafts, none applied</dd>
            </div>
          </dl>
        </div>
      )}
    </ProductCard>
  );
}
