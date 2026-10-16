"use client";

import { ChevronRight, FileCode2 } from "lucide-react";
import { useState } from "react";

import { DiffView } from "@/components/shared";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export interface DiffFile {
  path: string;
  diff: string;
  added: number;
  removed: number;
}

function FileRow({ file, defaultOpen }: { file: DiffFile; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="hover:bg-muted/40 flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors">
        <ChevronRight className={cn("text-muted-foreground size-4 shrink-0 transition-transform", open && "rotate-90")} aria-hidden />
        <FileCode2 className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{file.path}</span>
        <span className="font-mono text-xs tabular-nums">
          <span className="text-passed">+{file.added}</span> <span className="text-regression">−{file.removed}</span>
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4">
        <DiffView diff={file.diff} />
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Changed files as a compact list; each expands to its diff. */
export function DiffFiles({ files }: { files: DiffFile[] }) {
  return (
    <div className="divide-y rounded-xl border">
      {files.map((f) => (
        <FileRow key={f.path} file={f} defaultOpen={files.length === 1} />
      ))}
    </div>
  );
}
