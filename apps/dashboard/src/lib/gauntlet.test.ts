import { describe, expect, it } from "vitest";

import { classificationTone, parseGateRun, provenanceBadge, provenanceMode, type Provenance } from "./gauntlet";

const offline: Provenance = { provider: "golden-recording", mode: "offline_recording", live: false, label: "OFFLINE" };
const live: Provenance = { provider: "anchor", mode: "live", live: true, label: "Anchor session" };

describe("provenanceMode", () => {
  it("keeps mixed live and recorded evidence distinct from fully offline evidence", () => {
    expect(provenanceMode([live, offline])).toBe("mixed");
    expect(provenanceMode([offline])).toBe("offline");
  });
  it("does not infer an offline run from missing provenance", () => {
    expect(provenanceMode([])).toBe("unknown");
  });
  it("recognizes a list whose recorded entries are all live", () => {
    expect(provenanceMode([live])).toBe("live");
  });
});

describe("provenanceBadge", () => {
  it("limits the no-provider claim to fully offline evidence", () => {
    expect(provenanceBadge([offline]).text).toBe("OFFLINE / live NOT RUN");
    expect(provenanceBadge([offline]).title).toContain("no provider was contacted");
    expect(provenanceBadge([live, offline]).text).toContain("MIXED");
    expect(provenanceBadge([live, offline]).title).toContain("live and offline");
    expect(provenanceBadge([live, offline]).title).not.toContain("no provider was contacted");
  });
  it("reports live evidence without claiming every possible provider ran", () => {
    expect(provenanceBadge([live]).text).toBe("LIVE EVIDENCE");
    expect(provenanceBadge([live]).title).not.toContain("all providers");
  });
  it("shows absent provenance as unknown", () => {
    expect(provenanceBadge([]).text).toBe("PROVENANCE UNKNOWN");
    expect(provenanceBadge([]).title).not.toContain("no provider was contacted");
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
  it("rejects an attempt without its screenshot list", () => {
    const bad = { run_id: "r", status: "passed", attribution: "unknown", provenance: [offline], events: [], attempts: [{ revision: "head", outcome: "pass" }] };
    expect(() => parseGateRun(bad)).toThrow();
  });
});
