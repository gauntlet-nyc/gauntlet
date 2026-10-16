import { getOfflineGate } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OfflineGatePage() {
  let gate;
  try {
    gate = await getOfflineGate();
  } catch (err) {
    return (
      <main>
        <h1>Offline gate unavailable</h1>
        <p>{String(err)}</p>
      </main>
    );
  }
  const labels = ["head attempt 1", "head attempt 2", "base attempt"];
  return (
    <main>
      <h1>{gate.label}</h1>
      <p>
        Verdict: <strong>{gate.status}</strong> (attribution: {gate.attribution}), mode{" "}
        {gate.execution_mode}
      </p>
      <h2>Oracle outcomes</h2>
      <ul>
        {gate.oracle_outcomes.map((o, i) => (
          <li key={i}>
            {labels[i] ?? `attempt ${i + 1}`}: {o}
          </li>
        ))}
      </ul>
      <h2>Events</h2>
      <ul>
        {gate.events.map((e) => (
          <li key={e.event_id}>
            #{e.sequence} {e.event_type}
          </li>
        ))}
      </ul>
    </main>
  );
}
