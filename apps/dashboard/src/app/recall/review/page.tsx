import { ArrowLeft, ClipboardCheck, FileLock2 } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { decide } from "@/app/actions";
import { Reveal } from "@/components/motion/reveal";
import { ReviewItemCard, type ReviewEvidence } from "@/components/recall/review-item-card";
import { Banner, DecideForm, EmptyState, ErrorPanel, OfflineBadge, PageHeader, Section } from "@/components/shared";
import { Button } from "@/components/ui/button";
import type { AuditView, CounterfactualView, ReviewItem } from "@/lib/gauntlet";
import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

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
  const groups = [
    { title: "Remediation drafts", description: "Grouped follow-ups proposed from confirmed findings.", kind: "remediation_proposal" },
    { title: "Counterfactual cases", description: "Individual decisions that need a human look.", kind: "counterfactual_case" },
  ];
  const other = items.filter((i) => !groups.some((g) => g.kind === i.kind));
  if (other.length) groups.push({ title: "Other", description: "", kind: "" });

  return (
    <main>
      <PageHeader
        eyebrow="Recall"
        icon={ClipboardCheck}
        title="Review queue"
        description="Drafts produced by the Recall audit. A person approves or rejects each one; approving only marks it for human follow-up."
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link href="/recall">
              <ArrowLeft aria-hidden />
              Back to Recall
            </Link>
          </Button>
        }
      />
      <OfflineBadge provenance={[...audit.provenance, ...cf.provenance]} />
      <Banner params={query} />

      <div className="bg-card flex flex-col gap-4 rounded-xl border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <FileLock2 className="text-muted-foreground mt-0.5 size-5 shrink-0" aria-hidden />
          <div>
            <p className="text-sm font-medium">Drafts only, nothing auto-applied</p>
            <p className="text-muted-foreground mt-0.5 text-sm">
              Every item is review-only. Nothing is reversed, refunded or sent to a customer from this page.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-6 text-sm sm:border-l sm:pl-6">
          <div>
            <div className="text-2xl font-semibold tabular-nums">{pending}</div>
            <div className="text-muted-foreground text-xs">pending</div>
          </div>
          <div>
            <div className="text-2xl font-semibold tabular-nums">{items.length - pending}</div>
            <div className="text-muted-foreground text-xs">decided</div>
          </div>
        </div>
      </div>

      {items.length === 0 && (
        <div className="mt-10">
          <EmptyState title="Queue is empty" description="Recall produced no drafts for review." />
        </div>
      )}

      {groups.map((g) => {
        const groupItems = g.kind ? items.filter((i) => i.kind === g.kind) : other;
        if (!groupItems.length) return null;
        return (
          <Section key={g.title} title={`${g.title} (${groupItems.length})`} description={g.description || undefined}>
            <div className="space-y-4">
              {groupItems.map((item, i) => (
                <Reveal key={item.item_id} index={i}>
                  <ReviewItemCard
                    item={item}
                    evidence={evidenceFor(item, audit, cf)}
                    form={
                      item.status === "pending" ? (
                        <DecideForm
                          action={decide}
                          runId={item.recall_id}
                          subject="remediation"
                          subjectId={item.item_id}
                          planSha256={item.plan_sha256}
                          back="/recall/review"
                          approveLabel="Approve for review"
                        />
                      ) : (
                        <p className="text-muted-foreground text-xs">
                          Decision <code className="font-mono">{item.approval_id}</code>
                        </p>
                      )
                    }
                  />
                </Reveal>
              ))}
            </div>
          </Section>
        );
      })}
    </main>
  );
}
