import {
  AudioLines,
  Box,
  Brain,
  CheckCircle2,
  Cloud,
  Database,
  FlaskConical,
  GitPullRequest,
  Globe,
  KeyRound,
  Sparkles,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

import type { ReactNode } from "react";

import { CopyCommand } from "@/components/sponsors/copy-command";
import type { SponsorStatus } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

/** The only status the API uses once a recorded live run exists. Keys alone never produce it. */
export const LIVE_STATUS = "live verified";

export function isLive(s: SponsorStatus): boolean {
  return s.status === LIVE_STATUS;
}

interface Role {
  icon: LucideIcon;
  powers: string;
}

/** What each provider powers inside Gauntlet. Unknown sponsors fall back to a neutral role. */
const ROLES: Record<string, Role> = {
  Daytona: { icon: Box, powers: "Isolated base and head sandboxes" },
  Anchor: { icon: Globe, powers: "Cloud browser for UI attacks" },
  "Arize AX": { icon: Waypoints, powers: "Tracing and experiment visibility" },
  "SurrealDB core": { icon: Database, powers: "Run, evidence and lineage store" },
  "SurrealDB Agent Memory": { icon: Brain, powers: "Planner memory across runs" },
  ElevenLabs: { icon: AudioLines, powers: "Spoken run briefings" },
  "Azure OpenAI (planner)": { icon: Sparkles, powers: "Attack planner (proposes only)" },
  "AWS Bedrock (planner, alternate)": { icon: Cloud, powers: "Alternate attack planner" },
  "GitHub App (check runs)": { icon: GitPullRequest, powers: "Check runs on pull requests" },
};

/** Some sponsors have a note instead of a runnable command; only real commands get a copy button. */
const SHELL_COMMAND = /^[A-Z][A-Z0-9_]*=[^\s;]+\s|^(uv|pnpm|python|\.venv)\b/;

const FALLBACK_ROLE: Role = { icon: Box, powers: "Provider integration" };

function StatusBadge({ sponsor }: { sponsor: SponsorStatus }) {
  const live = isLive(sponsor);
  const Icon = live ? CheckCircle2 : FlaskConical;
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
        live ? "border-passed/30 bg-passed/10 text-passed" : "border-inconclusive/25 bg-inconclusive/[0.07] text-inconclusive",
      )}
    >
      <Icon className="size-3" aria-hidden />
      {sponsor.status}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[88px_1fr] sm:gap-3">
      <dt className="text-muted-foreground pt-0.5 text-xs">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export function SponsorCard({ sponsor }: { sponsor: SponsorStatus }) {
  const role = ROLES[sponsor.sponsor] ?? FALLBACK_ROLE;
  return (
    <article className="bg-card flex w-full flex-col rounded-xl border">
      <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="bg-foreground/[0.04] flex size-9 shrink-0 items-center justify-center rounded-lg border">
            <role.icon className="size-4" aria-hidden />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-[15px] leading-tight font-semibold tracking-tight">{sponsor.sponsor}</h3>
            <p className="text-muted-foreground truncate text-xs">{role.powers}</p>
          </div>
        </div>
        <StatusBadge sponsor={sponsor} />
      </header>

      <dl className="mt-5 space-y-3 px-5 text-sm">
        <Field label="Adapter">
          <code className="text-foreground/80 block truncate font-mono text-xs" title={sponsor.adapter}>
            {sponsor.adapter}
          </code>
        </Field>
        <Field label="Keys">
          {sponsor.configured ? (
            <span className="text-foreground inline-flex items-center gap-1.5 text-xs">
              <KeyRound className="size-3.5" aria-hidden />
              Configured
            </span>
          ) : (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground mr-0.5 text-xs">Missing</span>
              {sponsor.missing_env.map((env) => (
                <code
                  key={env}
                  className="bg-muted/60 text-foreground/80 rounded-md border px-1.5 py-0.5 font-mono text-[11px]"
                >
                  {env}
                </code>
              ))}
            </div>
          )}
        </Field>
        <Field label="Produces">
          <ul className="flex flex-wrap gap-1.5">
            {sponsor.produces.map((p) => (
              <li key={p} className="text-foreground/85 rounded-md border px-1.5 py-0.5 text-xs">
                {p}
              </li>
            ))}
          </ul>
        </Field>
      </dl>

      {sponsor.notes && (
        <p className="text-muted-foreground mt-4 px-5 text-[13px] leading-relaxed">{sponsor.notes}</p>
      )}

      <div className="mt-auto px-5 pt-4 pb-5">
        <div className="text-muted-foreground mb-1.5 text-xs">Prove it live</div>
        {SHELL_COMMAND.test(sponsor.live_command) ? (
          <CopyCommand command={sponsor.live_command} />
        ) : (
          <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-2.5 text-xs leading-5">
            {sponsor.live_command}
          </p>
        )}
      </div>
    </article>
  );
}
