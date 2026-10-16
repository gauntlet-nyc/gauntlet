import { ArrowUpRight, History, ShieldCheck, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { CountUp } from "@/components/overview/count-up";
import type { AuditView, GateRunSummary } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

interface Metric {
  label: string;
  value: number;
  bad?: boolean;
}

function ProductCard({
  href,
  icon: Icon,
  name,
  line,
  metrics,
}: {
  href: string;
  icon: LucideIcon;
  name: string;
  line: string;
  metrics: Metric[] | null;
}) {
  return (
    <Link
      href={href}
      className="group bg-card hover:border-foreground/20 focus-visible:ring-ring/50 flex w-full flex-col rounded-xl border p-5 transition-colors outline-none focus-visible:ring-[3px]"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Icon className="text-muted-foreground size-4" aria-hidden />
          <h3 className="text-[15px] font-semibold tracking-tight">{name}</h3>
        </div>
        <ArrowUpRight
          className="text-muted-foreground group-hover:text-foreground size-4 transition-[color,transform] group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          aria-hidden
        />
      </div>
      <p className="text-muted-foreground mt-1.5 text-sm">{line}</p>
      {metrics ? (
        <div className="mt-6 grid grid-cols-3 gap-4">
          {metrics.map((m) => (
            <div key={m.label}>
              <div
                className={cn("text-2xl font-semibold tracking-tight tabular-nums", m.bad && m.value > 0 && "text-regression")}
              >
                <CountUp value={m.value} />
              </div>
              <div className="text-muted-foreground mt-0.5 text-xs">{m.label}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground mt-6 text-xs">Live numbers unavailable while the API is offline.</p>
      )}
    </Link>
  );
}

export function GateCard({ runs }: { runs: GateRunSummary[] | null }) {
  return (
    <ProductCard
      href="/gate"
      icon={ShieldCheck}
      name="Gate"
      line="Before merge: attack what the PR changed, on base and head."
      metrics={
        runs && [
          { label: "Runs", value: runs.length },
          { label: "Regressions", value: runs.filter((r) => r.attribution === "introduced").length, bad: true },
          { label: "Passed", value: runs.filter((r) => r.status === "passed").length },
        ]
      }
    />
  );
}

export function RecallCard({ audit }: { audit: AuditView | null }) {
  const s = audit?.summary;
  return (
    <ProductCard
      href="/recall"
      icon={History}
      name="Recall"
      line="After it shipped: audit past agent decisions and replay them."
      metrics={
        s
          ? [
              { label: "Audited", value: s.audited },
              { label: "Violations", value: s.violations, bad: true },
              { label: "Clear", value: s.clear },
            ]
          : null
      }
    />
  );
}
