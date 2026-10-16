import { ArrowRight, History } from "lucide-react";
import Link from "next/link";

import { Reveal } from "@/components/motion/reveal";
import { GateCard, PipelineDiagram, RecallCard, SafetyStrip, SponsorRow } from "@/components/overview";
import { Section } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { api, type AuditView, type GateRunSummary } from "@/lib/gauntlet";
import { recallApi } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

/** Live numbers are a nice-to-have: any API failure renders the cards without them. */
async function loadNumbers(): Promise<{ runs: GateRunSummary[] | null; audit: AuditView | null }> {
  const [runs, audit] = await Promise.allSettled([api.runs(), recallApi.audit()]);
  return {
    runs: runs.status === "fulfilled" ? runs.value : null,
    audit: audit.status === "fulfilled" ? audit.value : null,
  };
}

export default async function Overview() {
  const { runs, audit } = await loadNumbers();
  return (
    <main>
      <section className="pt-4 pb-10 md:pt-8 md:pb-12">
        <Reveal>
          <div className="text-muted-foreground inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs">
            <span className="bg-foreground/60 size-1.5 rounded-full" aria-hidden />
            Change-aware adversarial release testing
          </div>
        </Reveal>
        <Reveal index={1}>
          <h1 className="mt-6 max-w-4xl text-[34px] leading-[1.08] font-semibold tracking-[-0.035em] text-balance sm:text-5xl md:text-[56px]">
            CI passes because nobody wrote the test.{" "}
            <span className="text-muted-foreground">Gauntlet reads the change and writes it.</span>
          </h1>
        </Reveal>
        <Reveal index={2}>
          <p className="text-muted-foreground mt-5 max-w-2xl text-base leading-relaxed md:text-lg">
            It plans attacks against each pull request, runs them on base and head, and shows you what the change broke.
          </p>
        </Reveal>
        <Reveal index={3}>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button asChild size="lg">
              <Link href="/gate">
                Start a Gate run
                <ArrowRight aria-hidden />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/recall">
                <History aria-hidden />
                Open Recall
              </Link>
            </Button>
          </div>
        </Reveal>
      </section>

      <Reveal index={4}>
        <figure className="bg-card/50 overflow-hidden rounded-xl border">
          <figcaption className="flex items-center justify-between gap-4 border-b px-5 py-3">
            <span className="text-sm font-medium">How a Gate run decides</span>
            <span className="text-muted-foreground hidden font-mono text-xs sm:inline">
              plan frozen before anything executes
            </span>
          </figcaption>
          <div className="px-5 py-6 md:px-8">
            <PipelineDiagram />
          </div>
        </figure>
      </Reveal>

      <Section title="Two products" className="mt-12">
        <div className="grid gap-4 md:grid-cols-2">
          <Reveal index={5} className="flex">
            <GateCard runs={runs} />
          </Reveal>
          <Reveal index={6} className="flex">
            <RecallCard audit={audit} />
          </Reveal>
        </div>
      </Section>

      <Section title="How it stays safe" className="mt-12">
        <SafetyStrip />
      </Section>

      <div className="mt-12">
        <SponsorRow />
      </div>
    </main>
  );
}
