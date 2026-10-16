import { afterEach, describe, expect, it, vi } from "vitest";

const { cookieGet } = vi.hoisted(() => ({ cookieGet: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: cookieGet }) }));

import { recallApi, ReviewerAuthRequired } from "./recall-api";

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("server Recall requests", () => {
  it.each(["audit", "counterfactual", "reviewQueue"] as const)("forwards the httpOnly reviewer token for %s", async (method) => {
    cookieGet.mockReturnValue({ value: "private-reviewer-token" });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(method === "reviewQueue" ? [] : { provenance: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await recallApi[method]();
    expect(fetcher.mock.calls[0]?.[1]).toEqual({ cache: "no-store", headers: { authorization: "Bearer private-reviewer-token" } });
    expect(String(fetcher.mock.calls[0]?.[0])).not.toContain("private-reviewer-token");
  });
  it("allows a public offline read without a token", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetcher = vi.fn().mockResolvedValue(new Response('{"provenance":[]}', { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await recallApi.audit();
    expect(fetcher.mock.calls[0]?.[1]?.headers).toEqual({});
  });
  it("signals login for a missing or expired reviewer token without exposing it", async () => {
    cookieGet.mockReturnValue({ value: "private-reviewer-token" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("denied", { status: 401 })));
    await expect(recallApi.counterfactual()).rejects.toThrow(ReviewerAuthRequired);
  });
});
