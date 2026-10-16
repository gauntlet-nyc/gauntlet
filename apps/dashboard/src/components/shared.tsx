import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  FileCode2,
  FlaskConical,
  ServerCrash,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card as UiCard, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { classificationTone, isOffline, type Provenance } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export type Tone = "bad" | "good" | "unknown";

/** Tailwind classes per verdict tone. Color in this product only ever means a verdict. */
export const TONE_CLASSES: Record<Tone, { text: string; bg: string; border: string; dot: string }> = {
  bad: { text: "text-regression", bg: "bg-regression/10", border: "border-regression/30", dot: "bg-regression" },
  good: { text: "text-passed", bg: "bg-passed/10", border: "border-passed/30", dot: "bg-passed" },
  unknown: { text: "text-inconclusive", bg: "bg-inconclusive/10", border: "border-inconclusive/30", dot: "bg-inconclusive" },
};

const TONE_ICON: Record<Tone, LucideIcon> = { bad: XCircle, good: CheckCircle2, unknown: CircleDashed };

export function toneOf(value: string): Tone {
  return classificationTone(value);
}

export function StatusPill({ value, size = "sm" }: { value: string; size?: "sm" | "lg" }) {
  const tone = TONE_CLASSES[toneOf(value)];
  return (
    <Badge
      variant="outline"
      data-testid="status-pill"
      className={cn(
        "gap-1.5 rounded-full font-medium",
        tone.text,
        tone.bg,
        tone.border,
        size === "lg" ? "h-7 px-3 text-sm" : "h-5 px-2 text-xs",
      )}
    >
      <span className={cn("size-1.5 rounded-full", tone.dot)} aria-hidden />
      {value.replaceAll("_", " ")}
    </Badge>
  );
}

export function ToneIcon({ value, className }: { value: string; className?: string }) {
  const tone = toneOf(value);
  const Icon = TONE_ICON[tone];
  return <Icon className={cn("size-4", TONE_CLASSES[tone].text, className)} aria-hidden />;
}

/** Shown whenever any data on the page came from fakes, recordings or fixtures. Compact by design. */
export function OfflineBadge({ provenance }: { provenance: readonly Provenance[] }) {
  if (!isOffline(provenance)) return null;
  return (
    <span
      role="status"
      data-testid="offline-badge"
      title="Data on this page comes from recordings, fixtures or fakes; no provider was contacted."
      className="border-inconclusive/25 bg-inconclusive/[0.06] text-inconclusive inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium whitespace-nowrap"
    >
      <FlaskConical className="size-3" aria-hidden />
      OFFLINE / live NOT RUN
    </span>
  );
}

export function ProvenanceList({ provenance }: { provenance: readonly Provenance[] }) {
  const unique = provenance.filter(
    (p, i, all) => all.findIndex((q) => q.provider === p.provider && q.label === p.label) === i,
  );
  return (
    <ul className="divide-border divide-y rounded-lg border">
      {unique.map((p) => (
        <li key={`${p.provider}-${p.label}`} className="flex items-start gap-3 px-4 py-3 text-sm">
          <span
            className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", p.live ? "bg-passed" : "bg-muted-foreground/50")}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <code className="font-mono text-xs">{p.provider}</code>
              <Badge variant="outline" className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
                {p.live ? "LIVE" : "OFFLINE"}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">{p.label}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  icon: Icon,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <div className="text-muted-foreground mb-3 flex items-center gap-2 text-xs font-medium tracking-wide uppercase">
            {Icon && <Icon className="size-3.5" aria-hidden />}
            {eyebrow}
          </div>
        )}
        <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-[34px]">{title}</h1>
        {description && <p className="text-muted-foreground mt-2.5 max-w-2xl text-[15px] leading-relaxed">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({
  title,
  description,
  icon: Icon,
  actions,
  children,
  className,
  id,
}: {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("mt-10 scroll-mt-20", className)}>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
            {Icon && <Icon className="text-muted-foreground size-4" aria-hidden />}
            {title}
          </h2>
          {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, tone, className }: { children: ReactNode; tone?: string; className?: string }) {
  const t = tone ? TONE_CLASSES[toneOf(tone)] : null;
  return (
    <UiCard className={cn("gap-0 py-0", t && t.border, className)}>
      <CardContent className="px-5 py-4">{children}</CardContent>
    </UiCard>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
}) {
  return (
    <UiCard className="gap-0 py-0">
      <CardContent className="px-5 py-4">
        <div className="text-muted-foreground flex items-center justify-between text-xs font-medium">
          <span>{label}</span>
          {Icon && <Icon className={cn("size-4", tone ? TONE_CLASSES[tone].text : "opacity-60")} aria-hidden />}
        </div>
        <div className={cn("mt-2 text-3xl font-semibold tracking-tight tabular-nums", tone && TONE_CLASSES[tone].text)}>
          {value}
        </div>
        {hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
      </CardContent>
    </UiCard>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = CircleSlash,
  children,
}: {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center">
      <div className="bg-muted mb-3 flex size-10 items-center justify-center rounded-full">
        <Icon className="text-muted-foreground size-5" aria-hidden />
      </div>
      <p className="font-medium">{title}</p>
      {description && <p className="text-muted-foreground mt-1 max-w-sm text-sm">{description}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

/** Unified diff with per-line add/remove/hunk coloring. */
export function DiffView({ path, diff, className }: { path?: string; diff: string; className?: string }) {
  const lines = diff.replace(/\n$/, "").split("\n");
  return (
    <div className={cn("bg-card overflow-hidden rounded-lg border", className)}>
      {path && (
        <div className="bg-muted/40 text-muted-foreground flex items-center gap-2 border-b px-4 py-2 font-mono text-xs">
          <FileCode2 className="size-3.5" aria-hidden />
          {path}
        </div>
      )}
      <pre className="overflow-x-auto py-2 font-mono text-[12.5px] leading-6">
        {lines.map((line, i) => {
          const kind = line.startsWith("@@")
            ? "hunk"
            : line.startsWith("+++") || line.startsWith("---")
              ? "meta"
              : line.startsWith("+")
                ? "add"
                : line.startsWith("-")
                  ? "del"
                  : "ctx";
          return (
            <div
              key={i}
              className={cn(
                "grid grid-cols-[2rem_1fr] pr-4",
                kind === "add" && "bg-passed/[0.08] text-passed",
                kind === "del" && "bg-regression/[0.08] text-regression",
                kind === "hunk" && "bg-muted/60 text-muted-foreground",
                kind === "meta" && "text-muted-foreground/70",
              )}
            >
              <span className="text-muted-foreground/40 text-center select-none">
                {kind === "add" ? "+" : kind === "del" ? "−" : ""}
              </span>
              <span className="whitespace-pre">{kind === "add" || kind === "del" ? line.slice(1) : line}</span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}

export function ErrorPanel({ what, error }: { what: string; error: unknown }) {
  return (
    <main className="mx-auto max-w-xl py-16">
      <div className="bg-card rounded-xl border p-8 text-center">
        <div className="bg-regression/10 mx-auto mb-4 flex size-12 items-center justify-center rounded-full">
          <ServerCrash className="text-regression size-6" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold">{what} unavailable</h1>
        <p className="text-muted-foreground mt-2 text-sm">Could not reach the Gauntlet API: {String(error)}</p>
        <p className="text-muted-foreground mt-4 text-sm">
          Start it with{" "}
          <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">uv run uvicorn gauntlet.api.main:app --port 8000</code>.
        </p>
      </div>
    </main>
  );
}

export function Banner({ params }: { params: Record<string, string | string[] | undefined> }) {
  const approval = params.approval;
  if (!approval) return null;
  const ok = approval === "recorded";
  const Icon = ok ? ShieldCheck : AlertTriangle;
  return (
    <div
      role="status"
      className={cn(
        "my-4 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm",
        ok ? "border-passed/30 bg-passed/[0.07] text-passed" : "border-regression/30 bg-regression/[0.07] text-regression",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>
        {ok
          ? "Decision recorded and bound to this exact plan hash. Nothing was merged, deployed, refunded or sent."
          : `Decision refused by the API (HTTP ${String(approval)}). 401 = log in; 409 = plan changed, review again.`}
      </span>
    </div>
  );
}

type DecideProps = {
  action: (form: FormData) => Promise<void>;
  runId: string;
  subject: "fix_plan" | "remediation" | "scope";
  subjectId: string;
  planSha256: string;
  back: string;
  approveLabel?: string;
};

export function DecideForm({ action, runId, subject, subjectId, planSha256, back, approveLabel = "Approve" }: DecideProps) {
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="subject" value={subject} />
      <input type="hidden" name="subject_id" value={subjectId} />
      <input type="hidden" name="plan_sha256" value={planSha256} />
      <input type="hidden" name="back" value={back} />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input name="reason" placeholder="Reason (required to reject)" className="flex-1" />
        <div className="flex gap-2">
          <Button type="submit" name="decision" value="approved">
            <ShieldCheck aria-hidden />
            {approveLabel}
          </Button>
          <Button type="submit" name="decision" value="rejected" variant="outline">
            Reject
          </Button>
        </div>
      </div>
      <p className="text-muted-foreground text-xs">
        Binds to plan hash <code className="font-mono">{planSha256.slice(0, 16)}…</code>. Human decision only; no auto-merge or
        remediation.
      </p>
    </form>
  );
}
