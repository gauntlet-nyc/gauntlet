import { Activity, FlaskConical, Lock } from "lucide-react";

import { AttackCard } from "@/components/gate/plan-pipeline";
import { EventTimeline } from "@/components/gate/run-sections";
import { ErrorPanel, OfflineBadge, PageHeader, Section } from "@/components/shared";
import { getFakeRun } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function FakeRunPage() {
  let run;
  try {
    run = await getFakeRun();
  } catch (err) {
    return <ErrorPanel what="Fake run" error={err} />;
  }
  return (
    <main>
      <PageHeader
        eyebrow="Diagnostics"
        icon={FlaskConical}
        title="Fake run"
        description={
          <>
            {run.label} · <code className="font-mono text-sm">{run.run_id}</code>
          </>
        }
        actions={<OfflineBadge provenance={[]} />}
      />
      <Section title="Planned attack" icon={Lock}>
        <AttackCard attack={run.plan} />
      </Section>
      <Section title="Events" icon={Activity}>
        <EventTimeline events={run.events} />
      </Section>
    </main>
  );
}
