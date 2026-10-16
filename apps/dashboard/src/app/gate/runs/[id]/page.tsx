import type { ReactNode } from "react";

import { decide, runRepair } from "@/app/actions";
import { DiffFiles } from "@/components/gate/diff-files";
import { CheckRunCard } from "@/components/gate/check-run-card";
import { tallyRun, verdictCopy } from "@/components/gate/copy";
import { EvidenceGallery, type EvidenceItem } from "@/components/gate/evidence-gallery";
import { FixPlanReview } from "@/components/gate/fix-plan-review";
import { MonoId } from "@/components/gate/mono-id";
import { AttackCard } from "@/components/gate/plan-pipeline";
import { RevisionCounters } from "@/components/gate/revision-compare";
import { AttemptsTable, EventTimeline, OracleRecords } from "@/components/gate/run-sections";
import { VerdictHero } from "@/components/gate/verdict-hero";
import { Reveal } from "@/components/motion/reveal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VoiceBriefingButton } from "@/components/VoiceBriefing";
import { Banner, EmptyState, ErrorPanel, OfflineBadge, PageHeader, ProvenanceList, StatusPill, toneOf } from "@/components/shared";
import { api, artifactUrl } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

function SubHeading({ children }: { children: ReactNode }) {
  return <h3 className="text-muted-foreground mb-3 text-xs font-medium tracking-wide uppercase">{children}</h3>;
}

function diffStats(diff: string): { added: number; removed: number } {
  const lines = diff.split("\n");
  return {
    added: lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length,
    removed: lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length,
  };
}

export default async function GateRunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  let run, briefing, check;
  try {
    [run, briefing, check] = await Promise.all([api.run(id), api.briefing(id), api.checkRun(id)]);
  } catch (err) {
    return <ErrorPanel what="Gate run" error={err} />;
  }
  const back = `/gate/runs/${encodeURIComponent(run.run_id)}`;
  const tally = tallyRun(run.attempts);
  const copy = verdictCopy(run, tally);
  const viewportOf = new Map(
    run.attacks.flatMap((attack) =>
      attack.steps.flatMap((s) => (s.action === "resize" ? [[attack.attack_id, `${s.width}×${s.height}`] as const] : [])),
    ),
  );
  const evidence: EvidenceItem[] = run.attempts
    .filter((a) => a.screenshot_artifact_ids.length > 0)
    .map((a) => ({
      key: `${a.attack_id}-${a.revision}-${a.attempt}`,
      attackId: a.attack_id,
      revision: a.revision,
      attempt: a.attempt,
      outcome: a.outcome,
      observed: a.observed,
      viewport: viewportOf.get(a.attack_id) ?? null,
      shots: a.screenshot_artifact_ids.map((artifactId) => ({ artifactId, src: artifactUrl(run.run_id, artifactId) })),
    }));
  const provenance = [...run.provenance, ...(run.repair?.provenance ?? [])];

  return (
    <main>
      <PageHeader
        title={run.feature_intent}
        description={
          <span className="text-sm">
            <span className="font-mono">{run.run_id}</span>
            <span className="text-muted-foreground/50 mx-2">·</span>
            <span className="font-mono">
              <MonoId value={run.base_sha} ellipsis={false} />
              <span className="text-muted-foreground/60 px-0.5 font-sans">..</span>
              <MonoId value={run.head_sha} ellipsis={false} />
            </span>
          </span>
        }
        actions={
          <>
            <OfflineBadge provenance={run.provenance} />
            <VoiceBriefingButton text={briefing.briefing.spoken_summary} providerLabel={briefing.provenance.label} />
          </>
        }
      />
      <Banner params={query} />

      <VerdictHero
        tone={toneOf(run.status)}
        headline={copy.headline}
        explanation={copy.explanation}
        verdictLine={
          <>
            <span className="text-muted-foreground">Verdict:</span>
            <StatusPill value={run.status} />
            {run.attribution === "introduced" && <span>— regression introduced by this PR</span>}
            {run.attribution === "pre_existing" && <span>— pre-existing on base</span>}
          </>
        }
        aside={run.attempts.length > 0 ? <RevisionCounters tally={tally} /> : undefined}
      />

      {run.attempts.length > 0 && (
        <Reveal index={1} className="mt-10">
          <SubHeading>Evidence</SubHeading>
          {evidence.length > 0 ? <EvidenceGallery items={evidence} /> : <OracleRecords attempts={run.attempts} />}
        </Reveal>
      )}

      {run.fix_plan && (
        <Reveal index={2} className="mt-10">
          <FixPlanReview
            runId={run.run_id}
            fixPlan={run.fix_plan}
            repair={run.repair}
            back={back}
            repairStatus={query.repair}
            decide={decide}
            runRepair={runRepair}
          />
        </Reveal>
      )}

      <Tabs defaultValue="changes" className="mt-12 gap-6">
        <TabsList variant="line" className="w-full justify-start border-b">
          <TabsTrigger value="changes" className="flex-none">
            Changes
            <span className="text-muted-foreground text-xs tabular-nums">{run.diff.length}</span>
          </TabsTrigger>
          <TabsTrigger value="plan" className="flex-none">
            Plan
            <span className="text-muted-foreground text-xs tabular-nums">{run.attacks.length}</span>
          </TabsTrigger>
          <TabsTrigger value="activity" className="flex-none">
            Activity
          </TabsTrigger>
        </TabsList>

        <TabsContent value="changes" className="space-y-3">
          <DiffFiles files={run.diff.map((d) => ({ path: d.path, diff: d.unified_diff, ...diffStats(d.unified_diff) }))} />
        </TabsContent>

        <TabsContent value="plan" className="space-y-4">
          <p className="text-muted-foreground text-sm">
            Frozen before any worker ran
            {run.plan_sha256 && (
              <>
                {" "}
                · hash <MonoId value={run.plan_sha256} chars={12} />
              </>
            )}{" "}
            · planner <span className="text-foreground">{run.model_id ?? "none"}</span> · target <span className="text-foreground">{run.target_id}</span>
          </p>
          {run.attacks.length > 0 ? (
            run.attacks.map((attack) => <AttackCard key={attack.attack_id} attack={attack} />)
          ) : (
            <EmptyState title="No attack was accepted for this change" description="Not tested does not mean safe." />
          )}
          {run.rejected_attacks.length > 0 && (
            <div>
              <SubHeading>Rejected by the validator</SubHeading>
              <ul className="space-y-1 font-mono text-xs">
                {run.rejected_attacks.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </TabsContent>

        <TabsContent value="activity" className="space-y-10">
          {run.attempts.length > 0 && (
            <div>
              <SubHeading>Attempts</SubHeading>
              <AttemptsTable attempts={run.attempts} />
            </div>
          )}
          <div>
            <SubHeading>GitHub check run (preview)</SubHeading>
            <CheckRunCard check={check} />
          </div>
          <div>
            <SubHeading>Events</SubHeading>
            <EventTimeline events={run.events} />
          </div>
          <div>
            <SubHeading>Provenance</SubHeading>
            <ProvenanceList provenance={provenance} />
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
