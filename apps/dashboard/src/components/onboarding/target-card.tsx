import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortSha, type OnboardingView } from "@/lib/gauntlet";

type Target = OnboardingView["targets"][number];

function Hash({ value }: { value: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <code tabIndex={0} className="text-foreground/85 cursor-default font-mono outline-none">
          {shortSha(value)}
        </code>
      </TooltipTrigger>
      <TooltipContent className="font-mono">{value}</TooltipContent>
    </Tooltip>
  );
}

export function TargetCard({ target }: { target: Target }) {
  const identities = target.identities.map((i) => `${i.id} (${i.role})`).join(", ");
  return (
    <article className="bg-card w-full rounded-xl border px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-medium tracking-tight">{target.fixture_id}</h3>
        <span className="text-muted-foreground text-xs">{target.synthetic_only ? "synthetic only" : "real target"}</span>
      </div>
      <p className="text-muted-foreground mt-0.5 text-xs">{target.target_id}</p>
      <dl className="mt-4 grid grid-cols-[88px_1fr] gap-x-4 gap-y-1.5 text-[13px]">
        <dt className="text-muted-foreground">Commits</dt>
        <dd className="text-xs leading-5">
          <Hash value={target.base_sha} />
          <span className="text-muted-foreground"> → </span>
          <Hash value={target.head_sha} />
        </dd>
        <dt className="text-muted-foreground">Routes</dt>
        <dd className="truncate font-mono text-xs leading-5">{target.routes.map((r) => r.path).join("  ")}</dd>
        <dt className="text-muted-foreground">Identities</dt>
        <dd>
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="cursor-default underline decoration-dotted underline-offset-4 outline-none">
                {target.identities.length} synthetic
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{identities}</TooltipContent>
          </Tooltip>
        </dd>
        <dt className="text-muted-foreground">GitHub</dt>
        <dd className={target.github_repository ? "font-mono text-xs leading-5" : "text-muted-foreground"}>
          {target.github_repository ?? "not bound"}
        </dd>
      </dl>
    </article>
  );
}
