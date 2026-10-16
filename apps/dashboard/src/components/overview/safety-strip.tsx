import { Fingerprint, Lightbulb, Scale, UserCheck, type LucideIcon } from "lucide-react";

const PRINCIPLES: readonly { icon: LucideIcon; title: string; body: string }[] = [
  { icon: Lightbulb, title: "The model only proposes", body: "It never decides a verdict." },
  { icon: Fingerprint, title: "Plans are frozen", body: "Approvals bind to a hash." },
  { icon: Scale, title: "Oracles decide", body: "Evidence, not the model." },
  { icon: UserCheck, title: "Humans approve", body: "Nothing auto-merges." },
];

export function SafetyStrip() {
  return (
    <ul className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
      {PRINCIPLES.map((p) => (
        <li key={p.title} className="flex gap-3">
          <p.icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <div className="text-sm font-medium tracking-tight">{p.title}</div>
            <div className="text-muted-foreground mt-0.5 text-[13px]">{p.body}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
