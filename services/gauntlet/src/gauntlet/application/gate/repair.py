"""P3 repair: propose -> freeze + hash -> human approval -> patch in a fresh tree -> re-verify.

* The proposer (model or scripted) only returns a ``FixPlan``. It never writes files.
* The patch runs only after ``ApprovalService.authorize`` accepts an ``ExecutionRequest`` whose
  hash is recomputed from the plan actually being applied and whose touched paths are parsed
  from the diff itself. The approval is spent once.
* Verification re-runs, on the patched revision: the original frozen attack, a variant attack,
  and the normal legitimate workflow. Each runs twice and is judged by the trusted oracle.
* The output is a review-only release verdict. Nothing is merged, pushed or deployed.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol

from gauntlet.contracts import AttackSpec, EvidenceSubject, Finding, FixPlan, Observation
from gauntlet.domain import GateStatus, OracleOutcome, is_patch_path_allowed
from gauntlet.ports import EnvironmentHandle, EnvironmentUnavailableError, SandboxProvider

from .approvals import ApprovalService, ExecutionRequest, fix_plan_hash
from .attempts import AttemptExecutor

_DIFF_PATH: Final = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)$")
_UNSAFE_DIFF: Final = ("GIT binary patch", "rename from", "rename to", "new mode", "old mode")
_ATTEMPTS: Final = 2


class FixProposer(Protocol):
    async def propose(
        self, *, run_id: str, finding: Finding, attack: AttackSpec, head_sha: str
    ) -> FixPlan: ...


@dataclass(frozen=True)
class PatchedRevision:
    patched_sha: str
    touched_paths: tuple[str, ...]


class PatchRunner(Protocol):
    async def apply(self, *, base_sha: str, plan: FixPlan) -> PatchedRevision:
        """Apply ``plan.unified_diff`` in a fresh isolated tree and commit it. Never pushes."""
        ...


SandboxFactory = Callable[[str, str], SandboxProvider]
"""(head_sha, patched_sha) -> a sandbox that may create exactly those two revisions."""


class ReleaseVerdict(StrEnum):
    FIX_VERIFIED_REVIEW_REQUIRED = "fix_verified_review_required"
    FIX_REJECTED = "fix_rejected"
    NOT_VERIFIED = "not_verified"


def diff_paths(unified_diff: str) -> tuple[str, ...]:
    """Every path a unified diff names. Rejects diffs this runner will not apply."""
    if any(marker in unified_diff for marker in _UNSAFE_DIFF):
        raise ValueError("binary, rename and mode-change patches are not applied")
    paths: list[str] = []
    for line in unified_diff.splitlines():
        match = _DIFF_PATH.match(line)
        if match and match.group(1) != "/dev/null":
            paths.append(match.group(1))
    if not paths:
        raise ValueError("diff names no file")
    return tuple(dict.fromkeys(paths))


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RepairReport:
    fix_plan_id: str
    plan_sha256: str
    approval_id: str
    patched_sha: str | None
    touched_paths: tuple[str, ...]
    checks: tuple[CheckResult, ...]
    verdict: ReleaseVerdict
    note: str = "Review only: Gauntlet never merges, pushes or deploys a patch."


@dataclass(frozen=True)
class RepairDependencies:
    proposer: FixProposer
    approvals: ApprovalService
    runner: PatchRunner
    executor: AttemptExecutor
    sandbox_for: SandboxFactory
    clock: Callable[[], datetime]
    new_id: Callable[[str], str]


@dataclass(frozen=True)
class VerificationSuite:
    """Original frozen attack, a variant, and the legitimate workflow that must keep working."""

    original: AttackSpec
    variants: tuple[AttackSpec, ...]
    legitimate: AttackSpec
    legitimate_ok: Callable[[Observation], bool]


class RepairUseCase:
    def __init__(self, deps: RepairDependencies) -> None:
        self._deps = deps

    async def propose(
        self, run_id: str, finding: Finding, attack: AttackSpec, head_sha: str
    ) -> tuple[FixPlan, str]:
        """Return the frozen fix plan and the hash a reviewer must approve."""
        if finding.status not in {
            GateStatus.CONFIRMED_REGRESSION,
            GateStatus.CONFIRMED_POLICY_VIOLATION,
        }:
            raise ValueError("only confirmed findings get a repair plan")
        plan = await self._deps.proposer.propose(
            run_id=run_id, finding=finding, attack=attack, head_sha=head_sha
        )
        paths = diff_paths(plan.unified_diff)
        outside = [p for p in paths if p not in plan.allowed_paths or not is_patch_path_allowed(p)]
        if outside or plan.base_sha != head_sha or plan.run_id != run_id:
            raise ValueError("fix plan touches paths outside its allowlist or wrong revision")
        return plan, fix_plan_hash(plan)

    async def execute(
        self,
        approval_id: str,
        plan: FixPlan,
        *,
        target_id: str,
        fixture_id: str,
        fixture_checksum: str,
        suite: VerificationSuite,
    ) -> RepairReport:
        plan_sha = fix_plan_hash(plan)
        touched = diff_paths(plan.unified_diff)
        await self._deps.approvals.authorize(
            approval_id,
            ExecutionRequest(
                run_id=plan.run_id,
                subject="fix_plan",
                subject_id=plan.fix_plan_id,
                plan_sha256=plan_sha,
                target_id=target_id,
                fixture_id=fixture_id,
                touched_paths=touched,
            ),
        )
        try:
            patched = await self._deps.runner.apply(base_sha=plan.base_sha, plan=plan)
        except (EnvironmentUnavailableError, ValueError) as exc:
            return RepairReport(
                plan.fix_plan_id, plan_sha, approval_id, None, touched,
                (CheckResult("apply", False, str(exc)[:300]),), ReleaseVerdict.NOT_VERIFIED,
            )  # fmt: skip
        if set(patched.touched_paths) - set(touched):
            return RepairReport(
                plan.fix_plan_id, plan_sha, approval_id, patched.patched_sha,
                patched.touched_paths,
                (CheckResult("apply", False, "patch changed files the plan did not name"),),
                ReleaseVerdict.FIX_REJECTED,
            )  # fmt: skip
        checks = await self._verify(
            plan, patched.patched_sha, target_id, fixture_id, fixture_checksum, suite
        )
        if any(c.detail.startswith("environment") for c in checks):
            verdict = ReleaseVerdict.NOT_VERIFIED
        elif all(c.passed for c in checks):
            verdict = ReleaseVerdict.FIX_VERIFIED_REVIEW_REQUIRED
        else:
            verdict = ReleaseVerdict.FIX_REJECTED
        return RepairReport(
            plan.fix_plan_id, plan_sha, approval_id, patched.patched_sha, touched, checks, verdict
        )

    async def _verify(
        self,
        plan: FixPlan,
        patched_sha: str,
        target_id: str,
        fixture_id: str,
        checksum: str,
        suite: VerificationSuite,
    ) -> tuple[CheckResult, ...]:
        sandbox = self._deps.sandbox_for(plan.base_sha, patched_sha)
        results: list[CheckResult] = []
        try:
            environment = await sandbox.create(
                target_id=target_id,
                source_sha=patched_sha,
                fixture_id=fixture_id,
                mode="fix_regression",
            )
        except EnvironmentUnavailableError:
            return (CheckResult("environment", False, "environment for the patch was unavailable"),)
        try:
            if not await sandbox.verify_fixture(environment.environment_id, checksum):
                return (CheckResult("environment", False, "environment fixture differs"),)
            named: Sequence[tuple[str, AttackSpec]] = [
                ("original_attack", suite.original),
                *[(f"variant_{i}", v) for i, v in enumerate(suite.variants)],
            ]
            for name, attack in named:
                outcomes: list[OracleOutcome] = []
                for _ in range(_ATTEMPTS):
                    attempt = await self._deps.executor.attempt(
                        attack, environment, self._subject(plan.run_id, environment)
                    )
                    outcomes.extend(v.outcome for v in attempt.verdicts)
                passed = bool(outcomes) and all(o is OracleOutcome.PASS for o in outcomes)
                results.append(
                    CheckResult(name, passed, ",".join(o.value for o in outcomes) or "no verdict")
                )
            legit: list[bool] = []
            for _ in range(_ATTEMPTS):
                attempt = await self._deps.executor.attempt(
                    suite.legitimate, environment, self._subject(plan.run_id, environment)
                )
                legit.append(
                    suite.legitimate_ok(attempt.observation)
                    and all(v.outcome is OracleOutcome.PASS for v in attempt.verdicts)
                )
            results.append(
                CheckResult(
                    "legitimate_workflow",
                    all(legit),
                    "owner flow still succeeds" if all(legit) else "legitimate flow broke",
                )
            )
        finally:
            await sandbox.destroy(environment.environment_id)
        return tuple(results)

    def _subject(self, run_id: str, environment: EnvironmentHandle) -> EvidenceSubject:
        return EvidenceSubject(
            run_id=run_id,
            attempt_id=self._deps.new_id("fix-attempt"),
            observation_id=self._deps.new_id("fix-observation"),
            environment_id=environment.environment_id,
            source_sha=environment.source_sha,
            fixture_checksum=environment.fixture_checksum,
            collector=self._deps.executor.collector,
        )
