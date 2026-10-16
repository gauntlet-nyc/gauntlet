"""P10: one test per enforced authorization policy listed in docs/TENANCY_AND_AUTH.md."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest
from pydantic import ValidationError

from gauntlet.application.errors import TargetNotAuthorizedError
from gauntlet.application.gate import ApprovalService, StaticTargetCatalog
from gauntlet.application.gate.plan_change import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.contracts import (
    ApprovalChannel,
    ApprovalRecord,
    ChangeImpactMap,
    ChangeRequest,
    Finding,
    RecallVerdict,
    TemporalMemoryFact,
)
from gauntlet.domain import Attribution, GateStatus, RecallClassification, Severity
from gauntlet.domain.path_policy import is_patch_path_allowed
from gauntlet.integrations.fake.approvals import InMemoryApprovalStore
from gauntlet.planning import PlanningLimits, select_memory
from gauntlet.planning.plan_validation import PlanValidator
from gauntlet.ports import TargetProfile
from gauntlet.verification.catalog import OracleCatalog
from gauntlet.verification.ledger_oracle import DESCRIPTOR as LEDGER
from gauntlet.verification.registry import RegisteredOracleRegistry

HEAD, BASE = "a" * 40, "b" * 40
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
CHANGE = ChangeRequest(
    repository_id="cartwheel",
    base_sha=BASE,
    head_sha=HEAD,
    fixture_id="baseline-v1",
    target_id="cartwheel-fixture",
    max_cost_usd_cents=100,
)
TARGET = TargetProfile(
    target_id="cartwheel-fixture",
    fixture_ids=frozenset({"baseline-v1"}),
    synthetic_actor_ids=frozenset({"owner-alice"}),
    agent_ids=frozenset({"support-test-agent"}),
    route_prefixes=("/checkout",),
)
REF = {"path": "src/a.css", "sha": HEAD, "start_line": 1, "end_line": 3}
IMPACT = ChangeImpactMap.model_validate(
    {
        "base_sha": BASE,
        "head_sha": HEAD,
        "changed_files": ["src/a.css"],
        "surfaces": [{"kind": "style", "identifier": "a", "source_refs": [REF], "confidence": 0.9}],
    }
)


def attack(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "attack_id": "attack-1",
        "hypothesis": "h",
        "why_this_change": "w",
        "expected_observation": "e",
        "source_refs": [REF],
        "worker_kind": "ui",
        "target_id": "cartwheel-fixture",
        "fixture_id": "baseline-v1",
        "steps": [{"action": "navigate", "path": "/checkout"}],
        "oracle_ids": ["ui.primary_action_reachable"],
        "max_actions": 3,
        "max_runtime_seconds": 30,
    }
    return {**base, **overrides}


def test_unregistered_target_is_refused() -> None:
    use_case = PlanChangeUseCase(
        PlanChangeDependencies(
            inspector=None,  # type: ignore[arg-type]
            planner=None,  # type: ignore[arg-type]
            store=None,  # type: ignore[arg-type]
            targets=StaticTargetCatalog(TARGET),
            clock=lambda: NOW,
            new_event_id=lambda: "e",
        )
    )
    foreign = CHANGE.model_copy(update={"target_id": "someone-else"})
    with pytest.raises(TargetNotAuthorizedError):
        asyncio.run(use_case.execute("run", foreign))
    other_fixture = CHANGE.model_copy(update={"fixture_id": "unregistered"})
    with pytest.raises(TargetNotAuthorizedError):
        asyncio.run(use_case.execute("run", other_fixture))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"oracle_ids": ["made.up_oracle"]}, "not registered"),
        ({"worker_kind": "ai_agent", "oracle_ids": [LEDGER.oracle_id]}, "not allowed"),
        ({"source_refs": [{**REF, "sha": "c" * 40}]}, "base or head"),
        ({"source_refs": [{**REF, "start_line": 50, "end_line": 60}]}, "overlaps"),
        ({"steps": [{"action": "navigate", "path": "/admin"}]}, "registered routes"),
        ({"target_id": "someone-else"}, "authorized target"),
    ],
)
def test_plan_validator_policies(overrides: dict[str, object], reason: str) -> None:
    registry = OracleCatalog(
        [RegisteredOracleRegistry(plans=(), primary_targets={}, evidence=())], LEDGER
    )
    result = PlanValidator(registry, PlanningLimits()).validate(
        json.dumps({"attacks": [attack(**overrides)]}), CHANGE, IMPACT, TARGET
    )
    assert not result.accepted
    assert any(reason in r for r in result.rejected[0].reasons)


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("src/app/page.tsx", True),
        ("api/src/tools/request_refund.ts", True),
        ("api/test/refund.test.ts", False),
        ("services/gauntlet/src/gauntlet/verification/registry.py", False),
        (".github/workflows/ci.yml", False),
        ("pnpm-lock.yaml", False),
        (".env.local", False),
        ("bench/private/truth.json", False),
        ("../outside.ts", False),
    ],
)
def test_patch_path_policy(path: str, allowed: bool) -> None:
    assert is_patch_path_allowed(path) is allowed


def test_approval_policies() -> None:
    assert "voice" not in get_args(ApprovalChannel)
    with pytest.raises(ValidationError):  # longer than 24 hours
        ApprovalRecord(
            approval_id="a",
            run_id="r",
            subject="scope",
            subject_id="s",
            plan_sha256="c" * 64,
            decision="approved",
            reviewer_id="alice",
            channel="api",
            decided_at=NOW,
            expires_at=NOW + timedelta(hours=25),
            target_id="t",
            fixture_id="f",
        )
    with pytest.raises(ValueError):
        ApprovalService(InMemoryApprovalStore(), lambda: NOW, lambda: "x", ttl=timedelta(days=2))


def test_confirmed_finding_needs_evidence() -> None:
    common = {
        "finding_id": "f",
        "attack_id": "a",
        "severity": Severity.HIGH,
        "oracle_ids": ("ui.primary_action_reachable",),
        "base_attempts": 2,
        "base_reproductions": 0,
    }
    with pytest.raises(ValidationError):  # one head reproduction is not confirmation
        Finding(
            **common,  # type: ignore[arg-type]
            status=GateStatus.CONFIRMED_REGRESSION,
            attribution=Attribution.INTRODUCED,
            head_reproductions=1,
            head_attempts=2,
            oracle_verdict_ids=("v",),
            evidence_ids=("e",),
        )
    with pytest.raises(ValidationError):  # no evidence
        Finding(
            **common,  # type: ignore[arg-type]
            status=GateStatus.CONFIRMED_REGRESSION,
            attribution=Attribution.INTRODUCED,
            head_reproductions=2,
            head_attempts=2,
        )


def test_tainted_needs_control_and_material_change() -> None:
    with pytest.raises(ValidationError):
        RecallVerdict(
            verdict_id="v",
            recall_id="r",
            decision_id="d",
            mode="decision_counterfactual",
            classification=RecallClassification.TAINTED,
            rationale="x",
            criterion_version="1.0",
            control_matches=False,
            material_change=True,
            replay_ids=("r1",),
        )


def test_memory_selection_policies() -> None:
    def fact(fact_id: str, **overrides: object) -> TemporalMemoryFact:
        base: dict[str, object] = {
            "fact_id": fact_id,
            "kind": "ui_occlusion",
            "summary": "s",
            "verification": "confirmed",
            "trust": "verified_test",
            "scope": "project/cartwheel-fixture",
            "surface_kinds": ["style"],
            "source": {"finding_id": "f", "oracle_id": "ui.primary_action_reachable"},
            "known_at": NOW - timedelta(days=1),
            "valid_from": NOW - timedelta(days=1),
        }
        return TemporalMemoryFact.model_validate({**base, **overrides})

    good = fact("good")
    future = fact("future", known_at=NOW + timedelta(hours=1))
    unverified = fact("unverified", verification="unverified", trust="app_content", source={})
    old = fact("old")
    newer = fact("newer", supersedes="old")
    chosen = select_memory(
        [good, future, unverified, old, newer], NOW, frozenset({"style"}), limit=10
    )
    assert {f.fact_id for f in chosen} == {"good", "newer"}
