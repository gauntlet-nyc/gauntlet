import { redirect } from "next/navigation";
import { decide } from "@/app/actions";
import { Banner, Card, DecideForm, ErrorPanel, OfflineBadge, Section, StatusPill } from "@/components/shared";

import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

export default async function ReviewQueuePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const query = await searchParams;
  let items, audit, cf;
  try {
    [items, audit, cf] = await Promise.all([recallApi.reviewQueue(), recallApi.audit(), recallApi.counterfactual()]);
  } catch (err) {
    if (err instanceof ReviewerAuthRequired) redirect("/login?next=/recall/review");
    return <ErrorPanel what="Review queue" error={err} />;
  }
  return (
    <main>
      <h1>Recall review queue</h1>
      <OfflineBadge provenance={[...audit.provenance, ...cf.provenance]} />
      <p>
        Every item is review-only. Approving marks it for human follow-up; nothing is reversed, refunded or sent to a
        customer.
      </p>
      <Banner params={query} />
      <Section title={`${items.length} items`}>
        {items.map((item) => (
          <Card key={item.item_id} tone={item.classification}>
            <StatusPill value={item.classification} /> <strong>{item.title}</strong> · <em>{item.status.replaceAll("_", " ")}</em>
            <p style={{ margin: "4px 0" }}>{item.rationale}</p>
            {item.status === "pending" ? (
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
              <small>Decision {item.approval_id}</small>
            )}
          </Card>
        ))}
      </Section>
    </main>
  );
}
