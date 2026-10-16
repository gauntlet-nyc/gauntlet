import Link from "next/link";

import { ErrorPanel, OfflineBadge, Section, StatusPill } from "@/components/ui";
import { api } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function MemoryPage() {
  let view;
  try {
    view = await api.memory();
  } catch (err) {
    return <ErrorPanel what="Memory" error={err} />;
  }
  const superseded = new Set(view.facts.map((f) => f.supersedes).filter(Boolean));
  return (
    <main>
      <h1>Memory comparison</h1>
      <OfflineBadge provenance={[view.provenance]} />
      <p>
        Each confirmed finding becomes a typed fact that cites the finding and oracle that proved it. Later plans
        receive only facts known at planning time, as untrusted evidence; they never replace the oracle. Corrections
        supersede older facts; nothing is overwritten.
      </p>
      <Section title="Planning with vs without memory">
        {view.runs.length === 0 ? (
          <p>
            No runs yet. Start the same change twice on the <Link href="/gate">Gate</Link> page to compare.
          </p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr><th align="left">Run</th><th align="left">Change</th><th align="left">Verdict</th><th align="left">Facts given to the planner</th><th align="left">Facts written</th></tr>
            </thead>
            <tbody>
              {view.runs.map((r) => (
                <tr key={r.run_id} style={{ borderTop: "1px solid #eee", verticalAlign: "top" }}>
                  <td><Link href={`/gate/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link></td>
                  <td>{r.change_id}</td>
                  <td><StatusPill value={r.status} /></td>
                  <td>{r.memory_fact_ids_used.length ? r.memory_fact_ids_used.map((f) => <code key={f}>{f} </code>) : <em>none (no memory yet)</em>}</td>
                  <td>{r.memory_facts_written.map((f) => <code key={f}>{f} </code>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      <Section title={`Facts (${view.facts.length})`}>
        {view.facts.map((f) => (
          <div key={f.fact_id} style={{ border: "1px solid #ddd", borderRadius: 4, padding: "6px 10px", margin: "6px 0", opacity: superseded.has(f.fact_id) ? 0.55 : 1 }}>
            <code>{f.fact_id}</code> · {f.kind} · {f.verification}/{f.trust} {superseded.has(f.fact_id) && <strong>· superseded (kept for audit)</strong>}
            <p style={{ margin: "4px 0" }}>{f.summary}</p>
            <small>
              proved by <code>{f.source.finding_id}</code> with <code>{f.source.oracle_id}</code> on <code>{f.source.commit?.slice(0, 7)}</code> · known {f.known_at}
              {f.supersedes && <> · supersedes <code>{f.supersedes}</code></>}
            </small>
          </div>
        ))}
      </Section>
      <p style={{ fontSize: 13, color: "#555" }}>{view.provenance.label}</p>
    </main>
  );
}
