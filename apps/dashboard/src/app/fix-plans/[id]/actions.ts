"use server";

import { redirect } from "next/navigation";

import { API_URL } from "@/lib/api";

// The reviewer token stays on the server; the browser never sees it and never sends a reviewer id.
export async function decide(formData: FormData): Promise<void> {
  const id = String(formData.get("subject_id") ?? "");
  const token = process.env.GAUNTLET_REVIEWER_TOKEN;
  const back = `/fix-plans/${encodeURIComponent(id)}`;
  if (!token) redirect(`${back}?msg=${encodeURIComponent("No reviewer token configured on the dashboard server")}`);
  const decision = String(formData.get("decision"));
  const reason = String(formData.get("reason") ?? "").trim();
  const res = await fetch(`${API_URL}/v1/fix-plans/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify({
      subject: "fix_plan",
      subject_id: id,
      plan_sha256: String(formData.get("plan_sha256")),
      decision,
      reason: reason || null,
    }),
  });
  const msg = res.ok ? `Recorded: ${decision}. Nothing was executed.` : `Refused (${res.status})`;
  redirect(`${back}?msg=${encodeURIComponent(msg)}`);
}
