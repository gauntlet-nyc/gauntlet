import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { TONE_CLASSES } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import type { CheckRunPreview } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

const CONCLUSION = {
  failure: { tone: TONE_CLASSES.bad, icon: XCircle, label: "Failing" },
  success: { tone: TONE_CLASSES.good, icon: CheckCircle2, label: "Successful" },
  neutral: { tone: TONE_CLASSES.unknown, icon: CircleDashed, label: "Neutral" },
} as const;

function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/** Inline markdown: **bold**, `code`, _italic_. Everything else is plain text (never HTML). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    if (part.length > 2 && part.startsWith("_") && part.endsWith("_"))
      return (
        <em key={i} className="text-muted-foreground">
          {part.slice(1, -1)}
        </em>
      );
    return part;
  });
}

function cells(row: string): string[] {
  return row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

/** Renders the check-run summary's small markdown subset: paragraphs and pipe tables. */
function SummaryMarkdown({ source }: { source: string }) {
  const blocks = source.split(/\n{2,}/);
  return (
    <div className="space-y-3 text-sm">
      {blocks.map((block, b) => {
        const lines = block.split("\n").filter(Boolean);
        if (lines.length >= 2 && lines.every((l) => l.trim().startsWith("|"))) {
          const [head, , ...rows] = lines;
          return (
            <div key={b} className="overflow-x-auto rounded-md border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40">
                  <tr>
                    {cells(head ?? "").map((c) => (
                      <th key={c} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map((r, i) => (
                    <tr key={i}>
                      {cells(r).map((c, j) => (
                        <td key={j} className="px-3 py-2 whitespace-nowrap tabular-nums">
                          {inline(c)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={b} className="leading-relaxed">
            {inline(lines.join(" "))}
          </p>
        );
      })}
    </div>
  );
}

/** Preview of the GitHub check run, laid out like GitHub's own checks panel. */
export function CheckRunCard({ check }: { check: CheckRunPreview }) {
  const c = CONCLUSION[check.conclusion];
  const Icon = c.icon;
  return (
    <div className="bg-card overflow-hidden rounded-xl border">
      <div className="bg-muted/30 flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <GithubMark className="size-3.5" />
          <span>Checks</span>
          <span className="text-muted-foreground/50">/</span>
          <span className="text-foreground font-medium">{check.name}</span>
        </div>
        <Badge variant="outline" className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
          {check.published ? "Published" : "Preview · not published"}
        </Badge>
      </div>
      <div className="flex items-start gap-3 px-4 py-4">
        <Icon className={cn("mt-0.5 size-5 shrink-0", c.tone.text)} aria-hidden />
        <div className="min-w-0">
          <div className="font-semibold">{check.title}</div>
          <div className="text-muted-foreground mt-0.5 text-xs">
            <span className={c.tone.text}>{c.label}</span> · conclusion <code className="font-mono">{check.conclusion}</code>
          </div>
        </div>
      </div>
      <div className="border-t px-4 py-4">
        <SummaryMarkdown source={check.summary} />
      </div>
      <div className="text-muted-foreground border-t px-4 py-2.5 text-xs">
        {check.note} Checks-only: Gauntlet never comments, approves or merges.
      </div>
    </div>
  );
}
