import { describe, expect, it } from "vitest";

import { classificationTone, isOffline, parseGateRun, type Provenance } from "./gauntlet";

const offline: Provenance = { provider: "golden-recording", mode: "offline_recording", live: false, label: "OFFLINE" };
const live: Provenance = { provider: "anchor", mode: "live", live: true, label: "Anchor session" };

describe("isOffline", () => {
  it("flags any non-live artifact", () => {
    expect(isOffline([live, offline])).toBe(true);
  });
  it("treats missing provenance as offline", () => {
    expect(isOffline([])).toBe(true);
  });
  it("is false only when everything is live", () => {
    expect(isOffline([live])).toBe(false);
  });
});

describe("classificationTone", () => {
  it("never shows inconclusive or not_tested as good", () => {
    expect(classificationTone("inconclusive")).toBe("unknown");
    expect(classificationTone("not_tested")).toBe("unknown");
    expect(classificationTone("not_replayable")).toBe("unknown");
  });
  it("marks harms and passes", () => {
    expect(classificationTone("tainted")).toBe("bad");
    expect(classificationTone("confirmed_regression")).toBe("bad");
    expect(classificationTone("cleared")).toBe("good");
  });
});

describe("parseGateRun", () => {
  it("rejects a run without provenance", () => {
    expect(() => parseGateRun({ run_id: "r", status: "passed", attribution: "unknown", attempts: [], events: [] })).toThrow();
  });
  it("rejects an attempt whose provenance lacks the live flag", () => {
    const bad = { run_id: "r", status: "passed", attribution: "unknown", provenance: [offline], events: [], attempts: [{ revision: "head", outcome: "pass", provenance: { provider: "x" } }] };
    expect(() => parseGateRun(bad)).toThrow();
  });
});
