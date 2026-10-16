import { getCartwheelChange } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CartwheelGatePage() {
  let change;
  try {
    change = await getCartwheelChange();
  } catch (err) {
    return (
      <main>
        <h1>Change unavailable</h1>
        <p>Could not load the Cartwheel change request: {String(err)}</p>
      </main>
    );
  }
  return (
    <main>
      <h1>Gate run: {change.target_id}</h1>
      <p>{change.feature_intent}</p>
      <dl>
        <dt>Base SHA</dt>
        <dd>
          <code>{change.base_sha}</code>
        </dd>
        <dt>Head SHA</dt>
        <dd>
          <code>{change.head_sha}</code>
        </dd>
        <dt>Fixture</dt>
        <dd>{change.fixture_id}</dd>
      </dl>
      <h2>Findings</h2>
      <p>
        <strong>not_tested</strong>: no worker has executed this change yet, so there are no
        observations, screenshots or traces to show.
      </p>
    </main>
  );
}
