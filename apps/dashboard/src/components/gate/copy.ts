import type { AttemptView, GateRunView } from "@/lib/gauntlet";

/** Product copy for the known demo changes. Unknown changes fall back to their feature intent only. */
export interface ChangeCopy {
  kind: string;
  summary: string;
}

export const CHANGE_COPY: Readonly<Record<string, ChangeCopy>> = {
  "help-button": {
    kind: "UI change",
    summary: "Adds a fixed-position Help button. Gauntlet checks whether it covers Checkout on narrow screens.",
  },
  "refund-tool": {
    kind: "AI-agent tool",
    summary: "Gives the support assistant a refund tool. Gauntlet tries to refund another customer's order through chat.",
  },
  clean: {
    kind: "Copy change",
    summary: "Rewords the product description. Nothing should break: this is the control run.",
  },
};

export interface RevisionTally {
  failed: number;
  total: number;
}

export interface RunTally {
  head: RevisionTally;
  base: RevisionTally;
}

function tallyOf(attempts: readonly AttemptView[]): RevisionTally {
  return { failed: attempts.filter((a) => a.outcome === "fail").length, total: attempts.length };
}

export function tallyRun(attempts: readonly AttemptView[]): RunTally {
  return {
    head: tallyOf(attempts.filter((a) => a.revision === "head")),
    base: tallyOf(attempts.filter((a) => a.revision === "base")),
  };
}

/** The exact comparison line the demo rehearsal asserts on. */
export function tallyLine({ head, base }: RunTally): string {
  return `Head: ${head.failed}/${head.total} failed · Base: ${base.failed}/${base.total} failed`;
}

export interface VerdictCopy {
  headline: string;
  explanation: string;
}

export function verdictCopy(run: Pick<GateRunView, "status" | "attribution" | "not_tested_reason">, tally: RunTally): VerdictCopy {
  const { head, base } = tally;
  const counts = `The attack failed ${head.failed} of ${head.total} times on head and ${base.failed} of ${base.total} times on base`;
  if (run.status === "passed") {
    return {
      headline: "No regression found",
      explanation:
        head.total > 0
          ? `Every planned attack passed on both revisions (${head.total + base.total} attempts). Not tested does not mean safe.`
          : "No attack failed. Not tested does not mean safe.",
    };
  }
  if (run.attribution === "introduced") {
    return {
      headline: run.status === "confirmed_policy_violation" ? "Policy violation introduced" : "Regression introduced",
      explanation: `${counts}, so the failure comes from this PR, not from code that was already there.`,
    };
  }
  if (run.attribution === "pre_existing") {
    return {
      headline: "Pre-existing failure",
      explanation: `${counts}. The problem predates this PR, so it should not block this change alone.`,
    };
  }
  return {
    headline: "Inconclusive",
    explanation: run.not_tested_reason ?? "The oracles could not reach a confident decision. Treat this change as untested.",
  };
}

export function humanize(value: string): string {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function runIndex(runId: string): string | null {
  const match = /-(\d+)$/.exec(runId);
  return match ? `#${match[1]}` : null;
}
