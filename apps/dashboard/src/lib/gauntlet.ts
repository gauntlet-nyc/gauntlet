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

/** True when anything shown came from fakes, recordings or fixtures rather than a live run. */
export function isOffline(provenance: readonly Provenance[]): boolean {
  return provenance.length === 0 || provenance.some((p) => !p.live);
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
