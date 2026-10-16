import { ErrorPanel } from "@/components/ui";
import { api } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function SponsorsPage() {
  let sponsors;
  try {
    sponsors = await api.sponsors();
  } catch (err) {
    return <ErrorPanel what="Sponsor proof" error={err} />;
  }
  return (
    <main>
      <h1>Sponsor proof</h1>
      <p>
        Which provider produces each artifact, and whether it has run live. Status changes to &ldquo;live verified&rdquo;
        only after a recorded live run in <code>docs/SDK_VALIDATION.md</code>; setting keys alone never changes it.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr><th align="left">Sponsor</th><th align="left">Produces</th><th align="left">Keys</th><th align="left">Status</th></tr>
        </thead>
        <tbody>
          {sponsors.map((s) => (
            <tr key={s.sponsor} style={{ borderTop: "1px solid #eee", verticalAlign: "top" }}>
              <td>
                <strong>{s.sponsor}</strong>
                <br />
                <code style={{ fontSize: 11 }}>{s.adapter}</code>
              </td>
              <td>{s.produces.join(", ")}</td>
              <td>{s.configured ? "set" : `missing: ${s.missing_env.join(", ")}`}</td>
              <td>
                <strong style={{ color: s.status === "live verified" ? "#03543f" : "#9b1c1c" }}>{s.status}</strong>
                <br />
                <small>{s.notes}</small>
                <br />
                <small>
                  Prove live: <code>{s.live_command}</code>
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
