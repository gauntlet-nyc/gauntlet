import { z } from "zod";

import { API_URL } from "./api";
import type { components } from "./api-types";

type S = components["schemas"];
export type Provenance = S["Provenance"];
export type GateRunView = S["GateRunView"];
export type GateRunSummary = S["GateRunSummary"];
export type ChangeOption = S["ChangeOption"];
export type AttemptView = S["AttemptView"];
export type AuditView = S["AuditView"];
export type CounterfactualView = S["CounterfactualView"];
export type CounterfactualCase = S["CounterfactualCase"];
export type DecisionView = S["DecisionView"];
export type ReviewItem = S["ReviewItem"];
export type SponsorStatus = S["SponsorStatus"];
export type BriefingView = S["BriefingView"];
export type ApprovalRecord = S["ApprovalRecord"];
export type CheckRunPreview = S["CheckRunPreview"];
export type OnboardingView = S["OnboardingView"];
export type MemoryView = S["MemoryView"];

// Runtime checks at the untrusted boundary: only the fields the UI relies on for safety labels.
const provenanceSchema = z.object({
  provider: z.string(),
  mode: z.string(),
  live: z.boolean(),
  label: z.string(),
});

const gateRunSchema = z
  .object({
    run_id: z.string(),
    status: z.string(),
    attribution: z.string(),
    attempts: z.array(z.object({ revision: z.string(), outcome: z.string(), screenshot_artifact_ids: z.array(z.string()) }).passthrough()),
    provenance: z.array(provenanceSchema),
    events: z.array(z.object({ sequence: z.number(), event_type: z.string() }).passthrough()),
  })
  .passthrough();

const withProvenance = z.object({ provenance: z.array(provenanceSchema) }).passthrough();

export function parseGateRun(data: unknown): GateRunView {
  return gateRunSchema.parse(data) as unknown as GateRunView;
}

export function parseWithProvenance<T>(data: unknown): T {
  return withProvenance.parse(data) as unknown as T;
}

export type ProvenanceMode = "offline" | "mixed" | "live" | "unknown";

/** Classify the evidence supplied to this view, without inferring unlisted providers. */
export function provenanceMode(provenance: readonly Provenance[]): ProvenanceMode {
  if (provenance.length === 0) return "unknown";
  const hasLive = provenance.some((p) => p.live);
  const hasOffline = provenance.some((p) => !p.live);
  if (hasLive && hasOffline) return "mixed";
  return hasLive ? "live" : "offline";
}

export function provenanceBadge(provenance: readonly Provenance[]): { text: string; title: string } {
  switch (provenanceMode(provenance)) {
    case "offline":
      return {
        text: "OFFLINE / live NOT RUN",
        title: "Data on this page comes from recordings, fixtures or fakes; no provider was contacted.",
      };
    case "mixed":
      return {
        text: "MIXED EVIDENCE",
        title: "This view includes live and offline provider evidence. Check the provenance list for each source.",
      };
    case "live":
      return {
        text: "LIVE EVIDENCE",
        title: "The listed provenance entries are live. Check the provenance list for their scope.",
      };
    case "unknown":
      return { text: "PROVENANCE UNKNOWN", title: "No provider provenance was supplied for this view." };
  }
}

/** Gate's static fixture diff is report context, not an execution adapter. */
export function executionProvenance(provenance: readonly Provenance[]): Provenance[] {
  return provenance.filter((p) => p.provider !== "cartwheel-templates");
}

/** The summary boolean covers offline and missing adapters, so it is not a live/offline verdict. */
export function gateSummaryEvidence(offline: boolean): string {
  return offline ? "Offline or unreported evidence" : "No offline execution reported";
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

export function classificationTone(value: string): "bad" | "good" | "unknown" {
  if (["confirmed_regression", "confirmed_policy_violation", "confirmed_pre_existing", "tainted", "audit_violation", "fail"].includes(value)) {
    return "bad";
  }
  if (["passed", "cleared", "audit_clear", "pass"].includes(value)) return "good";
  return "unknown";
}

async function get<T>(path: string, parse: (d: unknown) => T): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return parse(await res.json());
}

const asArray = <T,>(d: unknown): T[] => z.array(z.unknown()).parse(d) as T[];

export const api = {
  changes: () => get<ChangeOption[]>("/gate/changes", asArray),
  runs: () => get<GateRunSummary[]>("/gate/runs", asArray),
  run: (id: string) => get(`/gate/runs/${encodeURIComponent(id)}`, parseGateRun),
  briefing: (id: string) => get<BriefingView>(`/gate/runs/${encodeURIComponent(id)}/briefing`, (d) => d as BriefingView),
  timeline: () => get<DecisionView[]>("/recall/timeline", asArray),
  sponsors: () => get<SponsorStatus[]>("/sponsors", asArray),
  approvals: () => get<ApprovalRecord[]>("/approvals", asArray),
  checkRun: (id: string) => get<CheckRunPreview>(`/gate/runs/${encodeURIComponent(id)}/check-run`, (d) => d as CheckRunPreview),
  memory: () => get<MemoryView>("/memory", (d) => d as MemoryView),
  onboarding: () => get<OnboardingView>("/onboarding", (d) => d as OnboardingView),
};

export function artifactUrl(runId: string, artifactId: string): string {
  return `${API_URL}/gate/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
}
