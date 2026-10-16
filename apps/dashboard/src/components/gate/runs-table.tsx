import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { humanize, runIndex } from "@/components/gate/copy";
import { StatusPill } from "@/components/shared";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { gateSummaryEvidence, type ChangeOption, type GateRunSummary } from "@/lib/gauntlet";

export function RunsTable({ runs, changes }: { runs: GateRunSummary[]; changes: ChangeOption[] }) {
  const intentOf = new Map(changes.map((c) => [c.change_id, c.feature_intent]));
  return (
    <div className="bg-card overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-muted-foreground w-16 pl-5 text-xs">#</TableHead>
            <TableHead className="text-muted-foreground text-xs">Change</TableHead>
            <TableHead className="text-muted-foreground text-xs">Verdict</TableHead>
            <TableHead className="text-muted-foreground hidden text-xs sm:table-cell">Source</TableHead>
            <TableHead className="w-10 pr-5" aria-label="Open" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((r) => {
            const href = `/gate/runs/${encodeURIComponent(r.run_id)}`;
            return (
              <TableRow key={r.run_id} className="group relative">
                <TableCell className="text-muted-foreground pl-5 font-mono text-xs tabular-nums">{runIndex(r.run_id) ?? "—"}</TableCell>
                <TableCell className="max-w-0 min-w-48 py-3">
                  <Link
                    href={href}
                    title={r.run_id}
                    className="block truncate font-medium after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
                  >
                    {intentOf.get(r.change_id) ?? r.change_id}
                  </Link>
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <StatusPill value={r.status} />
                  {r.attribution !== "unknown" && <span className="text-muted-foreground ml-2 hidden text-xs md:inline">{humanize(r.attribution)}</span>}
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <span className="text-muted-foreground text-xs">{gateSummaryEvidence(r.offline)}</span>
                </TableCell>
                <TableCell className="pr-5 text-right">
                  <ChevronRight className="text-muted-foreground/50 group-hover:text-foreground ml-auto size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
