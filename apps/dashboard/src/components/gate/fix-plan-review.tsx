import { AlertTriangle, CheckCircle2, Wrench, XCircle } from "lucide-react";

import { humanize } from "@/components/gate/copy";
import { MonoId } from "@/components/gate/mono-id";
import { PatchDisclosure } from "@/components/gate/patch-disclosure";
import { PendingButton } from "@/components/gate/pending-button";
import { ScrollIntoView } from "@/components/gate/scroll-into-view";
import { DecideForm, DiffView, TONE_CLASSES } from "@/components/shared";
import type { GateRunView } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

type FixPlan = NonNullable<GateRunView["fix_plan"]>;
type Repair = NonNullable<GateRunView["repair"]>;

function RepairResult({ repair }: { repair: Repair }) {
  const ok = repair.verdict === "fix_verified_review_required";
  const tone = TONE_CLASSES[ok ? "good" : "bad"];
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="border-t pt-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Icon className={cn("size-4", tone.text)} aria-hidden />
        <strong className={cn("text-sm", tone.text)}>Release verdict: {repair.verdict.replaceAll("_", " ")}</strong>
        {repair.patched_sha && (
          <span className="text-muted-foreground text-xs">
            patched <MonoId value={repair.patched_sha} ellipsis={false} />, local commit, never pushed
          </span>
        )}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 pl-7">
        {repair.checks.map((c) => {
          const t = TONE_CLASSES[c.passed ? "good" : "bad"];
          const CheckIcon = c.passed ? CheckCircle2 : XCircle;
          return (
            <li key={c.name} className="flex items-center gap-1.5 text-xs" title={c.detail}>
              <CheckIcon className={cn("size-3.5", t.text)} aria-hidden />
              {humanize(c.name)}
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground mt-3 pl-7 text-xs">{repair.note}</p>
    </div>
  );
}

/** The one action this page asks of a reviewer: decide on the proposed fix, then re-verify it. */
export function FixPlanReview({
  runId,
  fixPlan,
  repair,
  back,
  repairStatus,
  approvalStatus,
  decide,
  runRepair,
}: {
  runId: string;
  fixPlan: FixPlan;
  repair: GateRunView["repair"];
  back: string;
  repairStatus: string | undefined;
  approvalStatus?: string | undefined;
  decide: (form: FormData) => Promise<void>;
  runRepair: (form: FormData) => Promise<void>;
}) {
  const { plan } = fixPlan;
  return (
    <section id="next-step" aria-label="Next step" className="bg-card scroll-mt-20 space-y-5 rounded-xl border p-6">
      <div>
        <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium tracking-wide uppercase">
          <Wrench className="size-3.5" aria-hidden />
          Next step · review the proposed fix
        </div>
        <p className="mt-2 text-[15px] leading-relaxed">{plan.rationale}</p>
      </div>
      <PatchDisclosure summary={<span className="font-mono text-xs">{fixPlan.allowed_paths.join(", ")}</span>}>
        <DiffView diff={plan.unified_diff} />
        <ol className="text-muted-foreground mt-3 list-decimal space-y-1 pl-5 text-xs">
          {plan.test_plan.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ol>
      </PatchDisclosure>
      {(approvalStatus !== undefined || repairStatus !== undefined) && <ScrollIntoView targetId="next-step" />}
      {approvalStatus === "recorded" && (
        <div
          role="status"
          className="border-passed/30 bg-passed/[0.07] text-passed flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm"
        >
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            Decision recorded for plan <span className="font-mono text-xs">{fixPlan.plan_sha256.slice(0, 12)}…</span>.
            It is single-use and expires; nothing was merged or deployed.
          </span>
        </div>
      )}
      {approvalStatus !== undefined && approvalStatus !== "recorded" && (
        <div
          role="alert"
          className="border-regression/30 bg-regression/[0.07] text-regression flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm"
        >
          <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            Decision refused (HTTP {approvalStatus}). {approvalStatus === "401" ? "Log in as a reviewer first." : "The plan changed; review it again."}
          </span>
        </div>
      )}
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
        <form action={runRepair} className="space-y-3">
          <input type="hidden" name="run_id" value={runId} />
          <PendingButton icon={<Wrench aria-hidden />} variant="outline" pendingLabel="Re-verifying in a fresh worktree…">
            Apply approved plan in a fresh worktree and re-verify
          </PendingButton>
          {repairStatus && repairStatus !== "done" && (
            <p role="alert" className="text-regression flex items-start gap-2 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              Refused (HTTP {repairStatus}): approve this exact hash first; approvals are single use.
            </p>
          )}
        </form>
      ) : (
        <p className="text-muted-foreground text-xs">Sample plan for review only; the repair runner is wired for AI-agent findings.</p>
      )}
      {repair && <RepairResult repair={repair} />}
    </section>
  );
}
