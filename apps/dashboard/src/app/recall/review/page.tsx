import { ClipboardCheck } from "lucide-react";
import { redirect } from "next/navigation";

import { decide } from "@/app/actions";
import { ReviewRow, type ReviewEvidence } from "@/components/recall/review-row";
import { Banner, EmptyState, ErrorPanel, OfflineBadge, PageHeader } from "@/components/shared";
import type { AuditView, CounterfactualView, ReviewItem } from "@/lib/gauntlet";
import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

const GROUPS = [
  { title: "Remediation drafts", kind: "remediation_proposal" },
  { title: "Counterfactual cases", kind: "counterfactual_case" },
] as const;

function evidenceFor(item: ReviewItem, audit: AuditView, cf: CounterfactualView): ReviewEvidence {
  const verdicts = [...audit.verdicts, ...cf.cases.map((c) => c.verdict)];
  const proposal = [...audit.proposals, ...cf.proposals].find((p) => p.proposal_id === item.item_id);
  if (proposal) {
    const linked = verdicts.filter((v) => proposal.verdict_ids.includes(v.verdict_id));
    return {
      decisions: [...new Set(linked.flatMap((v) => (v.decision_id ? [v.decision_id] : [])))],
      evidenceIds: [...new Set([...proposal.evidence_ids, ...linked.flatMap((v) => v.evidence_ids ?? [])])],
      replays: null,
      missing: [],
    };
  }
  const c = cf.cases.find((x) => x.verdict.verdict_id === item.item_id);
  if (c) {
    return {
      decisions: [c.decision_id],
      evidenceIds: c.verdict.evidence_ids ?? [],
      replays: (c.verdict.replay_ids ?? []).length,
      missing: c.missing_fields,
    };
  }
  return { decisions: [], evidenceIds: [], replays: null, missing: [] };
}

export default async function ReviewQueuePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const query = await searchParams;
  let items, audit, cf;
  try {
    [items, audit, cf] = await Promise.all([recallApi.reviewQueue(), recallApi.audit(), recallApi.counterfactual()]);
  } catch (err) {
    if (err instanceof ReviewerAuthRequired) redirect("/login?next=/recall/review");
    return <ErrorPanel what="Review queue" error={err} />;
  }
  const pending = items.filter((i) => i.status === "pending").length;
  const known = new Set<string>(GROUPS.map((g) => g.kind));
  const groups = [
    ...GROUPS.map((g) => ({ title: g.title, items: items.filter((i) => i.kind === g.kind) })),
    { title: "Other", items: items.filter((i) => !known.has(i.kind)) },
  ].filter((g) => g.items.length > 0);

  return (
    <main>
      <PageHeader
        eyebrow="Recall"
        icon={ClipboardCheck}
        title="Review queue"
        description="Drafts only, nothing auto-applied. Approving marks an item for human follow-up; nothing is reversed, refunded or sent."
        actions={
          <>
            <OfflineBadge provenance={[...audit.provenance, ...cf.provenance]} />
            <span className="text-muted-foreground text-sm tabular-nums">
              <span className="text-foreground font-medium">{pending}</span> pending
            </span>
          </>
        }
      />
      <Banner params={query} />

      {items.length === 0 ? (
        <EmptyState title="Queue is empty" description="Recall produced no drafts for review." />
      ) : (
        <div className="space-y-8">
          {groups.map((g) => (
            <section key={g.title}>
              <h2 className="text-muted-foreground mb-2 text-xs font-medium">
                {g.title} <span className="tabular-nums">· {g.items.length}</span>
              </h2>
              <ul className="divide-y rounded-xl border">
                {g.items.map((item) => (
                  <ReviewRow key={item.item_id} item={item} evidence={evidenceFor(item, audit, cf)} action={decide} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
