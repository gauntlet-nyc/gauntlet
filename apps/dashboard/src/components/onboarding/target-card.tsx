import { FileLock2, GitBranch, FolderGit2, Route, Users } from "lucide-react";
import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortSha, type OnboardingView } from "@/lib/gauntlet";

type Target = OnboardingView["targets"][number];

const CHECKSUM_PREVIEW = 12;

function Hash({ value, length }: { value: string; length?: number }) {
  const shown = length ? `${value.slice(0, length)}…` : shortSha(value);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <code tabIndex={0} className="text-foreground/85 cursor-default font-mono text-xs outline-none">
          {shown}
        </code>
      </TooltipTrigger>
      <TooltipContent className="font-mono">{value}</TooltipContent>
    </Tooltip>
  );
}

function Row({ icon: Icon, label, children }: { icon: typeof Route; label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[20px_1fr] gap-x-2 gap-y-1 sm:grid-cols-[20px_96px_1fr]">
      <Icon className="text-muted-foreground mt-0.5 size-3.5" aria-hidden />
      <dt className="text-muted-foreground text-xs leading-5">{label}</dt>
      <dd className="col-start-2 min-w-0 text-xs leading-5 sm:col-start-3">{children}</dd>
    </div>
  );
}

export function TargetCard({ target }: { target: Target }) {
  return (
    <article className="bg-card flex w-full flex-col rounded-xl border">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b px-5 py-4">
        <div className="min-w-0">
          <div className="text-muted-foreground text-xs">{target.target_id}</div>
          <h3 className="mt-0.5 font-mono text-[15px] font-medium tracking-tight">{target.fixture_id}</h3>
        </div>
        {target.synthetic_only && (
          <span className="text-muted-foreground inline-flex h-6 items-center rounded-full border px-2.5 text-xs">
            synthetic only
          </span>
        )}
      </header>
      <dl className="space-y-3 px-5 py-4">
        <Row icon={GitBranch} label="Commits">
          <span className="inline-flex items-center gap-1.5">
            <Hash value={target.base_sha} />
            <span className="text-muted-foreground">..</span>
            <Hash value={target.head_sha} />
          </span>
        </Row>
        <Row icon={FileLock2} label="Checksum">
          <Hash value={target.fixture_checksum_sha256} length={CHECKSUM_PREVIEW} />
        </Row>
        <Row icon={FolderGit2} label="GitHub repo">
          {target.github_repository ? (
            <code className="font-mono">{target.github_repository}</code>
          ) : (
            <span className="text-muted-foreground">not bound</span>
          )}
        </Row>
        <Row icon={Route} label="Routes">
          <ul className="space-y-1">
            {target.routes.map((r) => (
              <li key={r.path} className="flex flex-wrap items-center gap-2">
                <code className="text-foreground/90 font-mono">{r.path}</code>
                {r.primary_action && (
                  <span className="text-muted-foreground bg-muted/50 rounded border px-1.5 font-mono text-[10.5px]">
                    {r.primary_action}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Row>
        <Row icon={Users} label="Identities">
          <ul className="flex flex-wrap gap-1.5">
            {target.identities.map((i) => (
              <li key={i.id} className="inline-flex items-center overflow-hidden rounded-md border text-[11px]">
                <span className="px-1.5 py-0.5 font-mono">{i.id}</span>
                <span className="text-muted-foreground bg-muted/50 border-l px-1.5 py-0.5">{i.role}</span>
              </li>
            ))}
          </ul>
        </Row>
      </dl>
    </article>
  );
}
