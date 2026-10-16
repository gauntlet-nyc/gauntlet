import { ErrorPanel, Section } from "@/components/shared";
import { api, shortSha } from "@/lib/gauntlet";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  let view;
  try {
    view = await api.onboarding();
  } catch (err) {
    return <ErrorPanel what="Onboarding" error={err} />;
  }
  return (
    <main>
      <h1>Target onboarding</h1>
      <p>
        Targets come only from committed, synthetic manifests. This page shows what is registered and what an operator
        still has to configure. It changes nothing.
      </p>
      <Section title="Steps">
        <ol>
          {view.steps.map((s) => (
            <li key={s.step} style={{ marginBottom: 6 }}>
              <span aria-label={s.done ? "done" : "to do"}>{s.done ? "✅" : "⬜"}</span> <strong>{s.step}</strong>
              <br />
              <small>{s.detail}</small>
            </li>
          ))}
        </ol>
      </Section>
      <Section title="Registered targets">
        {view.targets.map((t) => (
          <div key={t.fixture_id} style={{ border: "1px solid #ddd", borderRadius: 4, padding: "8px 12px", margin: "8px 0" }}>
            <strong>{t.target_id}</strong> / <code>{t.fixture_id}</code> {t.synthetic_only && "· synthetic only"}
            <p style={{ margin: "4px 0", fontSize: 13 }}>
              <code>{shortSha(t.base_sha)}</code>..<code>{shortSha(t.head_sha)}</code> · checksum <code>{t.fixture_checksum_sha256.slice(0, 12)}…</code> · GitHub repo:{" "}
              {t.github_repository ?? "not bound"}
            </p>
            <small>
              Routes: {t.routes.map((r) => r.path + (r.primary_action ? ` (${r.primary_action})` : "")).join(", ")}
              <br />
              Synthetic identities: {t.identities.map((i) => `${i.id} [${i.role}]`).join(", ")}
            </small>
          </div>
        ))}
      </Section>
    </main>
  );
}
