import { CheckCircle2, FileSearch, Inbox, Scale } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPill, TONE_CLASSES } from "@/components/shared";
import type { ReviewItem } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

export const REVIEW_KIND_LABELS: Record<string, string> = {
  remediation_proposal: "Remediation draft",
  counterfactual_case: "Counterfactual case",
};

/** What approving each kind of draft would queue for a human. Nothing here is executed by Gauntlet. */
export const WOULD_CHANGE: Record<string, string> = {
  reverse_transaction_review: "Opens a reversal review for the listed ledger credits. No money moves until a person acts.",
  customer_contact_review: "Drafts a customer-contact review for each listed decision. No message is sent.",
  collect_missing_evidence: "Asks for the missing records to be collected. The case stays undetermined until then.",
  policy_fix_review: "Opens a policy-fix review. The agent's policy is not changed.",
  tainted: "Marks this decision for human follow-up. The original refund is not reversed.",
  not_replayable: "Marks this decision as undetermined pending evidence. It is never cleared automatically.",
  cleared: "Records that removing the source did not change this decision.",
};

const TITLE_LABELS: Record<string, string> = {
  reverse_transaction_review: "Reverse transaction review",
  customer_contact_review: "Customer contact review",
  collect_missing_evidence: "Collect missing evidence",
  policy_fix_review: "Policy fix review",
};

export interface ReviewEvidence {
  decisions: string[];
  evidenceIds: string[];
  replays: number | null;
  missing: string[];
}

function humanTitle(item: ReviewItem): ReactNode {
  const [head, rawTail] = item.title.split(" — ");
  const label = head ? TITLE_LABELS[head] : undefined;
  const tail = rawTail?.replace(/^1 items$/, "1 item");
  if (label) {
    return (
      <>
        {label}
        {tail && <span className="text-muted-foreground font-normal"> · {tail}</span>}
      </>
    );
  }
  return <span className="font-mono">{item.kind === "counterfactual_case" ? head?.split(":")[0] : item.title}</span>;
}

function Chips({ ids }: { ids: readonly string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <code key={id} className="bg-muted rounded px-1.5 py-0.5 font-mono text-[11px]">
          {id}
        </code>
      ))}
    </div>
  );
}

export function ReviewItemCard({ item, evidence, form }: { item: ReviewItem; evidence: ReviewEvidence; form: ReactNode }) {
  const pending = item.status === "pending";
  const isCase = item.kind === "counterfactual_case";
  const KindIcon = isCase ? Scale : Inbox;
  const change = WOULD_CHANGE[item.classification];

  return (
    <article className={cn("bg-card overflow-hidden rounded-xl border", !pending && "opacity-75")}>
      <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="bg-muted mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md">
            <KindIcon className="text-muted-foreground size-4" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="text-muted-foreground flex items-center gap-2 text-[11px] font-medium tracking-wide uppercase">
              {REVIEW_KIND_LABELS[item.kind] ?? item.kind}
              <span aria-hidden>·</span>
              <span className="font-mono tracking-normal normal-case">{item.recall_id}</span>
            </div>
            <h3 className="mt-0.5 text-[15px] font-medium">{humanTitle(item)}</h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isCase && <StatusPill value={item.classification} />}
          <span
            className={cn(
              "inline-flex h-5 items-center gap-1 rounded-full border px-2 text-xs",
              pending ? "text-muted-foreground" : cn(TONE_CLASSES.good.text, TONE_CLASSES.good.border),
            )}
          >
            {!pending && <CheckCircle2 className="size-3" aria-hidden />}
            {item.status.replaceAll("_", " ")}
          </span>
        </div>
      </header>

      <p className="text-muted-foreground mt-3 px-5 text-sm leading-relaxed">{item.rationale}</p>

      <div className="mt-4 grid gap-4 px-5 pb-4 md:grid-cols-2">
        <div className="rounded-lg border px-3.5 py-3">
          <div className="text-muted-foreground text-xs font-medium">If approved (draft only)</div>
          <p className="mt-1 text-sm">{change ?? "Records a human decision. Nothing is executed."}</p>
        </div>
        <div className="rounded-lg border px-3.5 py-3">
          <div className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
            <FileSearch className="size-3.5" aria-hidden />
            Evidence
          </div>
          <dl className="mt-1.5 space-y-1.5 text-xs">
            {evidence.decisions.length > 0 && (
              <div className="flex gap-3">
                <dt className="text-muted-foreground w-20 shrink-0">Decisions</dt>
                <dd>
                  <Chips ids={evidence.decisions} />
                </dd>
              </div>
            )}
            {evidence.evidenceIds.length > 0 && (
              <div className="flex gap-3">
                <dt className="text-muted-foreground w-20 shrink-0">Ledger</dt>
                <dd>
                  <Chips ids={evidence.evidenceIds} />
                </dd>
              </div>
            )}
            {evidence.replays != null && (
              <div className="flex gap-3">
                <dt className="text-muted-foreground w-20 shrink-0">Replays</dt>
                <dd className="tabular-nums">
                  {evidence.replays ? `${evidence.replays} (control + counterfactual)` : "none, inputs missing"}
                </dd>
              </div>
            )}
            {evidence.missing.length > 0 && (
              <div className="flex gap-3">
                <dt className="text-muted-foreground w-20 shrink-0">Missing</dt>
                <dd className={TONE_CLASSES.unknown.text}>
                  <Chips ids={evidence.missing} />
                </dd>
              </div>
            )}
            {evidence.decisions.length + evidence.evidenceIds.length + evidence.missing.length === 0 &&
              evidence.replays == null && <div className="text-muted-foreground">No linked evidence recorded.</div>}
          </dl>
        </div>
      </div>

      <div className="bg-muted/30 border-t px-5 py-4">{form}</div>
    </article>
  );
}
