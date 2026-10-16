import { redirect } from "next/navigation";
import Link from "next/link";

import { Card, ErrorPanel, OfflineBadge, ProvenanceList, Section, StatusPill } from "@/components/shared";
import { api, type CounterfactualCase } from "@/lib/gauntlet";

import { recallApi, ReviewerAuthRequired } from "@/lib/recall-api";

export const dynamic = "force-dynamic";

function LineagePath({ c }: { c: CounterfactualCase }) {
  const path = c.exposure.path;
  const first = path[0];
  if (!first) return null;
  return (
    <p style={{ fontSize: 13 }}>
      <code>{first.source.kind}:{first.source.node_id}</code>
      {path.map((e) => (
        <span key={e.edge_id}>
          {" "}—<em>{e.relation}</em>→ <code>{e.target.kind}:{e.target.node_id}</code>
        </span>
      ))}
      {" "}({c.exposure.direct ? "direct" : "second-order"})
    </p>
  );
}

export default async function RecallPage() {
  let timeline, audit, cf;
  try {
    [timeline, audit, cf] = await Promise.all([api.timeline(), recallApi.audit(), recallApi.counterfactual()]);
  } catch (err) {
    if (err instanceof ReviewerAuthRequired) redirect("/login?next=/recall");
    return <ErrorPanel what="Recall" error={err} />;
  }
  const flagged = new Set(audit.verdicts.filter((v) => v.classification !== "audit_clear").map((v) => v.decision_id));
  const exposed = new Set(cf.cases.map((c) => c.decision_id));
  return (
    <main>
      <h1>Recall — refund-tool agent</h1>
      <OfflineBadge provenance={[...audit.provenance, ...cf.provenance]} />
      <p>
        Audit past agent decisions from recorded history, then replay exposed ones with the suspect source removed.{" "}
        <Link href="/recall/review">Review queue →</Link>
      </p>

      <Section title={`Event audit — ${audit.summary.tool_name}`}>
        <p>
          {audit.summary.audited} operations audited: <StatusPill value="audit_violation" /> {audit.summary.violations} ·{" "}
          <StatusPill value="audit_clear" /> {audit.summary.clear} · <StatusPill value="inconclusive" /> {audit.summary.inconclusive}
        </p>
        {(audit.summary.gaps ?? []).map((g) => <p key={g}>Gap: {g}</p>)}
        {audit.verdicts
          .filter((v) => v.classification !== "audit_clear")
          .map((v) => (
            <Card key={v.verdict_id} tone={v.classification}>
              <StatusPill value={v.classification} /> <code>{v.tool_event_id}</code> ({v.decision_id})
              <p style={{ margin: "4px 0" }}>{v.rationale}</p>
              <small>Evidence: {(v.evidence_ids ?? []).join(", ") || "none"} · criterion {v.criterion_version}</small>
              {(v.limitations ?? []).length > 0 && <small> · limits: {(v.limitations ?? []).join("; ")}</small>}
            </Card>
          ))}
        <p style={{ fontSize: 13 }}>A caller/owner mismatch alone is never a violation; only a ledger credit to a non-owner is.</p>
      </Section>

      <Section title={`Counterfactual — trigger ${cf.trigger_reference}`}>
        <p>
          {Object.entries(cf.counts)
            .filter(([, n]) => n > 0)
            .map(([k, n]) => (
              <span key={k} style={{ marginRight: 12 }}><StatusPill value={k} /> {n}</span>
            ))}
        </p>
        {cf.cases.map((c) => (
          <Card key={c.decision_id} tone={c.verdict.classification}>
            <StatusPill value={c.verdict.classification} /> <strong>{c.decision_id}</strong>
            <LineagePath c={c} />
            <p style={{ margin: "4px 0" }}>{c.verdict.rationale}</p>
            <small>
              control matches: {String(c.verdict.control_matches ?? "n/a")} · material change: {String(c.verdict.material_change ?? "n/a")} ·
              replays: {(c.verdict.replay_ids ?? []).length}
              {c.missing_fields.length > 0 && ` · missing: ${c.missing_fields.join(", ")}`}
            </small>
          </Card>
        ))}
        {cf.gaps.map((g) => <p key={g}>Gap: {g}</p>)}
      </Section>

      <Section title="Decision timeline (7 days)">
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr><th align="left">Time</th><th align="left">Decision</th><th align="left">Requester</th><th align="left">Action</th><th align="left">Flags</th></tr>
          </thead>
          <tbody>
            {timeline.map((d) => (
              <tr key={d.decision.decision_id} style={{ background: flagged.has(d.decision.decision_id) ? "#fff5f5" : undefined }}>
                <td>{d.decision.occurred_at.replace("T", " ").slice(0, 16)}</td>
                <td>{d.decision.decision_id}</td>
                <td>{d.requester}</td>
                <td>{d.decision.structured_action}{d.decision.amount_minor != null && ` ${d.decision.amount_minor}¢`}</td>
                <td>
                  {exposed.has(d.decision.decision_id) && "exposed "}
                  {flagged.has(d.decision.decision_id) && "audit-flagged"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Provenance">
        <ProvenanceList provenance={[...audit.provenance, ...cf.provenance]} />
      </Section>
    </main>
  );
}
