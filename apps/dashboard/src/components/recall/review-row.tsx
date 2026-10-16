"use client";

import { ChevronRight, Inbox, Scale, ShieldCheck } from "lucide-react";
import { useId, useRef, useState, type MouseEvent } from "react";

import { StatusPill, TONE_CLASSES } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ReviewItem } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

const APPROVE_LABEL = "Approve for review";
const SUBJECT = "remediation";
const BACK = "/recall/review";

/** What approving each kind of draft would queue for a human. Nothing here is executed by Gauntlet. */
const WOULD_CHANGE: Record<string, string> = {
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

function titleOf(item: ReviewItem): { label: string; count: string | null; mono: boolean } {
  const [head = item.title, tail] = item.title.split(" — ");
  const label = TITLE_LABELS[head];
  if (label) return { label, count: tail?.replace(/^1 items$/, "1 item") ?? null, mono: false };
  return { label: item.kind === "counterfactual_case" ? (head.split(":")[0] ?? head) : item.title, count: null, mono: true };
}

function Ids({ ids }: { ids: readonly string[] }) {
  return <span className="text-foreground font-mono">{ids.join(", ")}</span>;
}

export function ReviewRow({
  item,
  evidence,
  action,
}: {
  item: ReviewItem;
  evidence: ReviewEvidence;
  action: (form: FormData) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const reasonRef = useRef<HTMLInputElement>(null);
  const detailId = useId();
  const pending = item.status === "pending";
  const isCase = item.kind === "counterfactual_case";
  const KindIcon = isCase ? Scale : Inbox;
  const title = titleOf(item);

  // A rejection needs a reason: open the row and ask for one instead of submitting blank.
  const onReject = (e: MouseEvent<HTMLButtonElement>) => {
    if (reasonRef.current?.value.trim()) return;
    e.preventDefault();
    setOpen(true);
    requestAnimationFrame(() => reasonRef.current?.focus());
  };

  return (
    <li className={cn("transition-colors", open && "bg-accent/30")}>
      <form action={action}>
        <input type="hidden" name="run_id" value={item.recall_id} />
        <input type="hidden" name="subject" value={SUBJECT} />
        <input type="hidden" name="subject_id" value={item.item_id} />
        <input type="hidden" name="plan_sha256" value={item.plan_sha256} />
        <input type="hidden" name="back" value={BACK} />

        <div className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-4">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls={detailId}
            className="flex min-w-0 flex-1 items-center gap-3 text-left"
          >
            <ChevronRight
              className={cn("text-muted-foreground size-4 shrink-0 transition-transform", open && "rotate-90")}
              aria-hidden
            />
            <KindIcon className="text-muted-foreground size-4 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className={cn("truncate text-sm font-medium", title.mono && "font-mono")}>{title.label}</span>
                {title.count && <span className="text-muted-foreground shrink-0 text-xs">{title.count}</span>}
                {isCase && <StatusPill value={item.classification} />}
              </span>
              <span className="text-muted-foreground block truncate text-xs">{item.rationale}</span>
            </span>
          </button>

          <div className="flex shrink-0 items-center gap-2 pl-14 md:pl-0">
            {pending ? (
              <>
                <Button type="submit" name="decision" value="approved" size="sm" variant="outline">
                  <ShieldCheck aria-hidden />
                  {APPROVE_LABEL}
                </Button>
                <Button type="submit" name="decision" value="rejected" variant="ghost" size="sm" onClick={onReject}>
                  Reject
                </Button>
              </>
            ) : (
              <span className={cn("text-xs", TONE_CLASSES.good.text)}>{item.status.replaceAll("_", " ")}</span>
            )}
          </div>
        </div>

        <div id={detailId} hidden={!open} className="space-y-3 px-4 pb-4 pl-[4.5rem] text-xs">
          <p className="text-sm">{WOULD_CHANGE[item.classification] ?? "Records a human decision. Nothing is executed."}</p>
          <div className="text-muted-foreground space-y-1">
            {evidence.decisions.length > 0 && (
              <p>
                Decisions <Ids ids={evidence.decisions} />
              </p>
            )}
            {evidence.evidenceIds.length > 0 && (
              <p>
                Ledger <Ids ids={evidence.evidenceIds} />
              </p>
            )}
            {evidence.replays != null && (
              <p>{evidence.replays ? `${evidence.replays} replays (control and counterfactual)` : "No replays: inputs missing"}</p>
            )}
            {evidence.missing.length > 0 && <p className={TONE_CLASSES.unknown.text}>Missing {evidence.missing.join(", ")}</p>}
          </div>
          {pending && (
            <div className="max-w-md space-y-1.5">
              <Input ref={reasonRef} name="reason" placeholder="Reason (required to reject)" className="h-8 text-sm" />
              <p className="text-muted-foreground">
                Binds to plan hash <code className="font-mono">{item.plan_sha256.slice(0, 16)}…</code>. Human decision only.
              </p>
            </div>
          )}
          {!pending && item.approval_id && (
            <p className="text-muted-foreground">
              Decision <code className="font-mono">{item.approval_id}</code>
            </p>
          )}
        </div>
      </form>
    </li>
  );
}
