import type { CounterfactualCase, DecisionView } from "@/lib/gauntlet";

/** Counterfactual classifications in the order the UI presents them. */
export const CASE_CLASSES = ["tainted", "cleared", "not_replayable"] as const;
export type CaseClass = (typeof CASE_CLASSES)[number] | "inconclusive";

export const ACTION_LABELS: Record<string, string> = {
  start_refund: "Start refund",
  decline_refund: "Decline refund",
};

export const NODE_KIND_LABELS: Record<string, string> = {
  document_chunk: "Knowledge chunk",
  memory: "Agent memory",
  decision: "Decision",
};

export const EXPOSURE_LABEL = { direct: "direct", secondOrder: "second-order" } as const;

/** Fixed-UTC formatting so server and client render identical strings. */
const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const TIME = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}
export function formatDay(iso: string): string {
  return DAY.format(new Date(iso));
}
export function formatTime(iso: string): string {
  return TIME.format(new Date(iso));
}

export function actionLabel(action: string | null | undefined): string {
  if (!action) return "Unknown";
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatAmount(minor: number | null | undefined): string | null {
  if (minor == null) return null;
  // Ledger amounts are USD minor units (cents), as in the Cartwheel order fixture.
  return USD.format(minor / 100);
}

export interface Outcome {
  action: string;
  amount: string | null;
  known: boolean;
}

/** The recorded decision the agent actually made. */
export function originalOutcome(view: DecisionView | undefined): Outcome {
  if (!view) return { action: "Not in timeline", amount: null, known: false };
  return {
    action: actionLabel(view.decision.structured_action),
    amount: formatAmount(view.decision.amount_minor),
    known: true,
  };
}

const CHOSE = /without \S+ the agent chose (\w+) \((?:amount (\d+)|no amount)\)/;

/**
 * The replayed decision with the trigger removed. A cleared case means the outcome did not change; tainted
 * rationales name the counterfactual action; anything not replayed has no counterfactual outcome.
 */
export function counterfactualOutcome(c: CounterfactualCase, original: Outcome): Outcome {
  const cls = c.verdict.classification;
  if (cls === "cleared") return { ...original };
  const match = CHOSE.exec(c.verdict.rationale);
  if (match?.[1]) {
    return {
      action: actionLabel(match[1]),
      amount: match[2] ? formatAmount(Number(match[2])) : null,
      known: true,
    };
  }
  return { action: c.replayable ? "No stable outcome" : "Not replayed", amount: null, known: false };
}

export function caseClass(c: CounterfactualCase): CaseClass {
  const cls = c.verdict.classification;
  return (CASE_CLASSES as readonly string[]).includes(cls) ? (cls as CaseClass) : "inconclusive";
}

export function caseAnchor(decisionId: string): string {
  return `case-${decisionId}`;
}
