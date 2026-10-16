"use client";

import { ChevronsUpDown, GitCompareArrows, Play } from "lucide-react";
import { useState } from "react";

import { CHANGE_COPY } from "@/components/gate/copy";
import { PendingButton } from "@/components/gate/pending-button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { shortSha, type ChangeOption } from "@/lib/gauntlet";

const DEFAULT_CHANGE_ID = "help-button";

/**
 * The run launcher. The native `<select name="change_id">` is the real control (it is what the form submits);
 * the panel under it previews the selected change.
 */
export function StartRunForm({ action, changes }: { action: (form: FormData) => Promise<void>; changes: ChangeOption[] }) {
  const initial = changes.some((c) => c.change_id === DEFAULT_CHANGE_ID) ? DEFAULT_CHANGE_ID : (changes[0]?.change_id ?? "");
  const [selected, setSelected] = useState(initial);
  const change = changes.find((c) => c.change_id === selected);
  const copy = change ? CHANGE_COPY[change.change_id] : undefined;

  return (
    <form action={action} className="bg-card overflow-hidden rounded-xl border">
      <div className="grid gap-6 p-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end md:p-6">
        <div className="min-w-0">
          <Label htmlFor="change_id" className="text-muted-foreground mb-2 text-xs font-medium">
            Pull request to test
          </Label>
          <div className="relative">
            <select
              id="change_id"
              name="change_id"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="border-input bg-background hover:border-foreground/20 focus-visible:border-ring focus-visible:ring-ring/40 h-10 w-full cursor-pointer appearance-none truncate rounded-md border pr-10 pl-3 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]"
            >
              {changes.map((c) => (
                <option key={c.change_id} value={c.change_id}>
                  {c.feature_intent} ({shortSha(c.base_sha)}..{shortSha(c.head_sha)})
                  {c.offline_recording_available ? " — offline recording" : " — needs live run"}
                </option>
              ))}
            </select>
            <ChevronsUpDown className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2" aria-hidden />
          </div>
        </div>
        <PendingButton icon={<Play aria-hidden />} pendingLabel="Planning and running…" className="h-10 px-5">
          Start Gate run
        </PendingButton>
      </div>
      {change && (
        <div className="bg-muted/20 flex flex-col gap-3 border-t px-5 py-4 md:flex-row md:items-center md:justify-between md:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {copy && (
                <Badge variant="outline" className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
                  {copy.kind}
                </Badge>
              )}
              <code className="text-muted-foreground font-mono text-xs">{change.change_id}</code>
            </div>
            <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">{copy?.summary ?? change.feature_intent}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-3 text-xs">
            <span className="text-muted-foreground flex items-center gap-1.5 font-mono">
              <GitCompareArrows className="size-3.5" aria-hidden />
              {shortSha(change.base_sha)}
              <span className="text-muted-foreground/50">..</span>
              <span className="text-foreground">{shortSha(change.head_sha)}</span>
            </span>
            {change.offline_recording_available ? (
              <Badge variant="outline" className="border-inconclusive/30 bg-inconclusive/10 text-inconclusive h-5 px-2 text-[11px]">
                Offline recording
              </Badge>
            ) : (
              <Badge variant="outline" className="h-5 px-2 text-[11px]">
                Needs live run
              </Badge>
            )}
          </div>
        </div>
      )}
    </form>
  );
}
