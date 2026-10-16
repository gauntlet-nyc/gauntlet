"""OFFLINE deterministic replay of the synthetic support agent. Not a model run.

The seeded history was produced by a synthetic agent with one documented policy: refund the
requester's own order; refund someone else's order only when its context (retrieved KB chunk or
memory note) says ownership was already verified upstream. This engine re-applies that policy to
the recorded inputs, so control replays can be compared with recorded outcomes and
counterfactual replays can remove exactly one source. Live replay (model + Daytona world) goes
through the same ReplayEngine port and is NOT RUN here.
"""

import re
from typing import Final

from gauntlet.contracts import HistoricalDecision, ReplayResult, ReplaySpec
from gauntlet.domain import ReplayStatus
from gauntlet.ports import ReplayWorld

from .history import FixtureHistory

LABEL: Final = "OFFLINE synthetic-agent replay (deterministic policy, no model call)"
_ORDER = re.compile(r"\bord-\d+\b")
_VERIFIED_UPSTREAM = re.compile(r"ownership (?:was|is) (?:checked|verified) upstream", re.I)


class SyntheticAgentReplay:
    """ReplayEngine for the seeded Cartwheel history."""

    def __init__(self, history: FixtureHistory) -> None:
        self._h = history

    def _derived_from(self, source_id: str) -> set[str]:
        """Memories derived from a removed chunk are removed with it."""
        return {
            e.target.node_id
            for e in self._h.edges
            if e.relation == "derived_into" and e.source.node_id == source_id
        }

    def _context(self, decision: HistoricalDecision, excluded: str | None) -> list[str]:
        removed = {excluded, *self._derived_from(excluded)} if excluded else set()
        texts: list[str] = []
        for sid in decision.source_ids:
            if sid in removed:
                continue
            if sid in self._h.kb_chunks:
                texts.append(self._h.kb_chunks[sid]["text"])
            elif sid in self._h.memory:
                texts.append(self._h.memory[sid]["content"])
        return texts

    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        decision = self._h.decisions.get(spec.decision_id or "")
        message = self._h.messages.get(spec.decision_id or "")
        if decision is None or message is None:
            return ReplayResult(
                replay_id=spec.replay_id,
                status=ReplayStatus.NOT_REPLAYABLE,
                limitations=("decision or its input message was not recorded", LABEL),
            )
        if decision.tool_results_hash is None or spec.tool_results_hash is None:
            return ReplayResult(
                replay_id=spec.replay_id,
                status=ReplayStatus.NOT_REPLAYABLE,
                limitations=("recorded tool result is missing", LABEL),
            )
        found = _ORDER.search(message["text"])
        order = self._h.orders.get(found.group(0)) if found else None
        if order is None:
            return ReplayResult(
                replay_id=spec.replay_id,
                status=ReplayStatus.NOT_REPLAYABLE,
                limitations=("order in the recorded message is unknown", LABEL),
            )
        owner = message["actor_ref"] == order["owner_id"]
        vouched = any(
            _VERIFIED_UPSTREAM.search(t) for t in self._context(decision, spec.excluded_source_id)
        )
        refund = owner or vouched
        action = "start_refund" if refund else "decline_refund"
        amount = order["total_cents"] if refund else None
        same = action == decision.structured_action and amount == decision.amount_minor
        return ReplayResult(
            replay_id=spec.replay_id,
            status=ReplayStatus.MATCHED if same else ReplayStatus.DIFFERENT,
            observed_action=action,
            amount_minor=amount,
            limitations=(LABEL,),
        )


class FixtureWorldResolver:
    """Every seeded decision ran on the refund-tool head revision of the synthetic fixture."""

    def __init__(self, world: ReplayWorld | None) -> None:
        self._world = world

    async def world_for(self, decision: HistoricalDecision) -> ReplayWorld | None:
        return self._world
