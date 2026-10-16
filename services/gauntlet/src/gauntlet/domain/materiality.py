"""When does a replayed decision count as 'the same' or 'materially different'? Stdlib only.

Structured outcomes (action + amount) are compared in code. Free-text promises need a
grounded judge with cited policy and human review; they are out of scope here.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionOutcome:
    action: str | None
    amount_minor: int | None


@dataclass(frozen=True)
class MaterialityPolicy:
    version: str = "materiality-1.0"
    amount_tolerance_minor: int = 0

    def differs(self, a: DecisionOutcome, b: DecisionOutcome) -> bool:
        if a.action != b.action:
            return True
        if (a.amount_minor is None) != (b.amount_minor is None):
            return True
        if a.amount_minor is not None and b.amount_minor is not None:
            return abs(a.amount_minor - b.amount_minor) > self.amount_tolerance_minor
        return False


@dataclass(frozen=True)
class ReplayDistribution:
    """Outcome of repeated replays. `stable` only if every run agrees under the policy."""

    outcomes: tuple[DecisionOutcome, ...]
    stable: bool


def distribution(
    outcomes: Sequence[DecisionOutcome], policy: MaterialityPolicy
) -> ReplayDistribution:
    stable = bool(outcomes) and all(not policy.differs(outcomes[0], o) for o in outcomes[1:])
    return ReplayDistribution(tuple(outcomes), stable)
