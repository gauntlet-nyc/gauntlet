import { Activity, FlaskConical } from "lucide-react";

import { humanize } from "@/components/gate/copy";
import { EventTimeline } from "@/components/gate/run-sections";
import { Reveal } from "@/components/motion/reveal";
import { Card, ErrorPanel, OfflineBadge, PageHeader, Section, StatusPill, TONE_CLASSES, toneOf } from "@/components/shared";
import { getOfflineGate } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const ATTEMPT_LABELS = ["Head attempt 1", "Head attempt 2", "Base attempt"];

export default async function OfflineGatePage() {
  let gate;
  try {
    gate = await getOfflineGate();
  } catch (err) {
    return <ErrorPanel what="Offline gate" error={err} />;
  }
  return (
    <main>
      <PageHeader
        eyebrow="Diagnostics"
        icon={FlaskConical}
        title="Offline gate (P0)"
        description="The first end-to-end gate: replayed golden observations judged by the real oracle path. No browser or sandbox runs here."
        actions={
          <OfflineBadge
            provenance={gate.execution_mode === "offline_recording"
              ? [{ provider: "golden-recording", mode: "offline_recording", live: false, label: "Recorded golden observations" }]
              : []}
          />
        }
      />
      <Reveal>
        <Card tone={gate.status}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">Verdict:</span>
            <StatusPill value={gate.status} size="lg" />
            <span className="text-muted-foreground">attribution</span>
            <span className="font-medium">{humanize(gate.attribution)}</span>
            <span className="text-muted-foreground ml-auto font-mono text-xs">{gate.execution_mode}</span>
          </div>
          <p className="text-muted-foreground mt-3 text-sm">{gate.label}</p>
        </Card>
      </Reveal>

      <Section title="Oracle outcomes" description="One oracle decision per recorded attempt.">
        <div className="grid gap-3 sm:grid-cols-3">
          {gate.oracle_outcomes.map((o, i) => {
            const tone = TONE_CLASSES[toneOf(o)];
            return (
              <Reveal key={i} index={i}>
                <div className={cn("bg-card flex items-center justify-between rounded-xl border px-5 py-4", tone.border)}>
                  <span className="text-sm">{ATTEMPT_LABELS[i] ?? `Attempt ${i + 1}`}</span>
                  <StatusPill value={o} />
                </div>
              </Reveal>
            );
          })}
        </div>
      </Section>

      <Section title="Events" icon={Activity}>
        <EventTimeline events={gate.events} />
      </Section>
    </main>
  );
}
