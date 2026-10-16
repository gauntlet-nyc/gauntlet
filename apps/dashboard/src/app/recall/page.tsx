import { ArrowRight, ClipboardCheck, History, Network, ScrollText, ShieldAlert, Waypoints } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Reveal } from "@/components/motion/reveal";
import {
  AuditPanel,
  counterfactualOutcome,
  CountUp,
  DecisionTimeline,
  formatDay,
  formatTime,
  LineageExplorer,
  originalOutcome,
  actionLabel,
  formatAmount,
  TriggerCard,
  type CaseViewModel,
  type TimelineRow,
} from "@/components/recall";
import { ErrorPanel, OfflineBadge, PageHeader, ProvenanceList, Section, StatCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/gauntlet";
import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

export default async function RecallPage() {
  let timeline, audit, cf;
  try {
    [timeline, audit, cf] = await Promise.all([api.timeline(), recallApi.audit(), recallApi.counterfactual()]);
  } catch (err) {
    if (err instanceof ReviewerAuthRequired) redirect("/login?next=/recall");
    return <ErrorPanel what="Recall" error={err} />;
  }

  const byDecision = new Map(timeline.map((d) => [d.decision.decision_id, d]));
  const caseClassOf = new Map(cf.cases.map((c) => [c.decision_id, c.verdict.classification]));
  const auditClassOf = new Map(
    audit.verdicts.filter((v) => v.classification !== "audit_clear").map((v) => [v.decision_id, v.classification]),
  );
  const cases: CaseViewModel[] = cf.cases.map((c) => {
    const original = originalOutcome(byDecision.get(c.decision_id));
    return { c, original, counterfactual: counterfactualOutcome(c, original) };
  });
  const rows: TimelineRow[] = timeline.map((d) => ({
    id: d.decision.decision_id,
    day: formatDay(d.decision.occurred_at),
    time: formatTime(d.decision.occurred_at),
    requester: d.requester,
    action: actionLabel(d.decision.structured_action),
    amount: formatAmount(d.decision.amount_minor),
    sources: d.decision.source_ids,
    exposure: caseClassOf.get(d.decision.decision_id) ?? null,
    audit: auditClassOf.get(d.decision.decision_id) ?? null,
  }));
  const intermediates = [
    ...new Set(cf.cases.flatMap((c) => c.exposure.path.filter((e) => e.target.kind !== "decision").map((e) => e.target.node_id))),
  ];
  const direct = cf.cases.filter((c) => c.exposure.direct).length;
  const count = (k: string) => cf.counts[k] ?? 0;
  const triggerKind = cf.cases[0]?.exposure.trigger_node.kind ?? "document_chunk";
  const provenance = [...audit.provenance, ...cf.provenance];

  return (
    <main>
      <PageHeader
        eyebrow="Recall"
        icon={History}
        title="Refund-tool agent audit"
        description="Find every past agent decision a bad source touched, replay it without that source, and check what the tool actually did against the ledger."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/recall/review">
              <ClipboardCheck aria-hidden />
              Review queue
              <ArrowRight aria-hidden />
            </Link>
          </Button>
        }
      />
      <OfflineBadge provenance={provenance} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Reveal index={0}>
          <TriggerCard
            trigger={cf.trigger_reference}
            kind={triggerKind}
            startAt={audit.summary.start_at}
            endAt={audit.summary.end_at}
            recallIds={[cf.recall_id, audit.recall_id]}
          />
        </Reveal>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Reveal index={1}>
            <StatCard
              label="Decisions exposed"
              value={<CountUp value={cf.cases.length} />}
              hint={`${direct} direct · ${cf.cases.length - direct} second-order`}
              icon={Waypoints}
            />
          </Reveal>
          <Reveal index={2}>
            <StatCard label="Tainted" value={<CountUp value={count("tainted")} />} hint="Outcome changed without the source" tone="bad" />
          </Reveal>
          <Reveal index={3}>
            <StatCard label="Cleared" value={<CountUp value={count("cleared")} />} hint="Same outcome without it" tone="good" />
          </Reveal>
          <Reveal index={4}>
            <StatCard
              label="Not replayable"
              value={<CountUp value={count("not_replayable")} />}
              hint="Inputs missing, never cleared"
              tone="unknown"
            />
          </Reveal>
          <Reveal index={5}>
            <StatCard
              label="Operations audited"
              value={<CountUp value={audit.summary.audited} />}
              hint={`${audit.summary.tool_name} calls in window`}
              icon={ScrollText}
            />
          </Reveal>
          <Reveal index={6}>
            <StatCard
              label="Violations"
              value={<CountUp value={audit.summary.violations} />}
              hint="Ledger credits to a non-owner"
              tone="bad"
              icon={ShieldAlert}
            />
          </Reveal>
        </div>
      </div>

      <Section
        title="Lineage"
        icon={Network}
        description={`How ${cf.trigger_reference} reached each decision: retrieved directly, or second-order through agent memory${intermediates.length ? ` (${intermediates.join(", ")})` : ""}.`}
      >
        <LineageExplorer cases={cases} trigger={cf.trigger_reference} />
        {cf.gaps.map((g) => (
          <p key={g} className="text-inconclusive mt-3 text-xs">
            Gap: {g}
          </p>
        ))}
      </Section>

      <Section
        title="Event audit"
        icon={ScrollText}
        description="Independent of lineage: every refund call is checked against who owns the order in the ledger."
      >
        <AuditPanel audit={audit} />
      </Section>

      <Section title="Decision timeline" icon={History} description="Every recorded decision in the window, with what Recall found.">
        <DecisionTimeline rows={rows} trigger={cf.trigger_reference} highlight={[cf.trigger_reference, ...intermediates]} />
      </Section>

      <Section title="Provenance">
        <ProvenanceList provenance={provenance} />
      </Section>
    </main>
  );
}
