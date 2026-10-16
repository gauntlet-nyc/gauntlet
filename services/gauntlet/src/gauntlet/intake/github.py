"""GitHub App intake: verify webhooks, map PR events to runs, render check-run reports.

The webhook body is untrusted until its HMAC verifies, and its PR title is untrusted even
after. Only repositories bound server-side to a registered target can start a run. The
check result is a recommendation; Gauntlet never pushes, merges, approves or comments.
"""

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gauntlet.contracts import ChangeRequest, Finding
from gauntlet.domain import CONFIRMED_GATE_STATUSES, GateStatus
from gauntlet.ports import CheckConclusion, CheckRunReport

SIGNATURE_PREFIX: Final = "sha256="
HANDLED_ACTIONS: Final = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})
CHECK_NAME: Final = "Gauntlet"
_MAX_TITLE: Final = 2048


def verify_signature(secret: bytes, body: bytes, signature_header: str | None) -> bool:
    """Constant-time check of GitHub's `X-Hub-Signature-256` header."""
    if not secret or not signature_header or not signature_header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[len(SIGNATURE_PREFIX) :])


class _GitHubModel(BaseModel):
    """External payloads carry many fields we do not use; ignore them, keep ours frozen."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class _Ref(_GitHubModel):
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class _PullRequest(_GitHubModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=10_000)
    draft: bool = False
    head: _Ref
    base: _Ref


class _Repository(_GitHubModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class _Installation(_GitHubModel):
    id: int = Field(ge=1)


class PullRequestEvent(_GitHubModel):
    action: str
    pull_request: _PullRequest
    repository: _Repository
    installation: _Installation | None = None


@dataclass(frozen=True)
class RepositoryBinding:
    """Server-side allowlist entry: which GitHub repo maps to which registered target."""

    repository_id: str
    target_id: str
    fixture_id: str
    max_cost_usd_cents: int


@dataclass(frozen=True)
class RunRequested:
    run_id: str
    change: ChangeRequest
    repository_full_name: str
    pull_number: int
    head_sha: str


@dataclass(frozen=True)
class EventIgnored:
    reason: str


def _run_id(full_name: str, number: int, head_sha: str) -> str:
    digest = hashlib.sha256(f"{full_name}#{number}@{head_sha}".encode()).hexdigest()
    return f"gh-{digest[:20]}"


def handle_pull_request_event(
    payload: Mapping[str, object],
    bindings: Mapping[str, RepositoryBinding],
) -> RunRequested | EventIgnored:
    """Call only after `verify_signature` succeeded. Same PR head → same run ID (idempotent)."""
    try:
        event = PullRequestEvent.model_validate(payload)
    except ValidationError:
        return EventIgnored("payload is not a recognisable pull_request event")
    if event.action not in HANDLED_ACTIONS:
        return EventIgnored(f"action '{event.action}' does not start a run")
    if event.pull_request.draft:
        return EventIgnored("draft pull requests are not tested")
    binding = bindings.get(event.repository.full_name)
    if binding is None:
        return EventIgnored("repository is not bound to a registered target")
    pr = event.pull_request
    change = ChangeRequest(
        repository_id=binding.repository_id,
        base_sha=pr.base.sha,
        head_sha=pr.head.sha,
        fixture_id=binding.fixture_id,
        target_id=binding.target_id,
        max_cost_usd_cents=binding.max_cost_usd_cents,
        feature_intent=pr.title[:_MAX_TITLE],
    )
    return RunRequested(
        run_id=_run_id(event.repository.full_name, pr.number, pr.head.sha),
        change=change,
        repository_full_name=event.repository.full_name,
        pull_number=pr.number,
        head_sha=pr.head.sha,
    )


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def render_check_run(
    run_id: str,
    findings: Sequence[Finding],
    coverage_gaps: Sequence[str],
    not_tested_reason: str | None,
    details_url: str | None = None,
) -> CheckRunReport:
    confirmed = [f for f in findings if f.status in CONFIRMED_GATE_STATUSES]
    suspected = [f for f in findings if f.status is GateStatus.SUSPECTED]
    passed = [f for f in findings if f.status is GateStatus.PASSED]
    if confirmed:
        conclusion: CheckConclusion = "failure"
        title = f"{_plural(len(confirmed), 'confirmed issue')} with reproducible evidence"
    elif not findings or not_tested_reason:
        conclusion = "neutral"
        title = "Not tested: " + (not_tested_reason or "no attacks ran")
    elif suspected or coverage_gaps or len(passed) != len(findings):
        conclusion = "neutral"
        title = f"No confirmed issues; {_plural(len(suspected), 'suspected finding')} to review"
    else:
        conclusion = "success"
        title = f"{_plural(len(passed), 'attack')} passed"
    lines = [
        f"**Run** `{run_id}`",
        "",
        "| Finding | Status | Attribution | Severity | Head repro | Base repro |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| `{f.finding_id}` | {f.status} | {f.attribution} | {f.severity} "
        f"| {f.head_reproductions}/{f.head_attempts} | {f.base_reproductions}/{f.base_attempts} |"
        for f in findings
    ]
    if coverage_gaps:
        lines += ["", "**Coverage gaps**", *[f"- {gap}" for gap in coverage_gaps[:20]]]
    lines += [
        "",
        "_Not tested does not mean safe. This is a review recommendation: Gauntlet never "
        "merges, approves or changes this repository._",
    ]
    return CheckRunReport(CHECK_NAME, conclusion, title[:255], "\n".join(lines), details_url)
