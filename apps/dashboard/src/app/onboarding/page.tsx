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
  const done = view.steps.filter((s) => s.done).length;
  return (
    <main>
      <PageHeader
        title="Target onboarding"
        description="Targets come only from committed, synthetic manifests. This page changes nothing."
      />
      <div className="grid gap-x-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Section title="Registered targets" className="mt-0">
          <div className="space-y-3">
            {view.targets.map((t, i) => (
              <Reveal key={t.fixture_id} index={i}>
                <TargetCard target={t} />
              </Reveal>
            ))}
          </div>
        </Section>
        <Section
          title="Operator steps"
          className="mt-10 lg:mt-0"
          actions={
            <span className="text-muted-foreground text-xs tabular-nums">
              {done} of {view.steps.length} done
            </span>
          }
        >
          <Reveal index={2}>
            <OnboardingStepper steps={view.steps} />
          </Reveal>
        </Section>
      </div>
    </main>
  );
}
