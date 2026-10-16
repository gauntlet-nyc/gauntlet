"""Pure paired UI Gate adjudication from trusted, typed execution records.

The caller supplies artifacts read from the trusted store. This module checks their
bytes and bindings again; a serialized execution report is never a verdict input.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet.contracts import (
    AttackSpec,
    ChangeRequest,
    EvidenceSubject,
    Observation,
    OracleVerdict,
)
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


@dataclass(frozen=True)
class GateAttempt:
    subject: EvidenceSubject
    observation: Observation
    verdicts: tuple[OracleVerdict, ...]
    artifacts: tuple[StoredArtifact, ...]


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
    attempt: GateAttempt, *, attack: AttackSpec, run_id: str, sha: str, checksum: str
) -> tuple[OracleOutcome | None, str | None]:
    subject, obs = attempt.subject, attempt.observation
    if (
        subject.run_id != run_id
        or subject.collector != "browser_collector"
        or subject.step_index is not None
        or subject.source_sha != sha
        or obs.source_sha != sha
        or subject.fixture_checksum != checksum
        or obs.fixture_checksum != checksum
        or subject.observation_id != obs.observation_id
        or subject.environment_id != obs.environment_id
        or obs.attack_id != attack.attack_id
    ):
        return None, "attempt identity, source, or fixture differs from the frozen pair"
    if obs.status == "environment_error":
        return None, "attempt reported an environment error"
    if obs.status != "completed":
        return None, "attempt did not complete"
    if len(obs.action_log) != len(attack.steps) or any(
        record.step_index != index or record.action != step.action
        for index, (step, record) in enumerate(zip(attack.steps, obs.action_log, strict=True))
    ):
        return None, "action log does not match the frozen attack"
    action_artifacts = tuple(
        artifact_id for record in obs.action_log for artifact_id in record.evidence_ids
    )
    if (
        len(set(action_artifacts)) != len(action_artifacts)
        or len(set(obs.evidence_ids)) != len(obs.evidence_ids)
        or set(obs.evidence_ids) != set(action_artifacts)
    ):
        return None, "observation evidence IDs do not match action records"
    if len(attempt.verdicts) != 1:
        return None, "one oracle verdict is required per UI attempt"
    oracle = attempt.verdicts[0]
    if (
        oracle.oracle_id != attack.oracle_ids[0]
        or oracle.observation_id != obs.observation_id
        or oracle.outcome is OracleOutcome.INCONCLUSIVE
    ):
        return None, "oracle verdict is missing, inconclusive, or mismatched"
    if oracle.oracle_kind is not OracleKind.HARD:
        return None, "oracle is not hard"
    if not oracle.evidence_ids or len(set(oracle.evidence_ids)) != len(oracle.evidence_ids):
        return None, "hard oracle verdict lacks distinct evidence"
    artifacts = {item.binding.evidence.artifact_id: item for item in attempt.artifacts}
    if len(artifacts) != len(attempt.artifacts):
        return None, "duplicate artifact ID"
    for artifact_id in oracle.evidence_ids:
        item = artifacts.get(artifact_id)
        if item is None or artifact_id not in obs.evidence_ids:
            return None, "hard oracle evidence is missing from the observation or store"
        binding = item.binding
        if (
            binding.byte_size != len(item.content)
            or binding.evidence.sha256 != hashlib.sha256(item.content).hexdigest()
        ):
            return None, "hard oracle evidence bytes differ from their stored binding"
        matching_steps = [
            record.step_index for record in obs.action_log if artifact_id in record.evidence_ids
        ]
        if len(matching_steps) != 1 or binding.subject != subject.model_copy(
            update={"step_index": matching_steps[0]}
        ):
            return None, "hard oracle evidence is bound to a different attempt or step"
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
    if attack.worker_kind != "ui" or attack.oracle_ids != (_UI_ORACLE_ID,):
        raise ValueError("paired UI adjudication requires the registered UI oracle")
    if attack.target_id != change.target_id or attack.fixture_id != change.fixture_id:
        raise ValueError("attack target or fixture differs from the change")
    if not attack.source_refs or any(ref.sha != change.head_sha for ref in attack.source_refs):
        raise ValueError("attack source references must bind to the head revision")
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
                attempt, attack=attack, run_id=run_id, sha=sha, checksum=fixture_checksum
            )
            if reason:
                complete = False
                limitations.append(f"{side}: {reason}")
                if side == "head" and any(
                    verdict.outcome is OracleOutcome.FAIL for verdict in attempt.verdicts
                ):
                    unverified_head_failure = True
                if "environment error" in reason or "source, or fixture" in reason:
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
