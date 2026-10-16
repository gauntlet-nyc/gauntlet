import { AlertTriangle, CheckCircle2, FolderLock, GitCommitHorizontal, ListChecks, Wrench, XCircle } from "lucide-react";

import { MonoId } from "@/components/gate/mono-id";
import { PendingButton } from "@/components/gate/pending-button";
import { DecideForm, DiffView, OfflineBadge, ProvenanceList, TONE_CLASSES } from "@/components/shared";
import type { GateRunView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

type FixPlan = NonNullable<GateRunView["fix_plan"]>;
type Repair = NonNullable<GateRunView["repair"]>;

function RepairResult({ repair }: { repair: Repair }) {
  const ok = repair.verdict === "fix_verified_review_required";
  const tone = TONE_CLASSES[ok ? "good" : "bad"];
  return (
    <div className={cn("bg-card overflow-hidden rounded-xl border", tone.border)}>
      <div className={cn("flex flex-wrap items-center gap-3 border-b px-5 py-4", tone.bg)}>
        {ok ? <CheckCircle2 className={cn("size-5", tone.text)} aria-hidden /> : <XCircle className={cn("size-5", tone.text)} aria-hidden />}
        <strong className={cn("text-base", tone.text)}>Release verdict: {repair.verdict.replaceAll("_", " ")}</strong>
        {repair.patched_sha && (
          <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
            <GitCommitHorizontal className="size-3.5" aria-hidden />
            patched <MonoId value={repair.patched_sha} /> (local commit, never pushed)
          </span>
        )}
      </div>
      <ul className="divide-y">
        {repair.checks.map((c) => {
          const t = TONE_CLASSES[c.passed ? "good" : "bad"];
          const Icon = c.passed ? CheckCircle2 : XCircle;
          return (
            <li key={c.name} className="flex items-start gap-3 px-5 py-3 text-sm">
              <Icon className={cn("mt-0.5 size-4 shrink-0", t.text)} aria-hidden />
              <div className="min-w-0">
                <div className="font-medium capitalize">{c.name.replaceAll("_", " ")}</div>
                <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">{c.detail}</p>
              </div>
            </li>
          );
        })}
      </ul>
      <div className="space-y-3 border-t px-5 py-4">
        <p className="text-muted-foreground text-xs leading-relaxed">{repair.note}</p>
        <ProvenanceList provenance={repair.provenance} />
      </div>
    </div>
  );
}

/** Proposed patch, its scope, the hash-bound human decision and the optional repair re-verification. */
export function FixPlanReview({
  runId,
  fixPlan,
  repair,
  back,
  repairStatus,
  decide,
  runRepair,
}: {
  runId: string;
  fixPlan: FixPlan;
  repair: GateRunView["repair"];
  back: string;
  repairStatus: string | undefined;
  decide: (form: FormData) => Promise<void>;
  runRepair: (form: FormData) => Promise<void>;
}) {
  const { plan } = fixPlan;
  return (
    <div className="space-y-4">
      <OfflineBadge provenance={[fixPlan.provenance]} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-3">
          <p className="text-[15px] leading-relaxed">{plan.rationale}</p>
          <DiffView diff={plan.unified_diff} />
        </div>
        <div className="space-y-4">
          <div className="bg-card rounded-xl border p-4">
            <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
              <FolderLock className="size-3.5" aria-hidden />
              Allowed paths
            </div>
            <ul className="mt-2 space-y-1">
              {fixPlan.allowed_paths.map((p) => (
                <li key={p} className="font-mono text-xs break-all">
                  {p}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground mt-2 text-[11px] leading-snug">Any edit outside these paths fails verification.</p>
          </div>
          <div className="bg-card rounded-xl border p-4">
            <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
              <ListChecks className="size-3.5" aria-hidden />
              Verification plan
            </div>
            <ol className="mt-2 space-y-2">
              {plan.test_plan.map((t, i) => (
                <li key={t} className="flex gap-2 text-xs leading-relaxed">
                  <span className="text-muted-foreground font-mono tabular-nums">{i + 1}.</span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl border">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
          <span className="text-sm font-medium">Your decision</span>
          <span className="text-muted-foreground text-xs">
            plan <MonoId value={fixPlan.plan_sha256} chars={12} />
          </span>
        </div>
        <div className="space-y-4 px-5 py-4">
          <DecideForm
            action={decide}
            runId={runId}
            subject="fix_plan"
            subjectId={plan.fix_plan_id}
            planSha256={fixPlan.plan_sha256}
            back={back}
            approveLabel="Approve fix plan"
          />
          {fixPlan.repairable ? (
            <form action={runRepair} className="space-y-3 border-t pt-4">
              <input type="hidden" name="run_id" value={runId} />
              <PendingButton icon={<Wrench aria-hidden />} variant="outline" pendingLabel="Re-verifying in a fresh worktree…">
                Apply approved plan in a fresh worktree and re-verify
              </PendingButton>
              {repairStatus && repairStatus !== "done" && (
                <div role="alert" className="border-regression/30 bg-regression/[0.07] text-regression flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>Refused (HTTP {repairStatus}): approve this exact hash first; approvals are single use.</span>
                </div>
              )}
            </form>
          ) : (
            <p className="text-muted-foreground border-t pt-4 text-xs">
              This sample plan is for review only; the repair runner is wired for AI-agent findings.
            </p>
          )}
        </div>
      </div>

      {repair && <RepairResult repair={repair} />}
    </div>
  );
}
