import { ArrowRight } from "lucide-react";
import Link from "next/link";

/** Text wordmarks only: no borrowed logos. */
const WORDMARKS: readonly string[] = ["Daytona", "Anchor", "Azure OpenAI", "Arize", "SurrealDB", "ElevenLabs", "GitHub"];

export function SponsorRow() {
  return (
    <div className="flex flex-col gap-4 border-t pt-6 md:flex-row md:items-center md:justify-between">
      <ul className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <li className="text-muted-foreground text-xs">Built with</li>
        {WORDMARKS.map((name) => (
          <li key={name} className="text-foreground/55 text-sm font-semibold tracking-tight">
            {name}
          </li>
        ))}
      </ul>
      <Link
        href="/sponsors"
        className="text-muted-foreground hover:text-foreground group inline-flex shrink-0 items-center gap-1.5 text-sm transition-colors"
      >
        Sponsor proof
        <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
      </Link>
    </div>
  );
}
