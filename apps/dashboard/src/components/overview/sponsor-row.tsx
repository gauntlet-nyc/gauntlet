import { ArrowRight } from "lucide-react";
import Link from "next/link";

/** Text wordmarks only: no borrowed logos. */
const WORDMARKS: readonly { name: string; className: string }[] = [
  { name: "Daytona", className: "font-semibold tracking-tight" },
  { name: "Anchor", className: "font-semibold tracking-[-0.02em]" },
  { name: "Azure OpenAI", className: "font-medium tracking-tight" },
  { name: "Arize", className: "font-semibold" },
  { name: "SurrealDB", className: "font-semibold tracking-tight" },
  { name: "ElevenLabs", className: "font-medium tracking-tight" },
  { name: "GitHub", className: "font-semibold tracking-tight" },
];

export function SponsorRow() {
  return (
    <div className="flex flex-col gap-5 rounded-xl border px-5 py-5 md:flex-row md:items-center md:justify-between md:px-6">
      <div className="text-muted-foreground shrink-0 text-xs font-medium tracking-wide uppercase">Built with</div>
      <ul className="flex flex-wrap items-center gap-x-7 gap-y-3">
        {WORDMARKS.map((w) => (
          <li key={w.name} className={`text-foreground/55 text-[15px] ${w.className}`}>
            {w.name}
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
