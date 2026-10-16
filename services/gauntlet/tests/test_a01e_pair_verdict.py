"""Paired UI claims require separate, bound hard-oracle attempts on both revisions."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gauntlet.application.gate.pair_verdict import (
    AttemptRejection,
    GateAttempt,
    PairedGateVerdict,
    adjudicate_ui_pair,
)
from gauntlet.contracts import (
    ActionRecord,
    AttackSpec,
    ChangeRequest,
    EvidenceBinding,
    EvidenceRef,
    EvidenceSubject,
    Observation,
    OracleVerdict,
)
from gauntlet.domain import Attribution, GateStatus, OracleKind, OracleOutcome
from gauntlet.ports.artifacts import StoredArtifact

ROOT = Path(__file__).resolve().parents[3]
HEAD = "a" * 40
BASE = "b" * 40
CHECKSUM = "c" * 64
WHEN = datetime(2026, 10, 14, tzinfo=UTC)
ATTACK = AttackSpec.model_validate_json(
    (ROOT / "docs/contracts/examples/ui-plan.v1.json").read_text()
)
ATTACK = ATTACK.model_copy(
    update={
        "source_refs": tuple(ref.model_copy(update={"sha": HEAD}) for ref in ATTACK.source_refs)
    }
)
CHANGE = ChangeRequest(
    repository_id="cartwheel",
    base_sha=BASE,
    head_sha=HEAD,
    fixture_id=ATTACK.fixture_id,
    target_id=ATTACK.target_id,
    max_cost_usd_cents=100,
)


def attempt(side: str, index: int, outcome: OracleOutcome) -> GateAttempt:
    sha = HEAD if side == "head" else BASE
    label = f"{side}-{index}"
    artifact_id = f"artifact-{label}"
    content = json.dumps({"label": label}).encode()
    subject = EvidenceSubject(
        run_id="run-pair",
        attempt_id=f"attempt-{label}",
        observation_id=f"observation-{label}",
        environment_id=f"environment-{side}",
        source_sha=sha,
        fixture_checksum=CHECKSUM,
        collector="browser_collector",
    )
    records = tuple(
        ActionRecord(
            step_index=i,
            action=step.action,
            outcome="blocked" if i == 3 and outcome is OracleOutcome.FAIL else "ok",
            evidence_ids=(artifact_id,) if i == 3 else (),
        )
        for i, step in enumerate(ATTACK.steps)
    )
    observation = Observation(
        observation_id=subject.observation_id,
        attack_id=ATTACK.attack_id,
        environment_id=subject.environment_id,
        source_sha=sha,
        fixture_checksum=CHECKSUM,
        status="completed",
        action_log=records,
        evidence_ids=(artifact_id,),
    )
    oracle = OracleVerdict(
        verdict_id=f"verdict-{label}",
        oracle_id=ATTACK.oracle_ids[0],
        oracle_kind=OracleKind.HARD,
        criterion_version="1.0",
        observation_id=subject.observation_id,
        outcome=outcome,
        observed="trusted result",
        expected="primary action receives click",
        evidence_ids=(artifact_id,),
    )
    binding = EvidenceBinding(
        evidence=EvidenceRef(
            artifact_id=artifact_id,
            sha256=hashlib.sha256(content).hexdigest(),
            media_type="application/json",
            created_at=WHEN,
        ),
        subject=subject.model_copy(update={"step_index": 3}),
        byte_size=len(content),
        recorded_at=WHEN,
    )
    return GateAttempt(subject, observation, (oracle,), (StoredArtifact(binding, content),))


def pair(head: tuple[GateAttempt, ...], base: tuple[GateAttempt, ...]) -> PairedGateVerdict:
    return adjudicate_ui_pair(
        change=CHANGE,
        attack=ATTACK,
        run_id="run-pair",
        fixture_checksum=CHECKSUM,
        head=head,
        base=base,
    )


def test_two_head_failures_and_two_base_passes_are_introduced() -> None:
    result = pair(
        (attempt("head", 1, OracleOutcome.FAIL), attempt("head", 2, OracleOutcome.FAIL)),
        (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS)),
    )
    assert result.verdict.status is GateStatus.CONFIRMED_REGRESSION
    assert result.verdict.attribution is Attribution.INTRODUCED
    assert result.head_attempts == result.head_failures == 2
    assert result.base_attempts == 2 and result.base_failures == 0
    assert len(result.oracle_verdict_ids) == len(result.evidence_ids) == 2


def test_two_failures_on_both_revisions_are_preexisting() -> None:
    result = pair(
        (attempt("head", 1, OracleOutcome.FAIL), attempt("head", 2, OracleOutcome.FAIL)),
        (attempt("base", 1, OracleOutcome.FAIL), attempt("base", 2, OracleOutcome.FAIL)),
    )
    assert result.verdict.status is GateStatus.CONFIRMED_PRE_EXISTING
    assert result.verdict.attribution is Attribution.PRE_EXISTING


def test_single_base_pass_cannot_confirm_regression() -> None:
    result = pair(
        (attempt("head", 1, OracleOutcome.FAIL), attempt("head", 2, OracleOutcome.FAIL)),
        (attempt("base", 1, OracleOutcome.PASS),),
    )
    assert result.verdict.status is GateStatus.SUSPECTED


def test_only_soft_oracle_failures_are_suspected() -> None:
    head = tuple(
        GateAttempt(
            item.subject,
            item.observation,
            (item.verdicts[0].model_copy(update={"oracle_kind": OracleKind.MODEL_ONLY}),),
            item.artifacts,
        )
        for item in (attempt("head", 1, OracleOutcome.FAIL), attempt("head", 2, OracleOutcome.FAIL))
    )
    base = (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS))
    assert pair(head, base).verdict.status is GateStatus.SUSPECTED


@pytest.mark.parametrize("bad", ["soft", "missing", "corrupt", "bound_to_other_attempt"])
def test_untrusted_head_support_cannot_confirm(bad: str) -> None:
    first = attempt("head", 1, OracleOutcome.FAIL)
    second = attempt("head", 2, OracleOutcome.FAIL)
    if bad == "soft":
        second = GateAttempt(
            second.subject,
            second.observation,
            (second.verdicts[0].model_copy(update={"oracle_kind": OracleKind.MODEL_ONLY}),),
            second.artifacts,
        )
    elif bad == "missing":
        second = GateAttempt(second.subject, second.observation, second.verdicts, ())
    elif bad == "corrupt":
        second = GateAttempt(
            second.subject,
            second.observation,
            second.verdicts,
            (StoredArtifact(second.artifacts[0].binding, b"changed"),),
        )
    else:
        item = second.artifacts[0]
        wrong = item.binding.model_copy(
            update={
                "subject": item.binding.subject.model_copy(update={"attempt_id": "attempt-other"})
            }
        )
        second = GateAttempt(
            second.subject,
            second.observation,
            second.verdicts,
            (StoredArtifact(wrong, item.content),),
        )
    result = pair(
        (first, second),
        (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS)),
    )
    assert result.verdict.status is GateStatus.SUSPECTED
    assert result.head_failures == 1


def test_mismatched_source_or_fixture_is_environment_error() -> None:
    good = attempt("head", 1, OracleOutcome.FAIL)
    wrong = attempt("head", 2, OracleOutcome.FAIL)
    wrong = GateAttempt(
        wrong.subject.model_copy(update={"source_sha": BASE}),
        wrong.observation,
        wrong.verdicts,
        wrong.artifacts,
    )
    result = pair(
        (good, wrong),
        (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS)),
    )
    assert result.verdict.status is GateStatus.ENVIRONMENT_ERROR


def test_aborted_or_duplicate_attempt_blocks_confirmation() -> None:
    first = attempt("head", 1, OracleOutcome.FAIL)
    aborted = attempt("head", 2, OracleOutcome.FAIL)
    aborted = GateAttempt(
        aborted.subject,
        aborted.observation.model_copy(update={"status": "aborted"}),
        aborted.verdicts,
        aborted.artifacts,
    )
    base = (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS))
    assert pair((first, aborted), base).verdict.status is GateStatus.SUSPECTED
    assert pair((first, first), base).verdict.status is GateStatus.SUSPECTED


def test_extra_incomplete_attempt_blocks_otherwise_confirming_pair() -> None:
    head = (
        attempt("head", 1, OracleOutcome.FAIL),
        attempt("head", 2, OracleOutcome.FAIL),
    )
    extra = attempt("head", 3, OracleOutcome.FAIL)
    extra = GateAttempt(
        extra.subject,
        extra.observation.model_copy(update={"status": "aborted"}),
        extra.verdicts,
        extra.artifacts,
    )
    base = (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS))
    assert pair((*head, extra), base).verdict.status is GateStatus.SUSPECTED


def test_environment_error_attempt_blocks_otherwise_confirming_pair() -> None:
    head = (
        attempt("head", 1, OracleOutcome.FAIL),
        attempt("head", 2, OracleOutcome.FAIL),
    )
    error = attempt("base", 3, OracleOutcome.PASS)
    error = GateAttempt(
        error.subject,
        error.observation.model_copy(update={"status": "environment_error"}),
        error.verdicts,
        error.artifacts,
    )
    base = (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS))
    assert pair(head, (*base, error)).verdict.status is GateStatus.ENVIRONMENT_ERROR


def test_absent_head_is_not_tested() -> None:
    result = pair(
        (), (attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS))
    )
    assert result.verdict.status is GateStatus.NOT_TESTED


def test_absent_head_with_base_failures_is_still_not_tested() -> None:
    base = (attempt("base", 1, OracleOutcome.FAIL), attempt("base", 2, OracleOutcome.FAIL))
    assert pair((), base).verdict.status is GateStatus.NOT_TESTED


def test_attack_citing_a_base_line_is_adjudicated_not_rejected() -> None:
    # The plan validator accepts base citations (e.g. a removed guard line).
    cited_base = ATTACK.model_copy(
        update={"source_refs": (ATTACK.source_refs[0].model_copy(update={"sha": BASE}),)}
    )
    result = adjudicate_ui_pair(
        change=CHANGE,
        attack=cited_base,
        run_id="run-pair",
        fixture_checksum=CHECKSUM,
        head=(attempt("head", 1, OracleOutcome.FAIL), attempt("head", 2, OracleOutcome.FAIL)),
        base=(attempt("base", 1, OracleOutcome.PASS), attempt("base", 2, OracleOutcome.PASS)),
    )
    assert result.verdict.status is GateStatus.CONFIRMED_REGRESSION


def test_attack_citing_an_unrelated_revision_is_rejected() -> None:
    foreign = ATTACK.model_copy(
        update={"source_refs": (ATTACK.source_refs[0].model_copy(update={"sha": "d" * 40}),)}
    )
    with pytest.raises(ValueError, match="base or head"):
        adjudicate_ui_pair(
            change=CHANGE,
            attack=foreign,
            run_id="run-pair",
            fixture_checksum=CHECKSUM,
            head=(),
            base=(),
        )


def test_environment_classification_uses_typed_reasons() -> None:
    assert AttemptRejection.IDENTITY_MISMATCH.is_environment_problem
    assert AttemptRejection.ENVIRONMENT_ERROR.is_environment_problem
    assert not any(
        reason.is_environment_problem
        for reason in AttemptRejection
        if reason
        not in {AttemptRejection.IDENTITY_MISMATCH, AttemptRejection.ENVIRONMENT_ERROR}
    )
