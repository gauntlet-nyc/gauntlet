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

export type OfflineGate = components["schemas"]["OfflineGateResponse"];

const offlineGateSchema = z.object({
  label: z.string(),
  execution_mode: z.string(),
  oracle_outcomes: z.array(z.string()),
  status: z.string(),
  attribution: z.string(),
  events: z.array(z.object({ sequence: z.number(), event_type: z.string() }).passthrough()),
});

export function parseOfflineGate(data: unknown): OfflineGate {
  return offlineGateSchema.parse(data) as unknown as OfflineGate;
}

export async function getOfflineGate(): Promise<OfflineGate> {
  const res = await fetch(`${API_URL}/runs/offline-gate`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return parseOfflineGate(await res.json());
}
