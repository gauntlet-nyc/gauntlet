import { isLive } from "@/components/sponsors/model";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SponsorStatus } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export function SponsorSummary({ sponsors }: { sponsors: SponsorStatus[] }) {
  const total = sponsors.length;
  const live = sponsors.filter(isLive).length;
  const configured = sponsors.filter((s) => s.configured).length;
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
      <p className="text-sm whitespace-nowrap tabular-nums">
        <span className="font-medium">
          {live} of {total} live
        </span>
        <span className="text-muted-foreground"> · {configured}/{total} configured</span>
      </p>
      <div className="flex flex-1 gap-1" role="list" aria-label="Per-sponsor live status">
        {sponsors.map((s) => (
          <Tooltip key={s.sponsor}>
            <TooltipTrigger asChild>
              <div
                role="listitem"
                aria-label={`${s.sponsor}: ${s.status}`}
                tabIndex={0}
                className={cn(
                  "focus-visible:ring-ring/50 h-1.5 flex-1 rounded-full outline-none focus-visible:ring-2",
                  isLive(s) ? "bg-passed" : s.configured ? "bg-foreground/40" : "bg-foreground/12",
                )}
              />
            </TooltipTrigger>
            <TooltipContent>{s.sponsor}</TooltipContent>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
