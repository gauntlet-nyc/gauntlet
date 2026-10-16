import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { MemoryView } from "@/lib/gauntlet";
import { shortSha } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export type MemoryFact = MemoryView["facts"][number];

const SHORT_SUFFIX = 12;

/** Readable short form of a long fact id; the full id stays in the DOM and in the tooltip. */
function shortFactId(id: string): string {
  return id.length > 28 ? `fact-…${id.slice(-SHORT_SUFFIX)}` : id;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-16 shrink-0 opacity-60">{label}</dt>
      <dd className="min-w-0 font-mono break-all">{children}</dd>
    </div>
  );
}

export function FactChip({ id, fact, variant }: { id: string; fact?: MemoryFact; variant: "used" | "written" }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex h-6 max-w-full items-center gap-1.5 rounded-md border px-2 font-mono text-[11px] outline-none",
            "focus-visible:ring-ring/50 focus-visible:ring-2",
            variant === "used" ? "border-info/30 bg-info/10 text-info" : "bg-muted/60 text-foreground",
          )}
        >
          <span className={cn("size-1.5 shrink-0 rounded-full", variant === "used" ? "bg-info" : "bg-foreground/60")} aria-hidden />
          <span className="sr-only">{id}</span>
          <span aria-hidden>{shortFactId(id)}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-sm px-3 py-2.5 text-left">
        <div className="font-mono text-[11px] break-all">{id}</div>
        {fact ? (
          <>
            <p className="mt-1.5 text-xs leading-snug">{fact.summary}</p>
            <dl className="mt-2 space-y-0.5 text-[11px]">
              <Row label="kind">{fact.kind}</Row>
              <Row label="trust">
                {fact.verification} / {fact.trust}
              </Row>
              {fact.source.finding_id && <Row label="finding">{fact.source.finding_id}</Row>}
              {fact.source.oracle_id && <Row label="oracle">{fact.source.oracle_id}</Row>}
              {fact.source.commit && <Row label="commit">{shortSha(fact.source.commit)}</Row>}
              <Row label="known">{fact.known_at.slice(0, 19).replace("T", " ")}Z</Row>
            </dl>
          </>
        ) : (
          <p className="mt-1.5 text-xs opacity-70">Fact not in the current memory view.</p>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
