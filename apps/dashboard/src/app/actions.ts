"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_URL } from "@/lib/api";

const COOKIE = "gauntlet_reviewer_token";

// Dev-grade reviewer login: the token is kept in an httpOnly cookie on the dashboard server and
// sent to the API as a bearer token. The API decides identity from its own server-side table.
export async function login(form: FormData): Promise<void> {
  const token = String(form.get("token") ?? "").trim();
  if (token.length < 16) redirect("/login?error=short");
  (await cookies()).set(COOKIE, token, { httpOnly: true, sameSite: "strict", path: "/" });
  redirect("/login?ok=1");
}

export async function logout(): Promise<void> {
  (await cookies()).delete(COOKIE);
  redirect("/login");
}

export async function startRun(form: FormData): Promise<void> {
  const changeId = String(form.get("change_id") ?? "help-button");
  // Offline runs are open; a run that would call a live provider needs the reviewer token.
  const token = (await cookies()).get(COOKIE)?.value;
  const res = await fetch(`${API_URL}/gate/runs`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ change_id: changeId }),
    cache: "no-store",
  });
  if (res.status === 401) redirect(`/login?next=${encodeURIComponent("/gate")}`);
  if (!res.ok) redirect(`/gate?error=${res.status}`);
  const run = (await res.json()) as { run_id: string };
  redirect(`/gate/runs/${encodeURIComponent(run.run_id)}`);
}

export async function decide(form: FormData): Promise<void> {
  const back = String(form.get("back") ?? "/");
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) redirect(`/login?next=${encodeURIComponent(back)}`);
  const decision = String(form.get("decision"));
  const reason = String(form.get("reason") ?? "").trim();
  const res = await fetch(`${API_URL}/approvals`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify({
      run_id: String(form.get("run_id")),
      subject: String(form.get("subject")),
      subject_id: String(form.get("subject_id")),
      plan_sha256: String(form.get("plan_sha256")),
      decision,
      reason: reason || (decision === "rejected" ? "Rejected in dashboard review" : null),
    }),
    cache: "no-store",
  });
  const sep = back.includes("?") ? "&" : "?";
  redirect(`${back}${sep}approval=${res.ok ? "recorded" : String(res.status)}`);
}

export async function runRepair(form: FormData): Promise<void> {
  const runId = String(form.get("run_id"));
  const back = `/gate/runs/${encodeURIComponent(runId)}`;
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) redirect(`/login?next=${encodeURIComponent(back)}`);
  const res = await fetch(`${API_URL}/gate/runs/${encodeURIComponent(runId)}/repair`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  redirect(`${back}?repair=${res.ok ? "done" : String(res.status)}`);
}
