import { Reveal } from "@/components/motion/reveal";
import { ErrorPanel, PageHeader } from "@/components/shared";
import { SponsorList, SponsorSummary } from "@/components/sponsors";
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
        title="Sponsor proof"
        description="A sponsor counts as live only after a recorded live run. Setting keys never changes it."
      />
      <Reveal>
        <SponsorSummary sponsors={sponsors} />
      </Reveal>
      <Reveal index={1} className="mt-6">
        <SponsorList sponsors={sponsors} />
      </Reveal>
    </main>
  );
}
