"""Gate run composition for the API.

Offline mode replays the committed golden recording through the real UI worker, oracle registry
and `classify_gate` (see routes/offline_gate.py). Changes without a recording are `not_tested`,
never passed. The live path (Daytona + Anchor + model planner) is Session 1's run use case and
is refused here with the missing env var names until it is wired.
"""

import difflib
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from pathlib import Path

from gauntlet.application.gate import fix_plan_hash
from gauntlet.contracts import AttackSpec, Finding, FixPlan, RunEvent
from gauntlet.domain import Attribution, GateStatus, Severity

from ..routes.offline_gate import FIXTURES, RUNS, run_offline_gate
from ..schemas import (
    AttemptView,
    ChangeOption,
    FileDiff,
    FixPlanView,
    GateRunSummary,
    GateRunView,
    Provenance,
)
from ..settings import REPO_ROOT, ApiSettings

TEMPLATES = REPO_ROOT / "apps/cartwheel/fixture"
OFFLINE_RECORDING = Provenance(
    provider="golden-recording",
    mode="offline_recording",
    live=False,
    label="OFFLINE RECORDING: golden observations replayed through the real UI worker and "
    "oracle; no Daytona sandbox or Anchor browser was run",
)
TEMPLATE_DIFF = Provenance(
    provider="cartwheel-templates",
    mode="offline_fixture",
    live=False,
    label="Diff computed from the committed Cartwheel fixture templates",
)
SAMPLE_FIX = Provenance(
    provider="sample-fix-plan",
    mode="offline_fixture",
    live=False,
    label="OFFLINE: hand-written sample fix plan for review UI; repair runner live NOT RUN",
)


@dataclass(frozen=True)
class ChangeDef:
    change_id: str
    feature_intent: str
    base_dir: str
    overlay_dir: str
    has_recording: bool


CHANGES: dict[str, ChangeDef] = {
    "help-button": ChangeDef("help-button", "Add a floating Help button", "base", "head", True),
    "refund-tool": ChangeDef(
        "refund-tool",
        "Let the support assistant request refunds for an order",
        "refund-base",
        "refund-head",
        False,
    ),
    "clean": ChangeDef("clean", "Clarify the product description", "base", "clean", False),
}


def _source(base_dir: str, rel: str) -> Path | None:
    """The file as it exists at the change's base (refund-base sits on top of base)."""
    for layer in [base_dir, "base"] if base_dir != "base" else ["base"]:
        candidate = TEMPLATES / layer / rel
        if candidate.is_file():
            return candidate
    return None


def template_diff(change: ChangeDef) -> list[FileDiff]:
    overlay = TEMPLATES / change.overlay_dir
    diffs: list[FileDiff] = []
    for path in sorted(p for p in overlay.rglob("*") if p.is_file()):
        rel = path.relative_to(overlay).as_posix()
        before_path = _source(change.base_dir, rel)
        before = before_path.read_text().splitlines(keepends=True) if before_path else []
        after = path.read_text().splitlines(keepends=True)
        text = "".join(
            difflib.unified_diff(before, after, f"a/{rel}", f"b/{rel}" if after else "/dev/null")
        )
        if text:
            diffs.append(FileDiff(path=rel, unified_diff=text))
    return diffs


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


SAMPLE_FIX_DIFF = """--- a/src/components/FloatingHelp.module.css
+++ b/src/components/FloatingHelp.module.css
@@ -1,12 +1,6 @@
 .floatingHelp {
   position: fixed;
-  bottom: 16px;
+  bottom: 96px;
   right: 16px;
   z-index: 50;
 }
-
-@media (min-width: 900px) {
-  .floatingHelp {
-    bottom: 96px;
-  }
-}
"""


@dataclass
class GateRunRecord:
    view: GateRunView
    created_at: datetime


@dataclass
class GateService:
    settings: ApiSettings
    manifests: dict[str, dict[str, str]]
    runs: dict[str, GateRunRecord] = field(default_factory=dict)
    _ids: "count[int]" = field(default_factory=lambda: count(1))

    def changes(self) -> list[ChangeOption]:
        return [
            ChangeOption(
                change_id=c.change_id,
                feature_intent=c.feature_intent,
                base_sha=self.manifests[c.change_id]["base_sha"],
                head_sha=self.manifests[c.change_id]["head_sha"],
                offline_recording_available=c.has_recording,
            )
            for c in CHANGES.values()
        ]

    def missing_live_env(self) -> list[str]:
        missing = [*self.settings.missing_env("daytona"), *self.settings.missing_env("anchor")]
        missing += self.settings.missing_env(
            "azure_openai" if self.settings.model_provider == "azure" else "bedrock"
        )
        if not self.settings.run_live_integrations:
            missing.append("RUN_LIVE_INTEGRATIONS=1")
        return missing

    async def start(self, change_id: str) -> GateRunView:
        change = CHANGES[change_id]
        refs = self.manifests[change_id]
        run_id = f"run-{change_id}-{next(self._ids):03d}"
        now = datetime.now(UTC)
        diff = template_diff(change)
        if not change.has_recording:
            view = GateRunView(
                run_id=run_id,
                change_id=change_id,
                feature_intent=change.feature_intent,
                target_id=refs["target_id"],
                fixture_id=refs["fixture_id"],
                base_sha=refs["base_sha"],
                head_sha=refs["head_sha"],
                status=GateStatus.NOT_TESTED.value,
                attribution=Attribution.UNKNOWN.value,
                not_tested_reason=(
                    "No offline recording exists for this change. A live run needs: "
                    + ", ".join(self.missing_live_env())
                    + ". Not tested does not mean safe."
                ),
                diff=diff,
                frozen_plan=None,
                plan_sha256=None,
                attempts=[],
                findings=[],
                fix_plan=None,
                events=[self._event(run_id, 1, "run_not_tested", now, {"reason": "no_recording"})],
                provenance=[TEMPLATE_DIFF],
            )
            self.runs[run_id] = GateRunRecord(view, now)
            return view

        offline = await run_offline_gate()
        plan = AttackSpec.model_validate_json(FIXTURES.joinpath("ui-plan.v1.json").read_bytes())
        plan_json = json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        attempts: list[AttemptView] = []
        per_revision: dict[str, int] = {}
        for (revision, sha, _), outcome in zip(RUNS, offline.oracle_outcomes, strict=True):
            per_revision[revision] = per_revision.get(revision, 0) + 1
            attempts.append(
                AttemptView(
                    revision=revision,  # type: ignore[arg-type]
                    attempt=per_revision[revision],
                    source_sha=sha,
                    oracle_id="ui.primary_action_reachable",
                    outcome=outcome,
                    evidence_ids=["art-shot-001"],
                    screenshot_artifact_ids=[],
                    provenance=OFFLINE_RECORDING,
                )
            )
        head = [a for a in attempts if a.revision == "head"]
        base = [a for a in attempts if a.revision == "base"]
        status = GateStatus(offline.status)
        finding = Finding(
            finding_id=f"{run_id}:finding-001",
            attack_id=plan.attack_id,
            status=status,
            attribution=Attribution(offline.attribution)
            if offline.attribution in {a.value for a in Attribution}
            else Attribution.UNKNOWN,
            severity=Severity.HIGH,
            oracle_ids=tuple(plan.oracle_ids),
            oracle_verdict_ids=(f"{run_id}:oracle-head-1", f"{run_id}:oracle-head-2"),
            head_reproductions=sum(a.outcome == "fail" for a in head),
            head_attempts=len(head),
            base_reproductions=sum(a.outcome == "fail" for a in base),
            base_attempts=len(base),
            evidence_ids=("art-shot-001",),
            limitations=(
                "Offline golden recording: no Daytona sandbox or Anchor browser was run",
                "Recorded SHAs are golden placeholders, not the registered Cartwheel SHAs",
            ),
        )
        fix = FixPlan(
            fix_plan_id=f"{run_id}:fix-001",
            run_id=run_id,
            finding_id=finding.finding_id,
            base_sha=refs["head_sha"],
            allowed_paths=("src/components/FloatingHelp.module.css",),
            unified_diff=SAMPLE_FIX_DIFF,
            rationale="Keep the Help button above the Checkout action at every width.",
            test_plan=(
                "Replay attack-ui-001 at 375x812 on the patched head: Checkout receives the click",
                "Legitimate: Help button still opens the help dialog",
                "Base and desktop widths unchanged",
            ),
            created_at=now,
        )
        events = [
            e.model_copy(update={"run_id": run_id, "idempotency_key": f"{run_id}:{e.event_type}"})
            for e in offline.events
        ]
        view = GateRunView(
            run_id=run_id,
            change_id=change_id,
            feature_intent=change.feature_intent,
            target_id=refs["target_id"],
            fixture_id=plan.fixture_id,
            base_sha=refs["base_sha"],
            head_sha=refs["head_sha"],
            status=status.value,
            attribution=finding.attribution.value,
            not_tested_reason=None,
            diff=diff,
            frozen_plan=plan,
            plan_sha256=_sha(plan_json),
            attempts=attempts,
            findings=[finding],
            fix_plan=FixPlanView(
                plan=fix,
                plan_sha256=fix_plan_hash(fix),
                allowed_paths=list(fix.allowed_paths),
                provenance=SAMPLE_FIX,
            ),
            events=events,
            provenance=[OFFLINE_RECORDING, TEMPLATE_DIFF, SAMPLE_FIX],
        )
        self.runs[run_id] = GateRunRecord(view, now)
        return view

    def append_event(
        self, run_id: str, event_type: str, payload: dict[str, str | int | float | bool | None]
    ) -> None:
        record = self.runs[run_id]
        seq = (record.view.events[-1].sequence + 1) if record.view.events else 1
        event = self._event(run_id, seq, event_type, datetime.now(UTC), payload)
        record.view = record.view.model_copy(update={"events": [*record.view.events, event]})

    @staticmethod
    def _event(
        run_id: str,
        sequence: int,
        event_type: str,
        at: datetime,
        payload: dict[str, str | int | float | bool | None],
    ) -> RunEvent:
        return RunEvent(
            event_id=f"{run_id}:event-{sequence:03d}",
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            actor="gauntlet-api",
            created_at=at,
            payload=payload,
        )

    def summaries(self) -> list[GateRunSummary]:
        return [
            GateRunSummary(
                run_id=r.view.run_id,
                change_id=r.view.change_id,
                status=r.view.status,
                attribution=r.view.attribution,
                offline=not any(p.live for p in r.view.provenance),
            )
            for r in sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)
        ]
