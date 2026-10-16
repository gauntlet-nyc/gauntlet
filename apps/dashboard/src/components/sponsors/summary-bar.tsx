import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isLive } from "@/components/sponsors/sponsor-card";
import type { SponsorStatus } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

function Stat({ label, value, total }: { label: string; value: number; total: number }) {
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">
        {value}
        <span className="text-muted-foreground text-base font-normal"> / {total}</span>
      </div>
    </div>
  );
}

export function SponsorSummary({ sponsors }: { sponsors: SponsorStatus[] }) {
  const total = sponsors.length;
  const live = sponsors.filter(isLive).length;
  const configured = sponsors.filter((s) => s.configured).length;
  const offline = total - live;
  return (
    <div className="bg-card rounded-xl border">
      <div className="grid gap-6 px-5 py-5 sm:grid-cols-3 md:px-6">
        <div>
          <div className="text-muted-foreground text-xs">Running live</div>
          <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">
            {live} of {total} live
          </div>
        </div>
        <Stat label="Keys configured" value={configured} total={total} />
        <Stat label="Offline-tested only" value={offline} total={total} />
      </div>
      <div className="border-t px-5 py-4 md:px-6">
        <div className="flex gap-1" role="list" aria-label="Per-sponsor live status">
          {sponsors.map((s) => (
            <Tooltip key={s.sponsor}>
              <TooltipTrigger asChild>
                <div
                  role="listitem"
                  aria-label={`${s.sponsor}: ${s.status}`}
                  tabIndex={0}
                  className={cn(
                    "h-1.5 flex-1 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                    isLive(s) ? "bg-passed" : s.configured ? "bg-foreground/40" : "bg-foreground/12",
                  )}
                />
              </TooltipTrigger>
              <TooltipContent>{s.sponsor}</TooltipContent>
            </Tooltip>
          ))}
        </div>
        <div className="text-muted-foreground mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs">
          <span className="inline-flex items-center gap-1.5">
            <span className="bg-passed size-1.5 rounded-full" aria-hidden />
            live run recorded
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="bg-foreground/40 size-1.5 rounded-full" aria-hidden />
            keys set, not yet run live
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="bg-foreground/12 size-1.5 rounded-full" aria-hidden />
            offline only
          </span>
        </div>
      </div>
    </div>
  );
}
