"use client";

import { useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";

import { StatusPill } from "@/components/shared";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export interface TimelineRow {
  id: string;
  day: string;
  time: string;
  requester: string;
  action: string;
  amount: string | null;
  sources: string[];
  exposure: string | null;
  audit: string | null;
}

type Filter = "all" | "flagged";

const SERIES = [
  { key: "tainted", label: "tainted", color: "var(--regression)" },
  { key: "cleared", label: "cleared", color: "var(--passed)" },
  { key: "not_replayable", label: "not replayable", color: "var(--inconclusive)" },
  { key: "unexposed", label: "not exposed", color: "oklch(1 0 0 / 9%)" },
] as const;

type DayBucket = { day: string } & Record<(typeof SERIES)[number]["key"], number>;

function bucketByDay(rows: readonly TimelineRow[]): DayBucket[] {
  const days = new Map<string, DayBucket>();
  for (const r of rows) {
    const b = days.get(r.day) ?? { day: r.day, tainted: 0, cleared: 0, not_replayable: 0, unexposed: 0 };
    const key = r.exposure && r.exposure in b ? (r.exposure as keyof Omit<DayBucket, "day">) : "unexposed";
    b[key] += 1;
    days.set(r.day, b);
  }
  return [...days.values()];
}

function DayChart({ rows, highlightSources }: { rows: readonly TimelineRow[]; highlightSources: string }) {
  const data = useMemo(() => bucketByDay(rows), [rows]);
  const reduce = useReducedMotion();
  return (
    <div className="border-b px-4 pt-4 pb-2">
      <div className="text-muted-foreground mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span>Decisions per day, by exposure to {highlightSources}</span>
        <span className="flex flex-wrap gap-3">
          {SERIES.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span className="size-1.5 rounded-full" style={{ background: s.color }} aria-hidden />
              {s.label}
            </span>
          ))}
        </span>
      </div>
      <div className="h-28">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="28%" maxBarSize={40} margin={{ top: 4, right: 0, bottom: 0, left: -28 }}>
            <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
            <ChartTooltip
              cursor={{ fill: "oklch(1 0 0 / 4%)" }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--foreground)", fontWeight: 500 }}
              itemStyle={{ padding: 0 }}
            />
            {SERIES.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stackId="d"
                fill={s.color}
                radius={i === SERIES.length - 1 ? [3, 3, 0, 0] : 0}
                isAnimationActive={!reduce}
                animationDuration={700}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function DecisionTimeline({
  rows,
  trigger,
  highlight,
}: {
  rows: readonly TimelineRow[];
  trigger: string;
  highlight: readonly string[];
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const flaggedCount = rows.filter((r) => r.exposure || r.audit).length;
  const shown = filter === "all" ? rows : rows.filter((r) => r.exposure || r.audit);

  return (
    <div className="overflow-hidden rounded-xl border">
      <DayChart rows={rows} highlightSources={trigger} />
      <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
        <span className="text-muted-foreground text-xs tabular-nums">
          {shown.length} of {rows.length} decisions
        </span>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={filter}
          onValueChange={(v) => v && setFilter(v as Filter)}
          aria-label="Filter decisions"
        >
          <ToggleGroupItem value="all" className="px-3 text-xs">
            All
          </ToggleGroupItem>
          <ToggleGroupItem value="flagged" className="px-3 text-xs">
            Flagged <span className="text-muted-foreground ml-1 tabular-nums">{flaggedCount}</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <ScrollArea className="h-[400px]">
        <Table>
          <TableHeader className="bg-background sticky top-0 z-10">
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Time (UTC)</TableHead>
              <TableHead>Decision</TableHead>
              <TableHead>Requester</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Sources</TableHead>
              <TableHead className="pr-4">Flags</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((r, i) => {
              const newDay = i === 0 || shown[i - 1]?.day !== r.day;
              return (
                <TableRow key={r.id} className={cn(newDay && i > 0 && "border-t-foreground/10")}>
                  <TableCell className="pl-4 text-xs tabular-nums">
                    <span className={cn("inline-block w-12", newDay ? "text-foreground font-medium" : "text-transparent")}>
                      {r.day}
                    </span>
                    <span className="text-muted-foreground ml-2 font-mono">{r.time}</span>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{r.requester}</TableCell>
                  <TableCell className="text-xs">
                    {r.action}
                    {r.amount && <span className="text-muted-foreground ml-1.5 font-mono tabular-nums">{r.amount}</span>}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {r.sources.map((s) => (
                        <code
                          key={s}
                          className={cn(
                            "rounded px-1.5 py-0.5 font-mono text-[11px]",
                            highlight.includes(s) ? "bg-foreground/10 text-foreground" : "text-muted-foreground",
                          )}
                        >
                          {s}
                        </code>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="pr-4">
                    <div className="flex gap-1">
                      {r.exposure && <StatusPill value={r.exposure} />}
                      {r.audit && <StatusPill value={r.audit} />}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}
