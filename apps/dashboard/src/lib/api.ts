import { z } from "zod";

import type { components } from "./api-types";

export const API_URL = process.env.NEXT_PUBLIC_GAUNTLET_API_URL ?? "http://localhost:8000";

export type FakeRun = components["schemas"]["FakeRunResponse"];

// Runtime check at the untrusted boundary; the TS type above is generated from OpenAPI.
const fakeRunSchema = z.object({
  label: z.string(),
  run_id: z.string(),
  plan: z.object({
    attack_id: z.string(),
    hypothesis: z.string(),
    steps: z.array(z.object({ action: z.string() }).passthrough()),
  }).passthrough(),
  events: z.array(
    z.object({ sequence: z.number(), event_type: z.string(), actor: z.string() }).passthrough(),
  ),
});

export function parseFakeRun(data: unknown): FakeRun {
  return fakeRunSchema.parse(data) as unknown as FakeRun;
}

export async function getFakeRun(): Promise<FakeRun> {
  const res = await fetch(`${API_URL}/runs/fake`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return parseFakeRun(await res.json());
}

export type ChangeRequest = components["schemas"]["ChangeRequest"];

const changeRequestSchema = z.object({
  repository_id: z.string(),
  base_sha: z.string(),
  head_sha: z.string(),
  fixture_id: z.string(),
  target_id: z.string(),
  feature_intent: z.string().nullable().optional(),
});

export function parseChangeRequest(data: unknown): ChangeRequest {
  return changeRequestSchema.parse(data) as unknown as ChangeRequest;
}

export async function getCartwheelChange(): Promise<ChangeRequest> {
  const res = await fetch(`${API_URL}/targets/cartwheel/change-request`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return parseChangeRequest(await res.json());
}

export type FixPlanView = components["schemas"]["FixPlanView"];

const fixPlanSchema = z.object({
  label: z.string(),
  plan_sha256: z.string(),
  target_id: z.string(),
  fixture_id: z.string(),
  fix_plan: z
    .object({
      fix_plan_id: z.string(),
      rationale: z.string(),
      unified_diff: z.string(),
      allowed_paths: z.array(z.string()),
      test_plan: z.array(z.string()),
    })
    .passthrough(),
  approvals: z.array(
    z.object({ approval_id: z.string(), decision: z.string(), reviewer_id: z.string() }).passthrough(),
  ),
});

export function parseFixPlan(data: unknown): FixPlanView {
  return fixPlanSchema.parse(data) as unknown as FixPlanView;
}

export async function getFixPlan(id: string): Promise<FixPlanView> {
  const res = await fetch(`${API_URL}/v1/fix-plans/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return parseFixPlan(await res.json());
}
