import Link from "next/link";

import { startRun } from "@/app/actions";
import { ErrorPanel, OfflineBadge, Section, StatusPill } from "@/components/ui";
import { api, shortSha } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function GatePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  let changes, runs;
  try {
    [changes, runs] = await Promise.all([api.changes(), api.runs()]);
  } catch (err) {
    return <ErrorPanel what="Gate" error={err} />;
  }
  return (
    <main>
      <h1>Gate</h1>
      <p>Read a PR diff, plan attacks, run them on base and head, let independent oracles decide.</p>
      {runs.some((r) => r.offline) && <OfflineBadge provenance={[]} />}
      {params.error && <p role="alert">Could not start run (HTTP {params.error}).</p>}
      <Section title="Start a run">
        <form action={startRun} style={{ display: "flex", gap: 8 }}>
          <select name="change_id" defaultValue="help-button">
            {changes.map((c) => (
              <option key={c.change_id} value={c.change_id}>
                {c.feature_intent} ({shortSha(c.base_sha)}..{shortSha(c.head_sha)})
                {c.offline_recording_available ? " — offline recording" : " — needs live run"}
              </option>
            ))}
          </select>
          <button type="submit">Start Gate run</button>
        </form>
      </Section>
      <Section title="Runs">
        {runs.length === 0 ? (
          <p>No runs yet in this API process.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr><th align="left">Run</th><th align="left">Change</th><th align="left">Verdict</th><th align="left">Source</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td><Link href={`/gate/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link></td>
                  <td>{r.change_id}</td>
                  <td><StatusPill value={r.status} /> {r.attribution !== "unknown" && r.attribution}</td>
                  <td>{r.offline ? "OFFLINE" : "live"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </main>
  );
}
