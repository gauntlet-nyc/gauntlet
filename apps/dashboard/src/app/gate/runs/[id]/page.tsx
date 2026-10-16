import { decide } from "@/app/actions";
import { VoiceBriefingButton } from "@/components/VoiceBriefing";
import { Banner, Card, DecideForm, ErrorPanel, OfflineBadge, ProvenanceList, Section, StatusPill } from "@/components/ui";
import { api, shortSha, type AttemptView } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

function AttemptTable({ attempts }: { attempts: AttemptView[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr><th align="left">Revision</th><th align="left">#</th><th align="left">SHA</th><th align="left">Oracle</th><th align="left">Outcome</th><th align="left">Evidence</th></tr>
      </thead>
      <tbody>
        {attempts.map((a) => (
          <tr key={`${a.revision}-${a.attempt}`}>
            <td>{a.revision}</td>
            <td>{a.attempt}</td>
            <td><code>{shortSha(a.source_sha)}</code></td>
            <td><code>{a.oracle_id}</code></td>
            <td><StatusPill value={a.outcome} /></td>
            <td>{a.evidence_ids.join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function GateRunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  let run, briefing;
  try {
    [run, briefing] = await Promise.all([api.run(id), api.briefing(id)]);
  } catch (err) {
    return <ErrorPanel what="Gate run" error={err} />;
  }
  const back = `/gate/runs/${encodeURIComponent(run.run_id)}`;
  const head = run.attempts.filter((a) => a.revision === "head");
  const base = run.attempts.filter((a) => a.revision === "base");
  return (
    <main>
      <h1>Gate run {run.run_id}</h1>
      <OfflineBadge provenance={run.provenance} />
      <Banner params={query} />
      <p>
        <strong>{run.feature_intent}</strong> · <code>{run.target_id}</code> ·{" "}
        <code>{shortSha(run.base_sha)}</code>..<code>{shortSha(run.head_sha)}</code>
      </p>
      <Card tone={run.status}>
        <div style={{ fontSize: 20 }}>
          Verdict: <StatusPill value={run.status} />{" "}
          {run.attribution === "introduced" && "— regression introduced by this PR"}
          {run.attribution === "pre_existing" && "— pre-existing on base"}
        </div>
        {run.not_tested_reason && <p>{run.not_tested_reason}</p>}
      </Card>

      <Section title="Voice briefing">
        <VoiceBriefingButton text={briefing.briefing.spoken_summary} providerLabel={briefing.provenance.label} />
      </Section>

      <Section title="Diff">
        {run.diff.map((d) => (
          <details key={d.path} open={run.diff.length <= 3}>
            <summary><code>{d.path}</code></summary>
            <pre style={{ background: "#f6f8fa", padding: 8, overflowX: "auto", fontSize: 12 }}>{d.unified_diff}</pre>
          </details>
        ))}
      </Section>

      <Section title="Frozen plan">
        {run.frozen_plan ? (
          <>
            <p>
              <strong>{run.frozen_plan.attack_id}</strong> ({run.frozen_plan.worker_kind} worker): {run.frozen_plan.hypothesis}
            </p>
            <p style={{ fontSize: 13 }}>Plan hash <code>{run.plan_sha256}</code> — frozen before any worker ran.</p>
            <ol>
              {run.frozen_plan.steps.map((s, i) => (
                <li key={i}><code>{JSON.stringify(s)}</code></li>
              ))}
            </ol>
            <p>Oracles: {run.frozen_plan.oracle_ids.map((o) => <code key={o}>{o} </code>)}</p>
          </>
        ) : (
          <p>No plan was frozen for this run.</p>
        )}
      </Section>

      <Section title="Attempts: head vs base">
        {run.attempts.length === 0 ? (
          <p>No attempts executed.</p>
        ) : (
          <>
            <p>Head: {head.filter((a) => a.outcome === "fail").length}/{head.length} failed · Base: {base.filter((a) => a.outcome === "fail").length}/{base.length} failed</p>
            <AttemptTable attempts={run.attempts} />
          </>
        )}
        <h3 style={{ fontSize: 15 }}>Screenshots</h3>
        {run.attempts.some((a) => a.screenshot_artifact_ids.length > 0) ? (
          <ul>{run.attempts.flatMap((a) => a.screenshot_artifact_ids.map((s) => <li key={s}><code>{s}</code></li>))}</ul>
        ) : (
          <p>No screenshots: offline recordings carry no image bytes. Live Anchor runs attach them here.</p>
        )}
      </Section>

      <Section title="Findings">
        {run.findings.length === 0 && <p>No findings. Not tested does not mean safe.</p>}
        {run.findings.map((f) => (
          <Card key={f.finding_id} tone={f.status}>
            <StatusPill value={f.status} /> {f.severity} · {f.attack_id} · head {f.head_reproductions}/{f.head_attempts}, base {f.base_reproductions}/{f.base_attempts}
            <ul style={{ fontSize: 13 }}>{(f.limitations ?? []).map((l) => <li key={l}>{l}</li>)}</ul>
          </Card>
        ))}
      </Section>

      {run.fix_plan && (
        <Section title="Fix plan review">
          <OfflineBadge provenance={[run.fix_plan.provenance]} />
          <p>{run.fix_plan.plan.rationale}</p>
          <p>Allowed paths: {run.fix_plan.allowed_paths.map((p) => <code key={p}>{p} </code>)}</p>
          <pre style={{ background: "#f6f8fa", padding: 8, fontSize: 12 }}>{run.fix_plan.plan.unified_diff}</pre>
          <p>Verification plan:</p>
          <ul>{run.fix_plan.plan.test_plan.map((t) => <li key={t}>{t}</li>)}</ul>
          <DecideForm
            action={decide}
            runId={run.run_id}
            subject="fix_plan"
            subjectId={run.fix_plan.plan.fix_plan_id}
            planSha256={run.fix_plan.plan_sha256}
            back={back}
            approveLabel="Approve fix plan"
          />
        </Section>
      )}

      <Section title="Events">
        <ol>
          {run.events.map((e) => (
            <li key={e.event_id}>
              #{e.sequence} <code>{e.event_type}</code> by {e.actor} <small>{JSON.stringify(e.payload)}</small>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Provenance">
        <ProvenanceList provenance={run.provenance} />
      </Section>
    </main>
  );
}
