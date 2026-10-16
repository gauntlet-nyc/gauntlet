import { ArrowRight, History } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  actionLabel,
  counterfactualOutcome,
  formatAmount,
  formatDay,
  formatTime,
  LineageExplorer,
  originalOutcome,
  RecallSummary,
  type CaseViewModel,
  type TimelineRow,
} from "@/components/recall";
import { ErrorPanel, OfflineBadge, PageHeader } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/gauntlet";
import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

const TRIGGER_KIND_LABELS: Record<string, string> = { document_chunk: "KB chunk", memory: "memory" };

function windowLabel(startAt: string, endAt: string): string {
  const start = formatDay(startAt);
  const end = formatDay(endAt);
  const [startMonth] = start.split(" ");
  return end.startsWith(`${startMonth} `) ? `${start}–${end.split(" ")[1]}` : `${start} – ${end}`;
}

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
  const count = (k: string) => cf.counts[k] ?? 0;
  const triggerKind = cf.cases[0]?.exposure.trigger_node.kind ?? "document_chunk";

  return (
    <main>
      <PageHeader
        eyebrow="Recall"
        icon={History}
        title="Refund-tool agent audit"
        description={
          <>
            Trigger: <span className="text-foreground font-mono text-sm">{cf.trigger_reference}</span>,{" "}
            {TRIGGER_KIND_LABELS[triggerKind] ?? triggerKind} · {windowLabel(audit.summary.start_at, audit.summary.end_at)}.
            Each exposed decision is replayed without it.
          </>
        }
        actions={
          <>
            <OfflineBadge provenance={[...audit.provenance, ...cf.provenance]} />
            <Button asChild variant="outline" size="sm">
              <Link href="/recall/review">
                Review queue
                <ArrowRight aria-hidden />
              </Link>
            </Button>
          </>
        }
      />

      <RecallSummary
        exposed={cf.cases.length}
        direct={cf.cases.filter((c) => c.exposure.direct).length}
        tainted={count("tainted")}
        cleared={count("cleared")}
        notReplayable={count("not_replayable")}
        audited={audit.summary.audited}
        violations={audit.summary.violations}
      />

      <div className="mt-8">
        <LineageExplorer
          cases={cases}
          trigger={cf.trigger_reference}
          audit={audit}
          rows={rows}
          highlight={[cf.trigger_reference, ...intermediates]}
        />
        {cf.gaps.map((g) => (
          <p key={g} className="text-inconclusive mt-3 text-xs">
            Gap: {g}
          </p>
        ))}
      </div>
    </main>
  );
}
