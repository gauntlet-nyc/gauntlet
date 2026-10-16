import { AlertTriangle, History } from "lucide-react";

import { startRun } from "@/app/actions";
import { RunsTable } from "@/components/gate/runs-table";
import { StartRunForm } from "@/components/gate/start-run-form";
import { Reveal } from "@/components/motion/reveal";
import { EmptyState, ErrorPanel, PageHeader, toneOf } from "@/components/shared";
import { api } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function GatePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  let changes, runs;
  try {
    [changes, runs] = await Promise.all([api.changes(), api.runs()]);
  } catch (err) {
    return <ErrorPanel what="Gate" error={err} />;
  }
  const regressions = runs.filter((r) => toneOf(r.status) === "bad").length;
  const passed = runs.filter((r) => toneOf(r.status) === "good").length;
  return (
    <main>
      <PageHeader
        title="Gate"
        description="Attack each pull request on base and head; independent oracles decide."
        actions={runs.some((r) => r.offline) ? (
          <span
            role="status"
            title="At least one listed run contains offline evidence or has no execution adapter recorded; open a run for details."
            className="border-inconclusive/25 bg-inconclusive/[0.06] text-inconclusive inline-flex h-6 items-center rounded-full border px-2.5 text-[11px] font-medium whitespace-nowrap"
          >
            SOME RUNS: OFFLINE OR UNREPORTED EVIDENCE
          </span>
        ) : undefined}
      />
      {params.error && (
        <p role="alert" className="text-regression mb-4 flex items-center gap-2 text-sm">
          <AlertTriangle className="size-4 shrink-0" aria-hidden />
          Could not start run (HTTP {params.error}).
        </p>
      )}

      <Reveal>
        <StartRunForm action={startRun} changes={changes} />
      </Reveal>

      <Reveal index={1} className="mt-12">
        <div className="mb-3 flex items-baseline justify-between gap-4">
          <h2 className="text-base font-semibold tracking-tight">Runs</h2>
          {runs.length > 0 && (
            <p className="text-muted-foreground text-xs tabular-nums">
              {runs.length} runs · <span className={regressions > 0 ? "text-regression" : undefined}>{regressions} regressions</span> ·{" "}
              <span className={passed > 0 ? "text-passed" : undefined}>{passed} passed</span>
            </p>
          )}
        </div>
        {runs.length === 0 ? (
          <EmptyState icon={History} title="No runs yet" description="Pick a change above and start one; offline runs take a few seconds." />
        ) : (
          <RunsTable runs={runs} changes={changes} />
        )}
      </Reveal>
    </main>
  );
}
