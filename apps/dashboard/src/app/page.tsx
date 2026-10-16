import Link from "next/link";

export default function Overview() {
  return (
    <main>
      <h1>Gauntlet</h1>
      <p>Change-aware adversarial release testing, and an audit of what already shipped.</p>
      <ul>
        <li>
          <Link href="/gate">Gate</Link>: read a PR diff, plan attacks, run them on base and head, let independent oracles
          decide: regression introduced, pre-existing, passed or inconclusive.
        </li>
        <li>
          <Link href="/recall">Recall</Link>: audit past agent decisions from recorded history, then replay exposed ones with
          the suspect source removed: tainted, cleared or inconclusive.
        </li>
        <li>
          <Link href="/sponsors">Sponsor proof</Link>: which provider produced each artifact, and whether it ran live.
        </li>
      </ul>
      <p>
        Pages show an <strong>OFFLINE / live NOT RUN</strong> badge whenever data comes from recordings, fixtures or
        fakes. The model only proposes; oracles and humans decide. Nothing auto-merges or auto-remediates.
      </p>
    </main>
  );
}
