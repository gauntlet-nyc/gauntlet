import { cn } from "@/lib/utils";

/** Gauntlet mark: a shield split by a diagonal, base vs head. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden className={cn("size-7", className)}>
      <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" className="fill-foreground/[0.06] stroke-foreground/15" />
      <path
        d="M16 6.5 24 9.6v6.1c0 4.9-3.3 8.4-8 9.8-4.7-1.4-8-4.9-8-9.8V9.6l8-3.1Z"
        className="stroke-foreground"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M16 6.5v19" className="stroke-foreground/40" strokeWidth="1.2" />
      <path d="m12.4 15.6 2.4 2.4 4.8-4.9" className="stroke-foreground" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
