import { getFakeRun } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function FakeRunPage() {
  let run;
  try {
    run = await getFakeRun();
  } catch (err) {
    return (
      <main>
        <h1>Fake run unavailable</h1>
        <p>Could not load /runs/fake from the control API: {String(err)}</p>
      </main>
    );
  }
  return (
    <main>
      <h1>{run.label}</h1>
      <p>
        Run {run.run_id}, attack {run.plan.attack_id}
      </p>
      <p>{run.plan.hypothesis}</p>
      <h2>Planned steps</h2>
      <ol>
        {run.plan.steps.map((s, i) => (
          <li key={i}>{s.action}</li>
        ))}
      </ol>
      <h2>Events</h2>
      <ul>
        {run.events.map((e) => (
          <li key={e.event_id}>
            #{e.sequence} {e.event_type} by {e.actor}
          </li>
        ))}
      </ul>
    </main>
  );
}
