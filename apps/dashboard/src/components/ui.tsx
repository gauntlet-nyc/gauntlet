import type { ReactNode } from "react";

import { classificationTone, isOffline, type Provenance } from "@/lib/gauntlet";

const TONE = {
  bad: { background: "#fde8e8", color: "#9b1c1c", border: "#f8b4b4" },
  good: { background: "#def7ec", color: "#03543f", border: "#84e1bc" },
  unknown: { background: "#fdf6b2", color: "#723b13", border: "#faca15" },
} as const;

export function StatusPill({ value }: { value: string }) {
  const tone = TONE[classificationTone(value)];
  return (
    <span
      data-testid="status-pill"
      style={{ ...tone, border: `1px solid ${tone.border}`, borderRadius: 4, padding: "1px 6px", fontWeight: 600, fontSize: 13 }}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

/** Shown whenever any data on the page came from fakes, recordings or fixtures. */
export function OfflineBadge({ provenance }: { provenance: readonly Provenance[] }) {
  if (!isOffline(provenance)) return null;
  return (
    <div
      role="status"
      data-testid="offline-badge"
      style={{ background: "#111", color: "#ffd400", padding: "6px 10px", borderRadius: 4, fontWeight: 700, margin: "8px 0" }}
    >
      OFFLINE / live NOT RUN — data below comes from recordings, fixtures or fakes
    </div>
  );
}

export function ProvenanceList({ provenance }: { provenance: readonly Provenance[] }) {
  return (
    <ul style={{ fontSize: 13, color: "#444" }}>
      {provenance
        .filter((p, i, all) => all.findIndex((q) => q.provider === p.provider && q.label === p.label) === i)
        .map((p) => (
        <li key={`${p.provider}-${p.label}`}>
          <code>{p.provider}</code> · {p.live ? "LIVE" : "OFFLINE"} · {p.label}
        </li>
      ))}
    </ul>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h2 style={{ fontSize: 18, borderBottom: "1px solid #ddd", paddingBottom: 4 }}>{title}</h2>
      {children}
    </section>
  );
}

export function Card({ children, tone }: { children: ReactNode; tone?: string }) {
  const border = tone ? TONE[classificationTone(tone)].border : "#ddd";
  return (
    <div style={{ border: `1px solid ${border}`, borderLeft: `4px solid ${border}`, borderRadius: 4, padding: "8px 12px", margin: "8px 0" }}>
      {children}
    </div>
  );
}

export function ErrorPanel({ what, error }: { what: string; error: unknown }) {
  return (
    <main>
      <h1>{what} unavailable</h1>
      <p>Could not reach the Gauntlet API: {String(error)}</p>
      <p>Start it with <code>uv run uvicorn gauntlet.api.main:app --port 8000</code>.</p>
    </main>
  );
}

export function Banner({ params }: { params: Record<string, string | string[] | undefined> }) {
  const approval = params.approval;
  if (!approval) return null;
  const ok = approval === "recorded";
  return (
    <p role="status" style={{ background: ok ? "#def7ec" : "#fde8e8", padding: 8 }}>
      {ok
        ? "Decision recorded and bound to this exact plan hash. Nothing was merged, deployed, refunded or sent."
        : `Decision refused by the API (HTTP ${String(approval)}). 401 = log in; 409 = plan changed, review again.`}
    </p>
  );
}

type DecideProps = {
  action: (form: FormData) => Promise<void>;
  runId: string;
  subject: "fix_plan" | "remediation" | "scope";
  subjectId: string;
  planSha256: string;
  back: string;
  approveLabel?: string;
};

export function DecideForm({ action, runId, subject, subjectId, planSha256, back, approveLabel = "Approve" }: DecideProps) {
  return (
    <form action={action} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="subject" value={subject} />
      <input type="hidden" name="subject_id" value={subjectId} />
      <input type="hidden" name="plan_sha256" value={planSha256} />
      <input type="hidden" name="back" value={back} />
      <input name="reason" placeholder="Reason (required to reject)" style={{ flex: 1, minWidth: 180 }} />
      <button type="submit" name="decision" value="approved">{approveLabel}</button>
      <button type="submit" name="decision" value="rejected">Reject</button>
      <small style={{ width: "100%", color: "#555" }}>
        Binds to plan hash <code>{planSha256.slice(0, 16)}…</code>. Human decision only; no auto-merge or remediation.
      </small>
    </form>
  );
}
