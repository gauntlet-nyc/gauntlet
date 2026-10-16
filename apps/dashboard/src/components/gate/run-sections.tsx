import {
  ClipboardCheck,
  Flag,
  Lock,
  Map as MapIcon,
  PlayCircle,
  Server,
  ShieldCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { humanize } from "@/components/gate/copy";
import { MonoId } from "@/components/gate/mono-id";
import { StatusPill, TONE_CLASSES, toneOf } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AttemptView, GateRunView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

type RunEvent = GateRunView["events"][number];
type Finding = GateRunView["findings"][number];

export function AttemptsTable({ attempts }: { attempts: AttemptView[] }) {
  return (
    <div className="bg-card overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-muted-foreground pl-5 text-xs">Attack</TableHead>
            <TableHead className="text-muted-foreground text-xs">Revision</TableHead>
            <TableHead className="text-muted-foreground hidden text-xs md:table-cell">SHA</TableHead>
            <TableHead className="text-muted-foreground text-xs">Outcome</TableHead>
            <TableHead className="text-muted-foreground pr-5 text-xs">Oracle observed</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {attempts.map((a) => (
            <TableRow key={`${a.attack_id}-${a.revision}-${a.attempt}`} className="align-top">
              <TableCell className="max-w-56 pl-5">
                <code className="block truncate font-mono text-xs" title={a.attack_id}>
                  {a.attack_id}
                </code>
                <code className="text-muted-foreground mt-0.5 block truncate font-mono text-[11px]">{a.oracle_id}</code>
              </TableCell>
              <TableCell className="text-sm whitespace-nowrap">
                <span className="capitalize">{a.revision}</span> <span className="text-muted-foreground tabular-nums">#{a.attempt}</span>
              </TableCell>
              <TableCell className="text-muted-foreground hidden text-xs md:table-cell">
                <MonoId value={a.source_sha} ellipsis={false} />
              </TableCell>
              <TableCell>
                <StatusPill value={a.outcome} />
              </TableCell>
              <TableCell className="text-muted-foreground min-w-64 pr-5 text-sm leading-relaxed whitespace-normal">{a.observed}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ReproBar({ label, hits, total }: { label: string; hits: number; total: number }) {
  const pct = total > 0 ? (hits / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-muted-foreground w-10">{label}</span>
      <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
        <div className="bg-regression h-full rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-14 text-right font-mono tabular-nums">
        {hits}/{total}
      </span>
    </div>
  );
}

export function FindingCard({ finding }: { finding: Finding }) {
  const tone = TONE_CLASSES[toneOf(finding.status)];
  return (
    <article className={cn("bg-card rounded-xl border p-5", tone.border)}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill value={finding.status} />
        <Badge variant="outline" className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
          {finding.severity}
        </Badge>
        {finding.attribution !== "unknown" && <span className="text-muted-foreground text-xs">{humanize(finding.attribution)}</span>}
      </div>
      <code className="mt-3 block truncate font-mono text-sm" title={finding.attack_id}>
        {finding.attack_id}
      </code>
      <div className="mt-4 space-y-2">
        <ReproBar label="Head" hits={finding.head_reproductions} total={finding.head_attempts} />
        <ReproBar label="Base" hits={finding.base_reproductions} total={finding.base_attempts} />
      </div>
      {(finding.limitations ?? []).length > 0 && (
        <ul className="text-muted-foreground mt-4 list-disc space-y-1 border-t pt-3 pl-4 text-xs">
          {(finding.limitations ?? []).map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

const EVENT_ICON: Record<string, LucideIcon> = {
  impact_mapped: MapIcon,
  plan_frozen: Lock,
  environments_ready: Server,
  attempt_recorded: PlayCircle,
  finding_recorded: Flag,
  run_completed: ClipboardCheck,
  approval_recorded: ShieldCheck,
  repair_verified: Wrench,
};

/** Status is shown as a pill; opaque ids and nulls are noise in the timeline (they remain in the JSON export). */
const HIDDEN_PAYLOAD_KEYS = new Set(["status", "overall_status", "idempotency_key"]);

function payloadValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || value === null) return String(value);
  return JSON.stringify(value);
}

function elapsed(fromIso: string, toIso: string): string {
  const ms = Date.parse(toIso) - Date.parse(fromIso);
  if (!Number.isFinite(ms) || ms < 0) return "";
  return ms < 1000 ? `+${ms} ms` : `+${(ms / 1000).toFixed(2)} s`;
}

/** Ordered event log as a vertical timeline; payload fields become compact key/value chips. */
export function EventTimeline({ events }: { events: RunEvent[] }) {
  const first = events[0]?.created_at ?? "";
  return (
    <ol className="bg-card rounded-xl border px-5 py-4">
      {events.map((e, i) => {
        const Icon = EVENT_ICON[e.event_type] ?? PlayCircle;
        const status = typeof e.payload?.status === "string" ? e.payload.status : typeof e.payload?.overall_status === "string" ? e.payload.overall_status : null;
        const entries = Object.entries(e.payload ?? {}).filter(([k, v]) => !HIDDEN_PAYLOAD_KEYS.has(k) && !/(_id|_checksum)$/.test(k) && v !== null);
        return (
          <li key={e.event_id} className="relative flex gap-4 pb-5 last:pb-0">
            {i < events.length - 1 && <span className="bg-border absolute top-8 bottom-0 left-[13px] w-px" aria-hidden />}
            <div className="bg-background relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border">
              <Icon className="text-muted-foreground size-3.5" aria-hidden />
            </div>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-sm font-medium">{humanize(e.event_type)}</span>
                {status && <StatusPill value={status} />}
                <span className="text-muted-foreground text-xs">by {e.actor}</span>
                <span className="text-muted-foreground/70 ml-auto font-mono text-[11px] tabular-nums">
                  #{e.sequence} {first && elapsed(first, e.created_at)}
                </span>
              </div>
              {entries.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {entries.map(([k, v]) => {
                    const text = payloadValue(v);
                    return (
                      <span key={k} className="bg-muted/60 inline-flex max-w-full min-w-0 items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px]" title={text}>
                        <span className="text-muted-foreground shrink-0">{k}</span>
                        <span className="truncate">{text.length > 24 ? `${text.slice(0, 24)}…` : text}</span>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
