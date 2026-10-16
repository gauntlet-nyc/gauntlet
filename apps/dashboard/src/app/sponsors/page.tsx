import { Activity } from "lucide-react";

import { Reveal } from "@/components/motion/reveal";
import { ErrorPanel, PageHeader } from "@/components/shared";
import { SponsorCard, SponsorSummary } from "@/components/sponsors";
import { api } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function SponsorsPage() {
  let sponsors;
  try {
    sponsors = await api.sponsors();
  } catch (err) {
    return <ErrorPanel what="Sponsor proof" error={err} />;
  }
  return (
    <main>
      <PageHeader
        eyebrow="Providers"
        icon={Activity}
        title="Sponsor proof"
        description={
          <>
            Which provider produces each artifact, and whether it has run live. A sponsor counts as live only after a
            recorded live run in <code className="font-mono text-[13px]">docs/SDK_VALIDATION.md</code>; setting keys alone
            never changes it.
          </>
        }
      />
      <Reveal>
        <SponsorSummary sponsors={sponsors} />
      </Reveal>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {sponsors.map((s, i) => (
          <Reveal key={s.sponsor} index={i + 1} className="flex">
            <SponsorCard sponsor={s} />
          </Reveal>
        ))}
      </div>
    </main>
  );
}
