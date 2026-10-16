import { cookies } from "next/headers";

import { login, logout } from "@/app/actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const query = await searchParams;
  const signedIn = Boolean((await cookies()).get("gauntlet_reviewer_token"));
  return (
    <main>
      <h1>Reviewer login (dev-grade)</h1>
      <p>
        Paste a reviewer token configured on the API in <code>GAUNTLET_REVIEWER_TOKENS</code>. The token is kept in an
        httpOnly cookie on this dashboard server and is never shown again. Demo use only.
      </p>
      {query.error === "short" && <p role="alert">Token must be at least 16 characters.</p>}
      {query.ok && <p role="status">Token stored. The API checks it on every approval.</p>}
      {query.next && <p role="status">Log in to record that decision, then go back.</p>}
      <form action={login} style={{ display: "flex", gap: 8 }}>
        <input name="token" type="password" autoComplete="off" placeholder="reviewer token" style={{ flex: 1 }} />
        <button type="submit">Store token</button>
      </form>
      {signedIn && (
        <form action={logout} style={{ marginTop: 12 }}>
          <button type="submit">Log out</button>
        </form>
      )}
    </main>
  );
}
