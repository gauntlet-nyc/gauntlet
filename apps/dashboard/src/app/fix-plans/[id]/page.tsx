import { getFixPlan } from "@/lib/api";

import { decide } from "./actions";

export const dynamic = "force-dynamic";

export default async function FixPlanPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ msg?: string }>;
}) {
  const { id } = await params;
  const { msg } = await searchParams;
  let view;
  try {
    view = await getFixPlan(id);
  } catch (err) {
    return (
      <main>
        <h1>Fix plan unavailable</h1>
        <p>{String(err)}</p>
      </main>
    );
  }
  const plan = view.fix_plan;
  return (
    <main>
      <h1>Fix plan {plan.fix_plan_id}</h1>
      <p>
        <em>{view.label}</em>
      </p>
      {msg && <p role="status">{msg}</p>}
      <p>{plan.rationale}</p>
      <p>
        Plan hash: <code>{view.plan_sha256}</code>
      </p>
      <h2>Allowed paths</h2>
      <ul>
        {plan.allowed_paths.map((p) => (
          <li key={p}>
            <code>{p}</code>
          </li>
        ))}
      </ul>
      <h2>Diff</h2>
      <pre style={{ overflowX: "auto", background: "#f6f6f6", padding: 12 }}>{plan.unified_diff}</pre>
      <h2>Test plan</h2>
      <ul>
        {plan.test_plan.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <h2>Decision</h2>
      <p>The approval binds to the exact hash above and expires. It does not merge or deploy.</p>
      <form action={decide}>
        <input type="hidden" name="subject_id" value={plan.fix_plan_id} />
        <input type="hidden" name="plan_sha256" value={view.plan_sha256} />
        <label>
          Reason (required to reject){" "}
          <input name="reason" type="text" maxLength={500} />
        </label>{" "}
        <button type="submit" name="decision" value="approved">
          Approve
        </button>{" "}
        <button type="submit" name="decision" value="rejected">
          Reject
        </button>
      </form>
      <h2>Recorded decisions</h2>
      {view.approvals.length === 0 ? (
        <p>None yet.</p>
      ) : (
        <ul>
          {view.approvals.map((a) => (
            <li key={a.approval_id}>
              {a.decision} by {a.reviewer_id} ({a.approval_id})
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
