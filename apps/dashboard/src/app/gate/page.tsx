import { AlertTriangle, CheckCircle2, History, ShieldCheck, XCircle } from "lucide-react";

import { startRun } from "@/app/actions";
import { RunsTable } from "@/components/gate/runs-table";
import { StartRunForm } from "@/components/gate/start-run-form";
import { Reveal } from "@/components/motion/reveal";
import { EmptyState, ErrorPanel, OfflineBadge, PageHeader, Section, StatCard, toneOf } from "@/components/shared";
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
        eyebrow="Gate"
        icon={ShieldCheck}
        title="Test a pull request before it ships"
        description="Gauntlet reads the diff, plans attacks against what changed, runs each one on base and on head, and lets independent oracles decide."
      />
      {runs.some((r) => r.offline) && <OfflineBadge provenance={[]} />}
      {params.error && (
        <div role="alert" className="border-regression/30 bg-regression/[0.07] text-regression my-4 flex items-center gap-2.5 rounded-lg border px-4 py-3 text-sm">
          <AlertTriangle className="size-4 shrink-0" aria-hidden />
          Could not start run (HTTP {params.error}).
        </div>
      )}

      <Section title="Start a run" description="Pick a change. The plan is hashed and frozen before any worker touches it.">
        <Reveal>
          <StartRunForm action={startRun} changes={changes} />
        </Reveal>
      </Section>

      <Section title="Runs" description="Newest first. Each run is immutable once its plan is frozen.">
        {runs.length === 0 ? (
          <EmptyState
            icon={History}
            title="No runs yet"
            description="Runs live in this API process. Pick a change above and start one; it takes a few seconds offline."
          />
        ) : (
          <>
            <div className="mb-4 grid grid-cols-3 gap-3">
              <Reveal index={0}>
                <StatCard label="Runs" value={runs.length} icon={History} />
              </Reveal>
              <Reveal index={1}>
                <StatCard label="Regressions" value={regressions} tone={regressions > 0 ? "bad" : undefined} icon={XCircle} />
              </Reveal>
              <Reveal index={2}>
                <StatCard label="Passed" value={passed} tone={passed > 0 ? "good" : undefined} icon={CheckCircle2} />
              </Reveal>
            </div>
            <Reveal index={3}>
              <RunsTable runs={runs} changes={changes} />
            </Reveal>
          </>
        )}
      </Section>
    </main>
  );
}
