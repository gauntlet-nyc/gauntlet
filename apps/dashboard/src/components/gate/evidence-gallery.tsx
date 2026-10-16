"use client";

import { Maximize2 } from "lucide-react";
import { useState } from "react";

import { StatusPill } from "@/components/shared";
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

interface Selection {
  item: EvidenceItem;
  shot: EvidenceShot;
  index: number;
}

const PIXELATED = "[image-rendering:pixelated]";

/** One figure per attempt, its captured frames side by side; any frame opens a lightbox. */
export function EvidenceGallery({ items }: { items: EvidenceItem[] }) {
  const [selected, setSelected] = useState<Selection | null>(null);
  const attackIds = [...new Set(items.map((i) => i.attackId))];

  return (
    <>
      <div className="space-y-6">
        {attackIds.map((attackId) => (
          <div key={attackId}>
            <code className="text-muted-foreground mb-2.5 block truncate font-mono text-xs">{attackId}</code>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {items
                .filter((i) => i.attackId === attackId)
                .map((item) => {
                  const failed = item.outcome === "fail";
                  return (
                    <figure
                      key={item.key}
                      className={cn("bg-card m-0 overflow-hidden rounded-lg border", failed && "border-regression/30")}
                    >
                      <div className="bg-muted/40 flex items-center gap-1.5 border-b px-2.5 py-1.5" aria-hidden>
                        <span className="bg-muted-foreground/30 size-1.5 rounded-full" />
                        <span className="bg-muted-foreground/30 size-1.5 rounded-full" />
                        <span className="bg-muted-foreground/30 size-1.5 rounded-full" />
                        <span className="text-muted-foreground ml-1.5 font-mono text-[10px] tracking-wide uppercase">{item.revision}</span>
                        {item.viewport && <span className="text-muted-foreground/70 ml-auto font-mono text-[10px] tabular-nums">{item.viewport}</span>}
                      </div>
                      <div className="grid grid-cols-2 gap-px bg-border">
                        {item.shots.map((shot, index) => (
                          <button
                            key={shot.artifactId}
                            type="button"
                            onClick={() => setSelected({ item, shot, index })}
                            className="group bg-background relative block aspect-[3/4] overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                            aria-label={`Open ${item.revision} attempt ${item.attempt} frame ${index + 1}`}
                          >
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={shot.src}
                              alt={`${item.revision} attempt ${item.attempt}, frame ${index + 1}`}
                              className={cn("size-full object-cover opacity-90 transition-opacity group-hover:opacity-100", PIXELATED)}
                            />
                            <span className="bg-background/80 text-muted-foreground absolute bottom-1.5 left-1.5 rounded px-1 font-mono text-[10px] tabular-nums backdrop-blur">
                              {index + 1}/{item.shots.length}
                            </span>
                            <span className="bg-background/80 text-muted-foreground absolute right-1.5 bottom-1.5 flex size-6 items-center justify-center rounded-md border opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
                              <Maximize2 className="size-3" aria-hidden />
                            </span>
                          </button>
                        ))}
                      </div>
                      <figcaption className="flex items-center justify-between gap-2 border-t px-2.5 py-2 text-xs">
                        <span className="font-medium capitalize">
                          {item.revision} <span className="text-muted-foreground font-normal">#{item.attempt}</span>
                        </span>
                        <span className={cn("flex items-center gap-1.5", failed ? "text-regression" : item.outcome === "pass" ? "text-passed" : "text-inconclusive")}>
                          <span className={cn("size-1.5 rounded-full", failed ? "bg-regression" : item.outcome === "pass" ? "bg-passed" : "bg-inconclusive")} aria-hidden />
                          {item.outcome}
                        </span>
                      </figcaption>
                    </figure>
                  );
                })}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="sm:max-w-2xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2 capitalize">
                  {selected.item.revision} attempt {selected.item.attempt}
                  <span className="text-muted-foreground font-normal normal-case">· frame {selected.index + 1} of {selected.item.shots.length}</span>
                </DialogTitle>
                <DialogDescription className="font-mono text-xs">{selected.item.attackId}</DialogDescription>
              </DialogHeader>
              <div className="bg-background overflow-hidden rounded-lg border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={selected.shot.src} alt={`${selected.item.revision} attempt ${selected.item.attempt}`} className={cn("mx-auto max-h-[60vh] w-full object-contain", PIXELATED)} />
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <StatusPill value={selected.item.outcome} />
                  <span className="text-muted-foreground">{selected.item.observed}</span>
                </div>
                <p className="text-muted-foreground font-mono text-xs break-all">{selected.shot.artifactId}</p>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
