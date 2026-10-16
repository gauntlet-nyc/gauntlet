import { Rocket } from "lucide-react";

import { Reveal } from "@/components/motion/reveal";
import { OnboardingStepper, TargetCard } from "@/components/onboarding";
import { ErrorPanel, PageHeader, Section } from "@/components/shared";
import { api } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  let view;
  try {
    view = await api.onboarding();
  } catch (err) {
    return <ErrorPanel what="Onboarding" error={err} />;
  }
  return (
    <main>
      <PageHeader
        eyebrow="Setup"
        icon={Rocket}
        title="Target onboarding"
        description="Targets come only from committed, synthetic manifests. This page shows what is registered and what an operator still has to configure. It changes nothing."
      />
      <Section
        title="Registered targets"
        description="Synthetic fixtures Gate is allowed to attack, pinned to exact commits and a checksum."
        className="mt-0"
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {view.targets.map((t, i) => (
            <Reveal key={t.fixture_id} index={i} className="flex">
              <TargetCard target={t} />
            </Reveal>
          ))}
        </div>
      </Section>
      <Section title="Operator steps" description="What is already in place, and what still needs an operator before live runs.">
        <Reveal index={2}>
          <OnboardingStepper steps={view.steps} />
        </Reveal>
      </Section>
    </main>
  );
}
