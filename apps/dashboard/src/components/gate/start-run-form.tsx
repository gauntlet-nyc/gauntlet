"use client";

import { ChevronsUpDown, Play } from "lucide-react";
import { useState } from "react";

import { CHANGE_COPY } from "@/components/gate/copy";
import { PendingButton } from "@/components/gate/pending-button";
import { shortSha, type ChangeOption } from "@/lib/gauntlet";

const DEFAULT_CHANGE_ID = "help-button";

/**
 * Inline run launcher. The native `<select name="change_id">` is the real control (it is what the form submits);
 * one muted line under it describes the selected change.
 */
export function StartRunForm({ action, changes }: { action: (form: FormData) => Promise<void>; changes: ChangeOption[] }) {
  const initial = changes.some((c) => c.change_id === DEFAULT_CHANGE_ID) ? DEFAULT_CHANGE_ID : (changes[0]?.change_id ?? "");
  const [selected, setSelected] = useState(initial);
  const change = changes.find((c) => c.change_id === selected);
  const copy = change ? CHANGE_COPY[change.change_id] : undefined;

  return (
    <form action={action}>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative min-w-0 flex-1">
          <label htmlFor="change_id" className="sr-only">
            Pull request to test
          </label>
          <select
            id="change_id"
            name="change_id"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="border-input bg-card hover:border-foreground/20 focus-visible:border-ring focus-visible:ring-ring/40 h-9 w-full cursor-pointer appearance-none truncate rounded-md border pr-9 pl-3 text-sm transition-colors outline-none focus-visible:ring-[3px]"
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
        <PendingButton icon={<Play aria-hidden />} pendingLabel="Planning and running…" className="h-9">
          Start Gate run
        </PendingButton>
      </div>
      {change && (
        <p className="text-muted-foreground mt-2 truncate text-xs">
          {copy ? `${copy.kind}: ${copy.summary}` : change.feature_intent}
        </p>
      )}
    </form>
  );
}
