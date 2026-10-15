import { describe, expect, it } from "vitest";

import { parseFakeRun, parseOfflineGate } from "./api";

const sample = {
  label: "FAKE RUN: x",
  run_id: "run-001",
  plan: { attack_id: "a1", hypothesis: "h", steps: [{ action: "navigate", path: "/checkout" }] },
  events: [{ sequence: 1, event_type: "plan_frozen", actor: "control-plane" }],
};

describe("parseFakeRun", () => {
  it("accepts a valid payload", () => {
    expect(parseFakeRun(sample).run_id).toBe("run-001");
  });
  it("rejects a payload missing the plan", () => {
    expect(() => parseFakeRun({ ...sample, plan: undefined })).toThrow();
  });
});
describe("parseOfflineGate", () => {
  it("rejects a payload without a verdict", () => {
    expect(() => parseOfflineGate({ label: "x", events: [] })).toThrow();
  });
});
