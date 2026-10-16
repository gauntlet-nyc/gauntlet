import { CheckCircle2, ChevronRight, FlaskConical } from "lucide-react";
import type { ReactNode } from "react";

import { CopyCommand } from "@/components/sponsors/copy-command";
import { isLive, isShellCommand, POWERS } from "@/components/sponsors/model";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { SponsorStatus } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

function StatusChip({ sponsor }: { sponsor: SponsorStatus }) {
  const live = isLive(sponsor);
  const Icon = live ? CheckCircle2 : FlaskConical;
  return (
    <span
      className={cn(
        "inline-flex h-6 w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        live ? "border-passed/30 bg-passed/10 text-passed" : "border-inconclusive/25 bg-inconclusive/[0.06] text-inconclusive",
      )}
    >
      <Icon className="size-3" aria-hidden />
      {sponsor.status}
    </span>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[96px_1fr] sm:gap-4">
      <dt className="text-muted-foreground text-xs leading-6">{label}</dt>
      <dd className="min-w-0 text-[13px] leading-6">{children}</dd>
    </div>
  );
}

function SponsorRow({ sponsor }: { sponsor: SponsorStatus }) {
  const missing = sponsor.missing_env.length;
  return (
    <Collapsible asChild>
      <li className="group/row">
        <CollapsibleTrigger className="hover:bg-accent/40 focus-visible:bg-accent/40 grid w-full grid-cols-[16px_1fr_auto] items-center gap-x-3 gap-y-2 px-4 py-3 text-left transition-colors outline-none md:grid-cols-[16px_minmax(0,1.3fr)_minmax(0,1fr)_224px_104px]">
          <ChevronRight
            className="text-muted-foreground size-4 transition-transform group-data-[state=open]/row:rotate-90"
            aria-hidden
          />
          <span className="truncate text-sm font-medium">{sponsor.sponsor}</span>
          <span className="text-muted-foreground hidden truncate text-sm md:block">{POWERS[sponsor.sponsor] ?? ""}</span>
          <span className="col-start-2 md:col-start-auto">
            <StatusChip sponsor={sponsor} />
          </span>
          <span className="text-muted-foreground col-start-3 row-start-1 text-right text-xs tabular-nums md:col-start-auto md:row-start-auto">
            {sponsor.configured ? "keys set" : `${missing} key${missing === 1 ? "" : "s"} missing`}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down overflow-hidden">
          <dl className="space-y-2 pt-1 pr-4 pb-5 pl-11">
            {!sponsor.configured && (
              <Detail label="Missing keys">
                <span className="flex flex-wrap gap-1.5 pt-0.5">
                  {sponsor.missing_env.map((env) => (
                    <code key={env} className="bg-muted/60 rounded px-1.5 py-0.5 font-mono text-[11px]">
                      {env}
                    </code>
                  ))}
                </span>
              </Detail>
            )}
            <Detail label="Produces">{sponsor.produces.join(", ")}</Detail>
            {sponsor.notes && (
              <Detail label="Notes">
                <span className="text-muted-foreground">{sponsor.notes}</span>
              </Detail>
            )}
            <Detail label="Prove it live">
              {isShellCommand(sponsor.live_command) ? (
                <CopyCommand command={sponsor.live_command} className="max-w-3xl" />
              ) : (
                <span className="text-muted-foreground">{sponsor.live_command}</span>
              )}
            </Detail>
          </dl>
        </CollapsibleContent>
      </li>
    </Collapsible>
  );
}

export function SponsorList({ sponsors }: { sponsors: SponsorStatus[] }) {
  return (
    <div className="rounded-xl border">
      <div className="text-muted-foreground hidden grid-cols-[16px_minmax(0,1.3fr)_minmax(0,1fr)_224px_104px] gap-x-3 border-b px-4 py-2 text-xs md:grid">
        <span />
        <span>Sponsor</span>
        <span>Powers</span>
        <span>Status</span>
        <span className="text-right">Keys</span>
      </div>
      <ul className="divide-y">
        {sponsors.map((s) => (
          <SponsorRow key={s.sponsor} sponsor={s} />
        ))}
      </ul>
    </div>
  );
}
