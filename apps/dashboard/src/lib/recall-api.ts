// next/headers is server-only: reviewer credentials never enter client components.
import { cookies } from "next/headers";
import { z } from "zod";

import { API_URL } from "./api";
import { parseWithProvenance, type AuditView, type CounterfactualView, type ReviewItem } from "./gauntlet";

export class ReviewerAuthRequired extends Error {
  constructor() { super("Reviewer login required for live Recall"); }
}

async function get<T>(path: string, parse: (data: unknown) => T): Promise<T> {
  const token = (await cookies()).get("gauntlet_reviewer_token")?.value;
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) throw new ReviewerAuthRequired();
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return parse(await res.json());
}

export const recallApi = {
  audit: () => get<AuditView>("/recall/audit", parseWithProvenance),
  counterfactual: () => get<CounterfactualView>("/recall/counterfactual", parseWithProvenance),
  reviewQueue: () => get<ReviewItem[]>("/recall/review-queue", (d) => z.array(z.unknown()).parse(d) as ReviewItem[]),
};
