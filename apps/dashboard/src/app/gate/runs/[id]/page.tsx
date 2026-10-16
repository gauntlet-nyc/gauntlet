import {
  Activity,
  Bot,
  FileCode2,
  Fingerprint,
  Flag,
  Images,
  Layers,
  Lock,
  PlayCircle,
  ShieldCheck,
  Target,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";

import { decide, runRepair } from "@/app/actions";
import { CheckRunCard } from "@/components/gate/check-run-card";
import { tallyRun, verdictCopy } from "@/components/gate/copy";
import { EvidenceGallery, type EvidenceItem } from "@/components/gate/evidence-gallery";
import { FixPlanReview } from "@/components/gate/fix-plan-review";
import { MonoId } from "@/components/gate/mono-id";
import { AttackCard } from "@/components/gate/plan-pipeline";
import { RevisionCompare } from "@/components/gate/revision-compare";
import { AttemptsTable, EventTimeline, FindingCard } from "@/components/gate/run-sections";
import { SectionNav, type NavSection } from "@/components/gate/section-nav";
import { VerdictHero } from "@/components/gate/verdict-hero";
import { Reveal } from "@/components/motion/reveal";
import { VoiceBriefingButton } from "@/components/VoiceBriefing";
import { Banner, DiffView, EmptyState, ErrorPanel, OfflineBadge, PageHeader, ProvenanceList, Section, StatusPill, toneOf } from "@/components/shared";
import { api, artifactUrl } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

/** In-page anchor target, offset for the sticky topbar plus section nav. */
function Anchor({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div id={id} className="scroll-mt-24">
      {children}
    </div>
  );
}

function Fact({ label, icon: Icon, children }: { label: string; icon: typeof Target; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Icon className="size-3" aria-hidden />
        {label}
      </dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
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
  const totals = run.diff.map((d) => diffStats(d.unified_diff)).reduce((acc, s) => ({ added: acc.added + s.added, removed: acc.removed + s.removed }), { added: 0, removed: 0 });

  const sections: NavSection[] = [
    { id: "evidence", label: "Evidence" },
    { id: "diff", label: "Diff" },
    { id: "plan", label: "Frozen plan" },
    { id: "attempts", label: "Attempts" },
    { id: "findings", label: "Findings" },
    ...(run.fix_plan ? [{ id: "fix", label: "Fix plan" }] : []),
    { id: "check", label: "Check run" },
    { id: "events", label: "Events" },
    { id: "provenance", label: "Provenance" },
  ];

  return (
    <main>
      <PageHeader
        eyebrow="Gate run"
        icon={ShieldCheck}
        title={run.feature_intent}
        description={
          <span className="font-mono text-sm">
            {run.run_id} <span className="text-muted-foreground/50">·</span> {run.change_id}
          </span>
        }
      />
      <OfflineBadge provenance={run.provenance} />
      <Banner params={query} />

      <VerdictHero
        tone={toneOf(run.status)}
        headline={copy.headline}
        explanation={copy.explanation}
        verdictLine={
          <>
            <span className="text-muted-foreground">Verdict:</span>
            <StatusPill value={run.status} size="lg" />
            {run.attribution === "introduced" && <span className="font-medium">— regression introduced by this PR</span>}
            {run.attribution === "pre_existing" && <span className="font-medium">— pre-existing on base</span>}
          </>
        }
        facts={
          <dl className="flex flex-wrap gap-x-10 gap-y-4">
            <Fact label="Target" icon={Target}>
              <code className="font-mono text-[13px]">{run.target_id}</code>
            </Fact>
            <Fact label="Base..head" icon={Layers}>
              <span className="font-mono text-[13px]">
                <MonoId value={run.base_sha} ellipsis={false} />
                <span className="text-muted-foreground/60">..</span>
                <MonoId value={run.head_sha} ellipsis={false} />
              </span>
            </Fact>
            <Fact label="Plan hash" icon={Fingerprint}>
              {run.plan_sha256 ? <MonoId value={run.plan_sha256} chars={12} className="text-[13px]" /> : <span className="text-muted-foreground">none</span>}
            </Fact>
            <Fact label="Planner" icon={Bot}>
              <code className="font-mono text-[13px]">{run.model_id ?? "none"}</code>
            </Fact>
          </dl>
        }
        aside={<VoiceBriefingButton text={briefing.briefing.spoken_summary} providerLabel={briefing.provenance.label} />}
      />
      {run.not_tested_reason && run.status !== "inconclusive" && <p className="text-muted-foreground mt-3 text-sm">{run.not_tested_reason}</p>}

      <Section title="Head vs base" icon={Activity} description="Every attack runs twice on each revision, in isolated environments. Hover a tile for what the oracle saw.">
        {run.attempts.length === 0 ? (
          <EmptyState title="No attempts executed" description="Not tested does not mean safe." />
        ) : (
          <Reveal>
            <RevisionCompare attempts={run.attempts} tally={tally} headSha={run.head_sha} baseSha={run.base_sha} />
          </Reveal>
        )}
      </Section>

      <SectionNav sections={sections} />

      <Anchor id="evidence">
        <Section
          title="Evidence"
          icon={Images}
         
          description="Frames captured by the worker. Bytes are served only by exact run and artifact ID from the write-once store."
        >
          {evidence.length > 0 ? (
            <EvidenceGallery items={evidence} />
          ) : (
            <EmptyState icon={Images} title="No screenshots for this run" description="This attack type records ledger and trace evidence instead of frames; see Attempts." />
          )}
        </Section>
      </Anchor>

      <Anchor id="diff">
        <Section
          title="Diff"
          icon={FileCode2}
         
          description={
            <>
              {run.diff.length} {run.diff.length === 1 ? "file" : "files"} changed · <span className="text-passed">+{totals.added}</span>{" "}
              <span className="text-regression">−{totals.removed}</span>
            </>
          }
        >
          <div className="space-y-3">
            {run.diff.map((d) => (
              <DiffView key={d.path} path={d.path} diff={d.unified_diff} className="[&>pre]:max-h-80 [&>pre]:overflow-y-auto" />
            ))}
          </div>
        </Section>
      </Anchor>

      <Anchor id="plan">
        <Section
          title="Frozen plan"
          icon={Lock}
         
          description={
            run.plan_sha256 ? (
              <>
                Hashed and frozen before any worker ran · <MonoId value={run.plan_sha256} chars={16} /> · planner <code className="font-mono">{run.model_id}</code>
              </>
            ) : undefined
          }
        >
          {run.attacks.length > 0 ? (
            <div className="space-y-3">
              {run.attacks.map((attack, i) => (
                <Reveal key={attack.attack_id} index={i}>
                  <AttackCard attack={attack} />
                </Reveal>
              ))}
            </div>
          ) : (
            <EmptyState title="No attack was accepted for this change" description="Not tested does not mean safe." />
          )}
          {run.rejected_attacks.length > 0 && (
            <div className="bg-card mt-3 rounded-xl border p-4">
              <p className="text-muted-foreground text-xs font-medium">Rejected by the validator</p>
              <ul className="mt-2 space-y-1 text-sm">
                {run.rejected_attacks.map((r) => (
                  <li key={r} className="font-mono text-xs">
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      </Anchor>

      <Anchor id="attempts">
        <Section title="Attempts" icon={PlayCircle} description="What each independent oracle observed, per revision and attempt.">
          {run.attempts.length === 0 ? <EmptyState title="No attempts executed" /> : <AttemptsTable attempts={run.attempts} />}
        </Section>
      </Anchor>

      <Anchor id="findings">
        <Section title="Findings" icon={Flag}>
          {run.findings.length === 0 ? (
            <EmptyState icon={Flag} title="No findings" description="Not tested does not mean safe." />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {run.findings.map((f) => (
                <FindingCard key={f.finding_id} finding={f} />
              ))}
            </div>
          )}
        </Section>
      </Anchor>

      {run.fix_plan && (
        <Anchor id="fix">
          <Section
            title="Fix plan review"
            icon={Wrench}
           
            description="A proposed patch. Nothing is applied until a human approves this exact plan hash."
          >
            <FixPlanReview
              runId={run.run_id}
              fixPlan={run.fix_plan}
              repair={run.repair}
              back={back}
              repairStatus={query.repair}
              decide={decide}
              runRepair={runRepair}
            />
          </Section>
        </Anchor>
      )}

      <Anchor id="check">
        <Section title="GitHub check run" icon={ShieldCheck} description="What reviewers would see on the pull request.">
          <CheckRunCard check={check} />
        </Section>
      </Anchor>

      <Anchor id="events">
        <Section title="Events" icon={Activity} description="Append-only run log, in sequence order.">
          <EventTimeline events={run.events} />
        </Section>
      </Anchor>

      <Anchor id="provenance">
        <Section title="Provenance" icon={Fingerprint} description="Which provider produced each part of this run, and whether it ran live.">
          <ProvenanceList provenance={run.provenance} />
        </Section>
      </Anchor>
    </main>
  );
}
