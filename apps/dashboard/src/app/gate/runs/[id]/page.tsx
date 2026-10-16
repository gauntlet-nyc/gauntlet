import { decide, runRepair } from "@/app/actions";
import { VoiceBriefingButton } from "@/components/VoiceBriefing";
import { Banner, Card, DecideForm, ErrorPanel, OfflineBadge, ProvenanceList, Section, StatusPill } from "@/components/ui";
import { api, artifactUrl, shortSha, type AttemptView } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

function AttemptTable({ attempts }: { attempts: AttemptView[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr><th align="left">Attack</th><th align="left">Revision</th><th align="left">#</th><th align="left">SHA</th><th align="left">Outcome</th><th align="left">Oracle observed</th></tr>
      </thead>
      <tbody>
        {attempts.map((a) => (
          <tr key={`${a.attack_id}-${a.revision}-${a.attempt}`} style={{ verticalAlign: "top" }}>
            <td><code>{a.attack_id}</code></td>
            <td>{a.revision}</td>
            <td>{a.attempt}</td>
            <td><code>{shortSha(a.source_sha)}</code></td>
            <td><StatusPill value={a.outcome} /></td>
            <td>{a.observed}</td>
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
  let run, briefing, check;
  try {
    [run, briefing, check] = await Promise.all([api.run(id), api.briefing(id), api.checkRun(id)]);
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
        {run.attacks.length > 0 ? (
          <>
            <p style={{ fontSize: 13 }}>
              Plan hash <code>{run.plan_sha256}</code> frozen before any worker ran · planner <code>{run.model_id}</code>
            </p>
            {run.attacks.map((attack) => (
              <Card key={attack.attack_id}>
                <strong>{attack.attack_id}</strong> ({attack.worker_kind} worker): {attack.hypothesis}
                <p style={{ fontSize: 13, margin: "4px 0" }}>Why this change: {attack.why_this_change}</p>
                <ol style={{ fontSize: 13 }}>
                  {attack.steps.map((s, i) => (
                    <li key={i}><code>{JSON.stringify(s)}</code></li>
                  ))}
                </ol>
                <small>Oracles: {attack.oracle_ids.join(", ")} · cites {(attack.source_refs ?? []).map((r) => `${r.path}:${r.start_line}`).join(", ")}</small>
              </Card>
            ))}
          </>
        ) : (
          <p>No attack was accepted for this change.</p>
        )}
        {run.rejected_attacks.length > 0 && (
          <>
            <p>Rejected by the validator:</p>
            <ul>{run.rejected_attacks.map((r) => <li key={r}>{r}</li>)}</ul>
          </>
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
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {run.attempts.flatMap((a) =>
              a.screenshot_artifact_ids.map((id) => (
                <figure key={id} style={{ margin: 0, fontSize: 11 }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={artifactUrl(run.run_id, id)} alt={`${a.revision} attempt ${a.attempt}`} width={96} height={96} style={{ border: "1px solid #ccc", imageRendering: "pixelated" }} />
                  <figcaption>{a.revision} #{a.attempt}</figcaption>
                </figure>
              )),
            )}
          </div>
        ) : (
          <p>No screenshots were captured for this run.</p>
        )}
        <p style={{ fontSize: 12, color: "#555" }}>Screenshot bytes are served only by exact run and artifact ID from the write-once store.</p>
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
          {run.fix_plan.repairable ? (
            <form action={runRepair} style={{ marginTop: 8 }}>
              <input type="hidden" name="run_id" value={run.run_id} />
              <button type="submit">Apply approved plan in a fresh worktree and re-verify</button>
              {query.repair && query.repair !== "done" && (
                <span role="alert"> Refused (HTTP {query.repair}): approve this exact hash first; approvals are single use.</span>
              )}
            </form>
          ) : (
            <p style={{ fontSize: 13 }}>This sample plan is for review only; the repair runner is wired for AI-agent findings.</p>
          )}
          {run.repair && (
            <Card tone={run.repair.verdict === "fix_verified_review_required" ? "passed" : "fail"}>
              <strong>Release verdict: {run.repair.verdict.replaceAll("_", " ")}</strong>
              {run.repair.patched_sha && (
                <span> · patched <code>{shortSha(run.repair.patched_sha)}</code> (local commit, never pushed)</span>
              )}
              <ul>
                {run.repair.checks.map((c) => (
                  <li key={c.name}>
                    <StatusPill value={c.passed ? "pass" : "fail"} /> {c.name.replaceAll("_", " ")} — {c.detail}
                  </li>
                ))}
              </ul>
              <small>{run.repair.note}</small>
              <ProvenanceList provenance={run.repair.provenance} />
            </Card>
          )}
        </Section>
      )}

      <Section title="GitHub check run (preview)">
        <p>
          <strong>{check.name}</strong> · conclusion <StatusPill value={check.conclusion === "failure" ? "fail" : check.conclusion === "success" ? "pass" : "inconclusive"} /> · {check.title}
        </p>
        <pre style={{ background: "#f6f8fa", padding: 8, fontSize: 12, whiteSpace: "pre-wrap" }}>{check.summary}</pre>
        <small style={{ color: "#555" }}>{check.note} Checks-only: Gauntlet never comments, approves or merges.</small>
      </Section>

      <Section title="Events">
        <ol>
          {run.events.map((e) => (
            <li key={e.event_id}>
              #{e.sequence} <code>{e.event_type}</code> by {e.actor} <small style={{ wordBreak: "break-all" }}>{JSON.stringify(e.payload)}</small>
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
