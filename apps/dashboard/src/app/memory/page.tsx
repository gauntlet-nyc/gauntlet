import { Brain, GitCompareArrows, Library, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { FactChip, MemoryFlow, type FlowStep, type MemoryFact } from "@/components/memory";
import { Reveal } from "@/components/motion/reveal";
import { EmptyState, ErrorPanel, OfflineBadge, PageHeader, ProvenanceList, Section, StatusPill } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, shortSha, type MemoryView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type MemoryRun = MemoryView["runs"][number];

const PRINCIPLES = [
  { title: "Proved, then remembered", body: "A fact is written only from a confirmed finding and cites the finding and oracle that proved it." },
  { title: "Evidence, not a verdict", body: "Later plans receive facts known at planning time as untrusted evidence. They widen the attack set; oracles still decide." },
  { title: "Append-only", body: "Corrections supersede older facts. Nothing is overwritten, so every plan can be audited as of its time." },
] as const;

/** Attacks a run planned that the previous run of the same change did not. */
function newAttacks(run: MemoryRun, runs: readonly MemoryRun[]): Set<string> {
  const idx = runs.indexOf(run);
  const prev = runs.slice(0, idx).reverse().find((r) => r.change_id === run.change_id);
  if (!prev) return new Set();
  return new Set(run.attack_ids.filter((a) => !prev.attack_ids.includes(a)));
}

function flowFor(runs: readonly MemoryRun[], facts: ReadonlyMap<string, MemoryFact>): { steps: FlowStep[]; links: string[] } | null {
  const reader = runs.find((r) => r.memory_fact_ids_used.length > 0);
  const factId = reader?.memory_fact_ids_used[0];
  if (!reader || !factId) return null;
  const writer = runs.find((r) => r.memory_facts_written.includes(factId));
  const fact = facts.get(factId);
  const added = newAttacks(reader, runs).size;
  const steps: FlowStep[] = [];
  if (writer) {
    steps.push({
      icon: "run",
      eyebrow: "Run without memory",
      title: writer.run_id,
      detail: `${writer.attack_ids.length} attack${writer.attack_ids.length === 1 ? "" : "s"} planned`,
      status: writer.status,
    });
  }
  steps.push(
    {
      icon: "fact",
      eyebrow: "Verified fact",
      title: factId.length > 28 ? `fact-…${factId.slice(-12)}` : factId,
      detail: fact ? `${fact.kind.replaceAll("_", " ")} · ${fact.verification} / ${fact.trust}` : "fact",
      emphasis: true,
    },
    {
      icon: "plan",
      eyebrow: "Run with memory",
      title: reader.run_id,
      detail: `${reader.attack_ids.length} attacks planned${added ? ` (+${added} from memory)` : ""}`,
    },
    {
      icon: "oracle",
      eyebrow: "Oracle decides",
      title: "Verdict",
      detail: "Decided by the oracle, independent of memory",
      status: reader.status,
    },
  );
  const links = writer ? ["writes", "informs plan", "verdict"] : ["informs plan", "verdict"];
  return { steps, links };
}

export default async function MemoryPage() {
  let view;
  try {
    view = await api.memory();
  } catch (err) {
    return <ErrorPanel what="Memory" error={err} />;
  }
  const facts = new Map(view.facts.map((f) => [f.fact_id, f]));
  const superseded = new Set(view.facts.map((f) => f.supersedes).filter(Boolean));
  const flow = flowFor(view.runs, facts);

  return (
    <main>
      <PageHeader
        eyebrow="Memory"
        icon={Brain}
        title="Planning memory"
        description="Confirmed findings become typed, cited facts that later attack plans can use. Memory is evidence for planning, never the oracle."
      />
      <OfflineBadge provenance={[view.provenance]} />

      <div className="grid gap-4 md:grid-cols-3">
        {PRINCIPLES.map((p, i) => (
          <Reveal key={p.title} index={i}>
            <div className="bg-card h-full rounded-xl border p-5">
              <div className="text-muted-foreground mb-2 font-mono text-xs tabular-nums">0{i + 1}</div>
              <p className="text-sm font-medium">{p.title}</p>
              <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{p.body}</p>
            </div>
          </Reveal>
        ))}
      </div>

      {flow && (
        <Section title="How a fact reaches the next plan" icon={GitCompareArrows}>
          <MemoryFlow steps={flow.steps} links={flow.links} />
        </Section>
      )}

      <Section
        title="Planning with vs without memory"
        icon={ShieldCheck}
        description="Each run, the facts its planner received, and the facts it wrote back. Hover a fact for its provenance."
      >
        {view.runs.length === 0 ? (
          <EmptyState
            title="No runs yet"
            description="Start the same change twice on the Gate page. The second plan will receive the fact the first run proved."
            icon={GitCompareArrows}
          >
            <Button asChild size="sm">
              <Link href="/gate">Open Gate</Link>
            </Button>
          </EmptyState>
        ) : (
          <div className="bg-card overflow-hidden rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">Run</TableHead>
                  <TableHead>Verdict</TableHead>
                  <TableHead>Attacks planned</TableHead>
                  <TableHead>Facts used by planner</TableHead>
                  <TableHead className="pr-5">Facts written</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {view.runs.map((r) => {
                  const added = newAttacks(r, view.runs);
                  return (
                    <TableRow key={r.run_id} className="align-top">
                      <TableCell className="py-3 pl-5">
                        <Link
                          href={`/gate/runs/${encodeURIComponent(r.run_id)}`}
                          className="font-mono text-xs font-medium underline-offset-4 hover:underline"
                        >
                          {r.run_id}
                        </Link>
                        <div className="text-muted-foreground mt-0.5 text-xs">{r.change_id}</div>
                      </TableCell>
                      <TableCell className="py-3">
                        <StatusPill value={r.status} />
                      </TableCell>
                      <TableCell className="py-3">
                        <div className="text-xs font-medium tabular-nums">{r.attack_ids.length}</div>
                        <ul className="mt-1 space-y-0.5">
                          {r.attack_ids.map((a) => (
                            <li key={a} className={cn("font-mono text-[11px]", added.has(a) ? "text-info" : "text-muted-foreground")}>
                              {added.has(a) && <span className="mr-1">+</span>}
                              {a}
                            </li>
                          ))}
                        </ul>
                      </TableCell>
                      <TableCell className="py-3">
                        {r.memory_fact_ids_used.length ? (
                          <div className="flex flex-wrap gap-1">
                            {r.memory_fact_ids_used.map((f) => (
                              <FactChip key={f} id={f} fact={facts.get(f)} variant="used" />
                            ))}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-xs">none (no memory yet)</span>
                        )}
                      </TableCell>
                      <TableCell className="py-3 pr-5">
                        {r.memory_facts_written.length ? (
                          <div className="flex flex-wrap gap-1">
                            {r.memory_facts_written.map((f) => (
                              <FactChip key={f} id={f} fact={facts.get(f)} variant="written" />
                            ))}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-xs">none</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <Section title={`Facts (${view.facts.length})`} icon={Library} description="Append-only. Superseded facts are kept for audit.">
        {view.facts.length === 0 ? (
          <EmptyState title="No facts yet" description="Facts appear once a run confirms a finding." icon={Library} />
        ) : (
          <div className="space-y-3">
            {view.facts.map((f, i) => {
              const old = superseded.has(f.fact_id);
              return (
                <Reveal key={f.fact_id} index={i}>
                  <article className={cn("bg-card rounded-xl border p-5", old && "opacity-60")}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <code className="min-w-0 truncate font-mono text-xs font-medium" title={f.fact_id}>
                        {f.fact_id}
                      </code>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        <span className="text-muted-foreground rounded-full border px-2 py-0.5">{f.kind.replaceAll("_", " ")}</span>
                        <span className="text-muted-foreground rounded-full border px-2 py-0.5">
                          {f.verification} / {f.trust.replaceAll("_", " ")}
                        </span>
                        {old && <span className="rounded-full border px-2 py-0.5">superseded (kept for audit)</span>}
                      </div>
                    </div>
                    <p className="mt-2 text-sm leading-relaxed">{f.summary}</p>
                    <dl className="text-muted-foreground mt-3 grid gap-x-6 gap-y-1 border-t pt-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                      <div>
                        <dt>Proved by</dt>
                        <dd className="text-foreground truncate font-mono">{f.source.finding_id ?? "n/a"}</dd>
                      </div>
                      <div>
                        <dt>Oracle</dt>
                        <dd className="text-foreground truncate font-mono">{f.source.oracle_id ?? "n/a"}</dd>
                      </div>
                      <div>
                        <dt>Commit</dt>
                        <dd className="text-foreground font-mono">{f.source.commit ? shortSha(f.source.commit) : "n/a"}</dd>
                      </div>
                      <div>
                        <dt>Known at</dt>
                        <dd className="text-foreground font-mono tabular-nums">{f.known_at.slice(0, 19).replace("T", " ")}Z</dd>
                      </div>
                    </dl>
                    {f.supersedes && (
                      <p className="text-muted-foreground mt-2 text-xs">
                        Supersedes <code className="font-mono">{f.supersedes}</code>
                      </p>
                    )}
                  </article>
                </Reveal>
              );
            })}
          </div>
        )}
      </Section>

      <Section title="Provenance">
        <ProvenanceList provenance={[view.provenance]} />
      </Section>
    </main>
  );
}
