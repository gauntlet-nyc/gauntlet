"use client";

import { useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface EvidenceShot {
  artifactId: string;
  src: string;
}

export interface EvidenceItem {
  key: string;
  attackId: string;
  revision: "base" | "head";
  attempt: number;
  outcome: string;
  observed: string;
  viewport: string | null;
  shots: EvidenceShot[];
}

function outcomeText(outcome: string): string {
  return outcome === "fail" ? "text-regression" : outcome === "pass" ? "text-passed" : "text-inconclusive";
}

/** A single strip: one figure per attempt showing its final frame; click for every frame of that attempt. */
export function EvidenceGallery({ items }: { items: EvidenceItem[] }) {
  const [selected, setSelected] = useState<EvidenceItem | null>(null);

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {items.map((item) => {
          const shot = item.shots[item.shots.length - 1];
          if (!shot) return null;
          return (
            <figure key={item.key} className="m-0 w-60 shrink-0">
              <button
                type="button"
                onClick={() => setSelected(item)}
                className={cn(
                  "bg-muted block aspect-[3/2] w-full overflow-hidden rounded-md border transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  item.outcome === "fail" && "border-regression/40",
                )}
                aria-label={`Open ${item.revision} attempt ${item.attempt}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={shot.src} alt={`${item.revision} attempt ${item.attempt}`} className="size-full object-cover object-bottom" />
              </button>
              <figcaption className="mt-1.5 flex items-center justify-between text-xs">
                <span className="capitalize">
                  {item.revision} <span className="text-muted-foreground">#{item.attempt}</span>
                </span>
                <span className={outcomeText(item.outcome)}>{item.outcome}</span>
              </figcaption>
              {item.viewport && <div className="text-muted-foreground font-mono text-[10px] tabular-nums">{item.viewport}</div>}
            </figure>
          );
        })}
      </div>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="sm:max-w-2xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="capitalize">
                  {selected.revision} attempt {selected.attempt} <span className={cn("font-normal normal-case", outcomeText(selected.outcome))}>· {selected.outcome}</span>
                </DialogTitle>
                <DialogDescription>{selected.observed}</DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-3">
                {selected.shots.map((shot, i) => (
                  <div key={shot.artifactId}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={shot.src} alt={`Frame ${i + 1}`} className="bg-muted aspect-[3/4] w-full rounded-md border object-contain" />
                    <p className="text-muted-foreground mt-1.5 truncate font-mono text-[11px]" title={shot.artifactId}>
                      Frame {i + 1} · {shot.artifactId}
                    </p>
                  </div>
                ))}
              </div>
              <p className="text-muted-foreground font-mono text-xs">{selected.attackId}</p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
