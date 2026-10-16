import { Fingerprint, Lightbulb, Scale, UserCheck, type LucideIcon } from "lucide-react";

interface Principle {
  icon: LucideIcon;
  title: string;
  body: string;
}

const PRINCIPLES: readonly Principle[] = [
  {
    icon: Lightbulb,
    title: "The model only proposes",
    body: "The planner suggests attacks. It never runs arbitrary shell commands and never decides a verdict.",
  },
  {
    icon: Fingerprint,
    title: "Frozen, hash-bound plans",
    body: "Each plan is hashed before it runs. Approvals bind to that exact hash, so any edit voids them.",
  },
  {
    icon: Scale,
    title: "Independent oracles",
    body: "Deterministic checks compare base and head. The verdict comes from evidence, not from the model.",
  },
  {
    icon: UserCheck,
    title: "Humans approve",
    body: "Fix plans and remediations wait for a reviewer. Nothing auto-merges, deploys or refunds.",
  },
];

export function SafetyStrip() {
  return (
    <div className="grid overflow-hidden rounded-xl border sm:grid-cols-2 lg:grid-cols-4">
      {PRINCIPLES.map((p, i) => (
        <div
          key={p.title}
          className={[
            "bg-card/40 p-5",
            i > 0 ? "border-t sm:border-t-0" : "",
            i % 2 === 1 ? "sm:border-l" : "",
            i >= 2 ? "sm:border-t lg:border-t-0" : "",
            i > 0 ? "lg:border-l" : "",
          ].join(" ")}
        >
          <div className="flex items-center gap-2.5">
            <span className="text-muted-foreground font-mono text-[11px] tabular-nums">0{i + 1}</span>
            <p.icon className="text-muted-foreground size-4" aria-hidden />
          </div>
          <h3 className="mt-3 text-sm font-medium tracking-tight">{p.title}</h3>
          <p className="text-muted-foreground mt-1.5 text-[13px] leading-relaxed">{p.body}</p>
        </div>
      ))}
    </div>
  );
}
