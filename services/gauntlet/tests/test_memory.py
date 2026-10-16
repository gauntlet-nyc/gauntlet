"""A-07 / Phase 7 gate shape: verified memory reaches the planner with provenance; no
hindsight via `as_of`; superseded advice hidden from planning but kept; untrusted ignored."""

import asyncio
import itertools
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import DemoRepo
from fakes import (
    FakeOracleRegistry,
    InMemoryRunStore,
    ScriptedModelGateway,
    StaticTargetCatalog,
)
from pydantic import ValidationError

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.contracts import ChangeRequest, SurfaceKind, TemporalMemoryFact
from gauntlet.planning import AttackPlanner, PlanningLimits, select_memory
from gauntlet.ports import MemoryQuery

DISCOVERED = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
LATER = DISCOVERED + timedelta(days=7)


def fact(fact_id: str, **overrides: object) -> TemporalMemoryFact:
    fields: dict[str, Any] = {
        "fact_id": fact_id,
        "kind": "ui_occlusion",
        "summary": "Fixed help overlays can occlude primary mobile actions",
        "verification": "confirmed",
        "trust": "verified_test",
        "scope": "project/cartwheel-fixture",
        "surface_kinds": ["style", "component"],
        "source": {"finding_id": "finding-001", "oracle_id": "ui.primary_action_reachable"},
        "known_at": DISCOVERED,
        "valid_from": DISCOVERED - timedelta(minutes=5),
    }
    fields.update(overrides)
    return TemporalMemoryFact.model_validate(fields)


OCCLUSION = fact("mem-083")
CORRECTION = fact(
    "mem-090",
    summary="Fixed overlays occlude mobile CTAs unless offset above the bottom safe area",
    known_at=DISCOVERED + timedelta(days=2),
    supersedes="mem-083",
)
UNVERIFIED = fact("mem-091", verification="unverified", trust="model_summary", source={})
APP_CONTENT = fact("mem-092", trust="app_content")
EXPIRED = fact("mem-093", valid_until=DISCOVERED + timedelta(days=1))
AUTHZ = fact("mem-094", kind="authz_bypass", surface_kinds=["agent_tool"])
ALL = (OCCLUSION, CORRECTION, UNVERIFIED, APP_CONTENT, EXPIRED, AUTHZ)
STYLE: frozenset[SurfaceKind] = frozenset({"style"})
AGENT_TOOL: frozenset[SurfaceKind] = frozenset({"agent_tool"})


def ids(facts: Sequence[TemporalMemoryFact]) -> list[str]:
    return [f.fact_id for f in facts]


def test_only_confirmed_trusted_current_facts_for_the_surface() -> None:
    # mem-093 is still inside its validity window at +1h; newest first, ties by id.
    assert ids(select_memory(ALL, DISCOVERED + timedelta(hours=1), STYLE, 10)) == [
        "mem-093",
        "mem-083",
    ]


def test_no_hindsight_before_discovery() -> None:
    assert select_memory(ALL, DISCOVERED - timedelta(seconds=1), STYLE, 10) == ()


def test_correction_supersedes_without_erasing() -> None:
    selected = select_memory(ALL, LATER, STYLE, 10)
    assert ids(selected) == ["mem-090"]
    assert OCCLUSION in ALL, "the superseded fact is still stored and inspectable"
    before_correction = select_memory(ALL, DISCOVERED + timedelta(days=1), STYLE, 10)
    assert ids(before_correction) == ["mem-083"]


def test_expired_validity_and_other_surfaces_are_excluded() -> None:
    assert "mem-093" not in ids(select_memory(ALL, LATER, STYLE, 10))
    assert ids(select_memory(ALL, LATER, AGENT_TOOL, 10)) == ["mem-094"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": {}},  # confirmed without finding/oracle
        {"trust": "model_summary"},  # model summaries cannot be confirmed
        {"valid_until": DISCOVERED - timedelta(days=1)},
        {"supersedes": "mem-083"},  # self-supersession (fact_id is mem-083)
        {"scope": "Project With Spaces"},
    ],
)
def test_contract_rejects_untraceable_or_inconsistent_facts(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        fact("mem-083", **overrides)


class Memory:
    def __init__(self, facts: Sequence[TemporalMemoryFact]) -> None:
        self.facts = tuple(facts)
        self.queries: list[MemoryQuery] = []

    async def recall(self, query: MemoryQuery) -> Sequence[TemporalMemoryFact]:
        self.queries.append(query)
        return self.facts  # deliberately unfiltered: the use case must re-filter


def plan_with_memory(
    repo: DemoRepo, as_of: datetime
) -> tuple[ScriptedModelGateway, InMemoryRunStore, Memory]:
    gateway = ScriptedModelGateway({"attacks": []})
    store = InMemoryRunStore()
    memory = Memory(ALL)
    ids_ = (f"event-{n}" for n in itertools.count())
    use_case = PlanChangeUseCase(
        PlanChangeDependencies(
            inspector=GitRepositoryInspector({"cartwheel": repo.path}),
            planner=AttackPlanner(gateway, FakeOracleRegistry(), "x", PlanningLimits()),
            store=store,
            targets=StaticTargetCatalog(),
            clock=lambda: LATER,
            new_event_id=lambda: next(ids_),
            memory=memory,
        )
    )
    change = ChangeRequest(
        repository_id="cartwheel", base_sha=repo.base, head_sha=repo.ui_head,
        fixture_id="baseline-v1", target_id="cartwheel-fixture", max_cost_usd_cents=500,
    )  # fmt: skip
    asyncio.run(use_case.execute("run-001", change, as_of=as_of))
    return gateway, store, memory


def test_planner_receives_verified_memory_with_provenance(demo_repo: DemoRepo) -> None:
    gateway, store, memory = plan_with_memory(demo_repo, as_of=LATER)
    payload = json.loads(gateway.requests[0].user)
    assert [m["fact_id"] for m in payload["verified_memory"]] == ["mem-090"]
    assert payload["verified_memory"][0]["source"]["finding_id"] == "finding-001"
    assert memory.queries[0].lens == "planner" and memory.queries[0].as_of == LATER
    assert store.events["run-001"][1].payload["memory_fact_ids"] == "mem-090"


def test_historical_planning_cannot_see_future_findings(demo_repo: DemoRepo) -> None:
    gateway, store, _ = plan_with_memory(demo_repo, as_of=DISCOVERED - timedelta(days=1))
    assert json.loads(gateway.requests[0].user)["verified_memory"] == []
    assert store.events["run-001"][1].payload["memory_fact_ids"] is None
