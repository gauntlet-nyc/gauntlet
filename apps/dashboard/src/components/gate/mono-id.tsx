import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** A long id or hash, truncated to `chars`, with the full value in a tooltip. */
export function MonoId({
  value,
  chars = 7,
  ellipsis = true,
  className,
}: {
  value: string;
  chars?: number;
  ellipsis?: boolean;
  className?: string;
}) {
  const short = value.length > chars ? `${value.slice(0, chars)}${ellipsis ? "…" : ""}` : value;
  if (short === value) return <code className={cn("font-mono text-[0.92em]", className)}>{value}</code>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <code tabIndex={0} className={cn("cursor-help font-mono text-[0.92em] underline decoration-dotted decoration-1 underline-offset-4 decoration-muted-foreground/40", className)}>
          {short}
        </code>
      </TooltipTrigger>
      <TooltipContent className="max-w-none font-mono text-xs">{value}</TooltipContent>
    </Tooltip>
  );
}
