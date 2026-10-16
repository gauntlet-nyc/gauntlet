import { CircleDashed, GitPullRequest } from "lucide-react";
import type { ReactNode } from "react";

import { MonoId } from "@/components/gate/mono-id";
import { Card, EmptyState, ErrorPanel, PageHeader, Section, StatusPill } from "@/components/shared";
import { getCartwheelChange } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CartwheelGatePage() {
  let change;
  try {
    change = await getCartwheelChange();
  } catch (err) {
    return <ErrorPanel what="Cartwheel change request" error={err} />;
  }
  const facts: { label: string; value: ReactNode }[] = [
    { label: "Repository", value: <code className="font-mono">{change.repository_id}</code> },
    { label: "Base SHA", value: <MonoId value={change.base_sha} chars={12} /> },
    { label: "Head SHA", value: <MonoId value={change.head_sha} chars={12} /> },
    { label: "Fixture", value: <code className="font-mono">{change.fixture_id}</code> },
    { label: "Cost cap", value: <span className="tabular-nums">${(change.max_cost_usd_cents / 100).toFixed(2)}</span> },
  ];
  return (
    <main>
      <PageHeader
        eyebrow="Diagnostics"
        icon={GitPullRequest}
        title={`Gate run: ${change.target_id}`}
        description={change.feature_intent ?? "Change request with no stated intent."}
      />
      <Card>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-5">
          {facts.map((f) => (
            <div key={f.label} className="min-w-0">
              <dt className="text-muted-foreground text-xs">{f.label}</dt>
              <dd className="mt-1 truncate text-sm">{f.value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Section title="Findings">
        <EmptyState icon={CircleDashed} title="Not tested" description="No worker has executed this change yet, so there are no observations, screenshots or traces to show.">
          <StatusPill value="not_tested" />
        </EmptyState>
      </Section>
    </main>
  );
}
