"use client";

import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

/** "View patch" disclosure; the diff stays one click away instead of filling the page. */
export function PatchDisclosure({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="text-muted-foreground hover:text-foreground flex max-w-full min-w-0 items-center gap-1.5 text-sm transition-colors">
        <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} aria-hidden />
        <span className="whitespace-nowrap">{open ? "Hide patch" : "View patch"}</span>
        <span className="text-muted-foreground/70 hidden min-w-0 truncate sm:inline">{summary}</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}
