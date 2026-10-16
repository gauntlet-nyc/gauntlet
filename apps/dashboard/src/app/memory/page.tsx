import { Brain, GitCompareArrows } from "lucide-react";
import Link from "next/link";

import { FactChip, MemoryFlow, type FlowStep, type MemoryFact } from "@/components/memory";
import { EmptyState, ErrorPanel, OfflineBadge, PageHeader, Section, StatusPill } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type MemoryView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type MemoryRun = MemoryView["runs"][number];

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
      detail: "Independent of memory",
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
  const flow = flowFor(view.runs, facts);

  return (
    <main>
      <PageHeader
        eyebrow="Memory"
        icon={Brain}
        title="Planning memory"
        description="Confirmed findings become cited facts that later plans can use. Memory is evidence for planning, never the oracle."
        actions={<OfflineBadge provenance={[view.provenance]} />}
      />

      {flow && (
        <div className="mt-2">
          <MemoryFlow steps={flow.steps} links={flow.links} />
        </div>
      )}

      <Section
        title="Planning with vs without memory"
        description="Hover a fact for its provenance."
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
          <div className="overflow-hidden rounded-xl border">
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

    </main>
  );
}
