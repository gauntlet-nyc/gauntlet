"""Pure paired UI Gate adjudication from trusted, typed execution records.

The caller supplies artifacts read from the trusted store. This module checks their
bytes and bindings again; a serialized execution report is never a verdict input.
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from gauntlet.contracts import (
    AttackSpec,
    ChangeRequest,
    EvidenceSubject,
    Observation,
    OracleVerdict,
    WorkerKind,
)
from gauntlet.contracts.evidence import EvidenceCollector
from gauntlet.domain import (
    GateEvidence,
    GateVerdict,
    OracleKind,
    OracleOutcome,
    classify_gate,
)
from gauntlet.ports.artifacts import StoredArtifact

_MIN_PAIR_ATTEMPTS = 2
_UI_ORACLE_ID = "ui.primary_action_reachable"
_AGENT_ORACLE_ID = "agent.refund_authorized"


class AttemptRejection(StrEnum):
    """Typed reason an attempt cannot count. Only the environment reasons void the pair."""

    IDENTITY_MISMATCH = "attempt identity, source, or fixture differs from the frozen pair"
    ENVIRONMENT_ERROR = "attempt reported an environment error"
    INCOMPLETE = "attempt did not complete"
    ACTION_LOG_MISMATCH = "action log does not match the frozen attack"
    EVIDENCE_ID_MISMATCH = "observation evidence IDs do not match action records"
    VERDICT_COUNT = "one oracle verdict is required per attempt"
    VERDICT_MISMATCH = "oracle verdict is missing, inconclusive, or mismatched"
    SOFT_ORACLE = "oracle is not hard"
    EVIDENCE_NOT_DISTINCT = "hard oracle verdict lacks distinct evidence"
    DUPLICATE_ARTIFACT = "duplicate artifact ID"
    EVIDENCE_MISSING = "hard oracle evidence is missing from the observation or store"
    EVIDENCE_BYTES = "hard oracle evidence bytes differ from their stored binding"
    EVIDENCE_BINDING = "hard oracle evidence is bound to a different attempt or step"

    @property
    def is_environment_problem(self) -> bool:
        return self in _ENVIRONMENT_REJECTIONS


_ENVIRONMENT_REJECTIONS = frozenset(
    {AttemptRejection.IDENTITY_MISMATCH, AttemptRejection.ENVIRONMENT_ERROR}
)


@dataclass(frozen=True)
class GateAttempt:
    subject: EvidenceSubject
    observation: Observation
    verdicts: tuple[OracleVerdict, ...]
    artifacts: tuple[StoredArtifact, ...]


PairAdjudicatorFn = Callable[..., "PairedGateVerdict"]


@dataclass(frozen=True)
class PairedGateVerdict:
    verdict: GateVerdict
    head_attempts: int
    head_failures: int
    base_attempts: int
    base_failures: int
    oracle_verdict_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    limitations: tuple[str, ...]


def _checked_outcome(
    attempt: GateAttempt,
    *,
    attack: AttackSpec,
    run_id: str,
    sha: str,
    checksum: str,
    collector: EvidenceCollector,
) -> tuple[OracleOutcome | None, AttemptRejection | None]:
    subject, obs = attempt.subject, attempt.observation
    if (
        subject.run_id != run_id
        or subject.collector != collector
        or subject.step_index is not None
        or subject.source_sha != sha
        or obs.source_sha != sha
        or subject.fixture_checksum != checksum
        or obs.fixture_checksum != checksum
        or subject.observation_id != obs.observation_id
        or subject.environment_id != obs.environment_id
        or obs.attack_id != attack.attack_id
    ):
        return None, AttemptRejection.IDENTITY_MISMATCH
    if obs.status == "environment_error":
        return None, AttemptRejection.ENVIRONMENT_ERROR
    if obs.status != "completed":
        return None, AttemptRejection.INCOMPLETE
    if len(obs.action_log) != len(attack.steps) or any(
        record.step_index != index or record.action != step.action
        for index, (step, record) in enumerate(zip(attack.steps, obs.action_log, strict=True))
    ):
        return None, AttemptRejection.ACTION_LOG_MISMATCH
    action_artifacts = tuple(
        artifact_id for record in obs.action_log for artifact_id in record.evidence_ids
    )
    if (
        len(set(action_artifacts)) != len(action_artifacts)
        or len(set(obs.evidence_ids)) != len(obs.evidence_ids)
        or set(obs.evidence_ids) != set(action_artifacts)
    ):
        return None, AttemptRejection.EVIDENCE_ID_MISMATCH
    if len(attempt.verdicts) != 1:
        return None, AttemptRejection.VERDICT_COUNT
    oracle = attempt.verdicts[0]
    if (
        oracle.oracle_id != attack.oracle_ids[0]
        or oracle.observation_id != obs.observation_id
        or oracle.outcome is OracleOutcome.INCONCLUSIVE
    ):
        return None, AttemptRejection.VERDICT_MISMATCH
    if oracle.oracle_kind is not OracleKind.HARD:
        return None, AttemptRejection.SOFT_ORACLE
    if not oracle.evidence_ids or len(set(oracle.evidence_ids)) != len(oracle.evidence_ids):
        return None, AttemptRejection.EVIDENCE_NOT_DISTINCT
    artifacts = {item.binding.evidence.artifact_id: item for item in attempt.artifacts}
    if len(artifacts) != len(attempt.artifacts):
        return None, AttemptRejection.DUPLICATE_ARTIFACT
    for artifact_id in oracle.evidence_ids:
        item = artifacts.get(artifact_id)
        if item is None or artifact_id not in obs.evidence_ids:
            return None, AttemptRejection.EVIDENCE_MISSING
        binding = item.binding
        if (
            binding.byte_size != len(item.content)
            or binding.evidence.sha256 != hashlib.sha256(item.content).hexdigest()
        ):
            return None, AttemptRejection.EVIDENCE_BYTES
        matching_steps = [
            record.step_index for record in obs.action_log if artifact_id in record.evidence_ids
        ]
        if len(matching_steps) != 1 or binding.subject != subject.model_copy(
            update={"step_index": matching_steps[0]}
        ):
            return None, AttemptRejection.EVIDENCE_BINDING
    return oracle.outcome, None


def adjudicate_ui_pair(
    *,
    change: ChangeRequest,
    attack: AttackSpec,
    run_id: str,
    fixture_checksum: str,
    head: Sequence[GateAttempt],
    base: Sequence[GateAttempt],
) -> PairedGateVerdict:
    """Classify one unchanged frozen UI attack on head and base.

    The trusted caller must establish the frozen plan and environment provenance
    before supplying these records. This function never executes an attack.
    """
    return _adjudicate_pair(
        change=change,
        attack=attack,
        run_id=run_id,
        fixture_checksum=fixture_checksum,
        head=head,
        base=base,
        worker_kind="ui",
        oracle_id=_UI_ORACLE_ID,
        collector="browser_collector",
    )


def adjudicator_for(
    worker_kind: WorkerKind, oracle_id: str, collector: EvidenceCollector
) -> "PairAdjudicatorFn":
    """Paired adjudication for any registered hard oracle with the same rules."""

    def adjudicate(
        *,
        change: ChangeRequest,
        attack: AttackSpec,
        run_id: str,
        fixture_checksum: str,
        head: Sequence[GateAttempt],
        base: Sequence[GateAttempt],
    ) -> PairedGateVerdict:
        return _adjudicate_pair(
            change=change,
            attack=attack,
            run_id=run_id,
            fixture_checksum=fixture_checksum,
            head=head,
            base=base,
            worker_kind=worker_kind,
            oracle_id=oracle_id,
            collector=collector,
        )

    return adjudicate


def adjudicate_agent_pair(
    *,
    change: ChangeRequest,
    attack: AttackSpec,
    run_id: str,
    fixture_checksum: str,
    head: Sequence[GateAttempt],
    base: Sequence[GateAttempt],
) -> PairedGateVerdict:
    """Same rules for an AI-agent attack judged by the trusted ledger oracle."""
    return _adjudicate_pair(
        change=change,
        attack=attack,
        run_id=run_id,
        fixture_checksum=fixture_checksum,
        head=head,
        base=base,
        worker_kind="ai_agent",
        oracle_id=_AGENT_ORACLE_ID,
        collector="api_collector",
    )


def _adjudicate_pair(
    *,
    change: ChangeRequest,
    attack: AttackSpec,
    run_id: str,
    fixture_checksum: str,
    head: Sequence[GateAttempt],
    base: Sequence[GateAttempt],
    worker_kind: WorkerKind,
    oracle_id: str,
    collector: EvidenceCollector,
) -> PairedGateVerdict:
    if attack.worker_kind != worker_kind or attack.oracle_ids != (oracle_id,):
        raise ValueError(f"paired {worker_kind} adjudication requires its registered oracle")
    if attack.target_id != change.target_id or attack.fixture_id != change.fixture_id:
        raise ValueError("attack target or fixture differs from the change")
    # The plan validator accepts citations of either compared revision (e.g. a removed line).
    if not attack.source_refs or any(
        ref.sha not in {change.head_sha, change.base_sha} for ref in attack.source_refs
    ):
        raise ValueError("attack source references must bind to the base or head revision")
    if change.base_sha == change.head_sha:
        raise ValueError("base and head must be different revisions")

    limitations: list[str] = []
    identities: set[str] = set()
    verdict_ids: list[str] = []
    evidence_ids: list[str] = []
    counts: dict[str, tuple[int, int]] = {}
    environment_ok = True
    complete = True
    unverified_head_failure = False
    for side, sha, attempts in (
        ("head", change.head_sha, head),
        ("base", change.base_sha, base),
    ):
        accepted = 0
        failures = 0
        for attempt in attempts:
            subject = attempt.subject
            ids = [subject.attempt_id, subject.observation_id]
            ids.extend(verdict.verdict_id for verdict in attempt.verdicts)
            ids.extend(item.binding.evidence.artifact_id for item in attempt.artifacts)
            if any(identity in identities for identity in ids) or len(set(ids)) != len(ids):
                complete = False
                limitations.append(f"{side}: duplicate attempt, verdict, or artifact identity")
                continue
            identities.update(ids)
            outcome, reason = _checked_outcome(
                attempt,
                attack=attack,
                run_id=run_id,
                sha=sha,
                checksum=fixture_checksum,
                collector=collector,
            )
            if reason is not None:
                complete = False
                limitations.append(f"{side}: {reason.value}")
                if side == "head" and any(
                    verdict.outcome is OracleOutcome.FAIL for verdict in attempt.verdicts
                ):
                    unverified_head_failure = True
                if reason.is_environment_problem:
                    environment_ok = False
                continue
            assert outcome is not None
            accepted += 1
            if outcome is OracleOutcome.FAIL:
                failures += 1
                verdict_ids.append(attempt.verdicts[0].verdict_id)
                evidence_ids.extend(attempt.verdicts[0].evidence_ids)
        counts[side] = (accepted, failures)

    head_attempts, head_failures = counts["head"]
    base_attempts, base_failures = counts["base"]
    enough_pair = head_attempts >= _MIN_PAIR_ATTEMPTS and base_attempts >= _MIN_PAIR_ATTEMPTS
    if not enough_pair:
        limitations.append(
            "two complete, distinct hard-oracle attempts are required on each revision"
        )
    # An incomplete pair cannot be interpreted as a clean head or attributed regression.
    if not complete or not enough_pair:
        if head_failures == 0:
            classified_head_attempts = 1 if unverified_head_failure else 0
            classified_base_attempts = 0
            classified_base_failures = 0
        else:
            classified_head_attempts = head_attempts
            classified_base_attempts = base_attempts
            classified_base_failures = base_failures
        oracle_trusted = False
    else:
        classified_head_attempts = head_attempts
        classified_base_attempts = base_attempts
        classified_base_failures = base_failures
        oracle_trusted = True
    verdict = classify_gate(
        GateEvidence(
            environment_ok=environment_ok,
            fixtures_equal=environment_ok,
            oracle_trusted=oracle_trusted,
            head_attempts=classified_head_attempts,
            head_failures=max(head_failures, int(unverified_head_failure))
            if not complete or not enough_pair
            else head_failures,
            base_attempts=classified_base_attempts,
            base_failures=classified_base_failures,
        )
    )
    return PairedGateVerdict(
        verdict=verdict,
        head_attempts=head_attempts,
        head_failures=head_failures,
        base_attempts=base_attempts,
        base_failures=base_failures,
        oracle_verdict_ids=tuple(verdict_ids),
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        limitations=tuple(dict.fromkeys(limitations)),
    )
