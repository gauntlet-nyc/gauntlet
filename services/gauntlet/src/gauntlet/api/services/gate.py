"""Gate run composition for the API, over Session 1's RunGateUseCase (gauntlet.composition).

Adapters are chosen from settings: live (Azure/Bedrock planner, Daytona, Anchor) only when
RUN_LIVE_INTEGRATIONS=1 and that adapter's env vars are set; otherwise the labelled offline
adapters (scripted planner, fake sandbox, simulated layout browser). Every attempt still goes
through the real planner/validator, plan freeze, UI worker, stored-evidence oracle and pair
verdict. The refund-tool change needs the AI/tool worker, which is not routed yet, so it is
`not_tested`, never passed.
"""

import difflib
import importlib.util
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from types import ModuleType
from typing import Any

from gauntlet.application.gate import fix_plan_hash
from gauntlet.composition import GateTarget, build_gate, readiness
from gauntlet.contracts import FixPlan, RunEvent
from gauntlet.domain import CONFIRMED_GATE_STATUSES, Attribution, GateStatus
from gauntlet.settings import MissingSettingError, Settings

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

Payload = dict[str, str | int | float | bool | None]

TEMPLATES = REPO_ROOT / "apps/cartwheel/fixture"
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
    label="OFFLINE: hand-written sample fix plan for the review UI; repair runner live NOT RUN",
)
_LABEL_TEXT = {
    "offline_scripted": "OFFLINE scripted planner (no model call)",
    "offline_fake": "OFFLINE fake sandbox (no Daytona)",
    "offline_simulated_layout": "OFFLINE simulated layout browser (no Anchor); real oracle path",
    "local_prestarted": "Local pre-started Cartwheel servers (not Daytona)",
    "local_headless_chromium": "Local headless Chromium (not Anchor)",
    "live_azure_openai": "LIVE Azure OpenAI planner",
    "live_bedrock": "LIVE AWS Bedrock planner",
    "live_daytona": "LIVE Daytona sandboxes",
    "live_anchor_with_egress_proxy": "LIVE Anchor browser with egress proxy",
    "live_anchor_no_egress_proxy": "LIVE Anchor browser WITHOUT egress proxy (weaker isolation)",
}


@dataclass(frozen=True)
class ChangeDef:
    change_id: str
    feature_intent: str
    base_dir: str
    overlay_dir: str
    runnable: bool


CHANGES: dict[str, ChangeDef] = {
    "help-button": ChangeDef("help-button", "Add a floating Help button", "base", "head", True),
    "refund-tool": ChangeDef(
        "refund-tool",
        "Let the support assistant request refunds for an order",
        "refund-base",
        "refund-head",
        False,
    ),
    "clean": ChangeDef("clean", "Clarify the product description", "base", "clean", True),
}

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
        text = "".join(difflib.unified_diff(before, after, f"a/{rel}", f"b/{rel}"))
        if text:
            diffs.append(FileDiff(path=rel, unified_diff=text))
    return diffs


def _load_clean_builder() -> ModuleType:
    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "build_cartwheel_clean_fixture", REPO_ROOT / "scripts/build_cartwheel_clean_fixture.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture builder not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _provenance(labels: dict[str, str]) -> list[Provenance]:
    out: list[Provenance] = []
    for part in ("model", "sandbox", "browser"):
        label = labels[part]
        live = label.startswith("live_")
        out.append(
            Provenance(
                provider=f"{part}:{label}",
                mode="live" if live else "offline_recording",
                live=live,
                label=_LABEL_TEXT.get(label, label),
            )
        )
    return out


def _event(run_id: str, sequence: int, event_type: str, payload: Payload) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}:event-{sequence:03d}",
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        actor="gauntlet-api",
        created_at=datetime.now(UTC),
        payload=payload,
    )


def _is_offline(view: GateRunView) -> bool:
    adapters = [p for p in view.provenance if p.provider != TEMPLATE_DIFF.provider]
    return not adapters or any(not p.live for p in adapters)


@dataclass
class GateRunRecord:
    view: GateRunView
    created_at: datetime
    artifacts: dict[str, tuple[str, bytes]] = field(default_factory=dict)


@dataclass
class GateService:
    settings: ApiSettings
    manifests: dict[str, dict[str, str]]
    runs: dict[str, GateRunRecord] = field(default_factory=dict)
    _ids: "count[int]" = field(default_factory=lambda: count(1))
    _fixture: dict[str, Any] | None = None

    def changes(self) -> list[ChangeOption]:
        return [
            ChangeOption(
                change_id=c.change_id,
                feature_intent=c.feature_intent,
                base_sha=self.manifests[c.change_id]["base_sha"],
                head_sha=self.manifests[c.change_id]["head_sha"],
                offline_recording_available=c.runnable,
            )
            for c in CHANGES.values()
        ]

    def _fixture_repo(self) -> tuple[Path, dict[str, str]]:
        """Build the deterministic Cartwheel checkout once per process."""
        if self._fixture is None:
            root = Path(tempfile.mkdtemp(prefix="gauntlet-api-cartwheel-")) / "cartwheel"
            self._fixture = {"repo": root, "refs": _load_clean_builder().build_clean(root)}
        return self._fixture["repo"], self._fixture["refs"]

    @staticmethod
    def missing(core: Settings, adapter: str) -> tuple[str, ...]:
        return readiness(core)[adapter]

    @staticmethod
    def adapters(core: Settings) -> tuple[str, str, str]:
        """Live only where RUN_LIVE_INTEGRATIONS=1 and that adapter's keys are all set."""
        ready = readiness(core)
        live = core.run_live_integrations
        model: str = core.model_provider
        if model != "scripted" and not (live and not ready[model]):
            model = "scripted"
        infra_live = live and not ready["daytona"] and not ready["anchor"]
        sandbox, browser = ("daytona", "anchor") if infra_live else ("fake", "fake")
        return model, sandbox, browser

    def _base_view(self, run_id: str, change: ChangeDef) -> GateRunView:
        refs = self.manifests[change.change_id]
        return GateRunView(
            run_id=run_id,
            change_id=change.change_id,
            feature_intent=change.feature_intent,
            target_id=refs["target_id"],
            fixture_id=refs["fixture_id"],
            base_sha=refs["base_sha"],
            head_sha=refs["head_sha"],
            status=GateStatus.NOT_TESTED.value,
            attribution=Attribution.UNKNOWN.value,
            not_tested_reason=None,
            diff=template_diff(change),
            attacks=[],
            rejected_attacks=[],
            plan_sha256=None,
            model_id=None,
            attempts=[],
            findings=[],
            fix_plan=None,
            events=[],
            provenance=[TEMPLATE_DIFF],
        )

    def _not_tested(self, view: GateRunView, reason: str, code: str) -> GateRunView:
        return view.model_copy(
            update={
                "not_tested_reason": f"{reason} Not tested does not mean safe.",
                "events": [_event(view.run_id, 1, "run_not_tested", {"reason": code})],
            }
        )

    async def start(self, change_id: str) -> GateRunView:
        change = CHANGES[change_id]
        run_id = f"run-{change_id}-{next(self._ids):03d}"
        record = GateRunRecord(self._base_view(run_id, change), datetime.now(UTC))
        self.runs[run_id] = record
        if not change.runnable:
            record.view = self._not_tested(
                record.view,
                "This change needs the AI/tool worker, which is not routed in this build.",
                "no_ai_worker",
            )
            return record.view
        try:
            record.view = await self._execute(change, record)
        except (MissingSettingError, RuntimeError, ValueError) as exc:
            record.view = self._not_tested(record.view, f"Run could not start: {exc}.", "setup")
        return record.view

    async def _execute(self, change: ChangeDef, record: GateRunRecord) -> GateRunView:
        run_id = record.view.run_id
        core = Settings.from_env()
        model, sandbox, browser = self.adapters(core)
        repo, refs = self._fixture_repo()
        target = GateTarget.cartwheel(repo)
        if change.change_id == "clean":
            target = replace(target, clean_head_sha=refs["clean_sha"])
        runtime = await build_gate(
            core,
            target,
            model=model,  # type: ignore[arg-type]
            sandbox=sandbox,  # type: ignore[arg-type]
            browser=browser,  # type: ignore[arg-type]
            artifact_root=Path(tempfile.mkdtemp(prefix=f"gauntlet-{run_id}-")),
        )
        try:
            report = await runtime.use_case.execute(
                run_id, target.change(intent=change.feature_intent), target.fixture_checksum
            )
        finally:
            await runtime.aclose()
        attempts: list[AttemptView] = []
        for outcome in report.outcomes:
            for revision, side in (("head", outcome.head), ("base", outcome.base)):
                for index, attempt in enumerate(side, start=1):
                    shots: list[str] = []
                    for artifact in attempt.artifacts:
                        ref = artifact.binding.evidence
                        record.artifacts[ref.artifact_id] = (ref.media_type, artifact.content)
                        if ref.media_type.startswith("image/"):
                            shots.append(ref.artifact_id)
                    verdict = attempt.verdicts[0] if attempt.verdicts else None
                    attempts.append(
                        AttemptView(
                            attack_id=outcome.attack.attack_id,
                            revision=revision,  # type: ignore[arg-type]
                            attempt=index,
                            source_sha=attempt.subject.source_sha,
                            oracle_id=verdict.oracle_id if verdict else "none",
                            outcome=verdict.outcome.value if verdict else "inconclusive",
                            observed=verdict.observed if verdict else "",
                            evidence_ids=list(attempt.observation.evidence_ids),
                            screenshot_artifact_ids=shots,
                        )
                    )
        status = report.overall
        confirmed = [f for f in report.findings if f.status in CONFIRMED_GATE_STATUSES]
        attribution = confirmed[0].attribution if confirmed else Attribution.UNKNOWN
        provenance = [*_provenance(runtime.labels), TEMPLATE_DIFF]
        fix_view = None
        if change.change_id == "help-button" and status is GateStatus.CONFIRMED_REGRESSION:
            fix = FixPlan(
                fix_plan_id=f"{run_id}:fix-001",
                run_id=run_id,
                finding_id=confirmed[0].finding_id,
                base_sha=target.head_sha,
                allowed_paths=("src/components/FloatingHelp.module.css",),
                unified_diff=SAMPLE_FIX_DIFF,
                rationale="Keep the Help button above the Checkout action at every width.",
                test_plan=(
                    "Replay the frozen attack on the patched head: Checkout receives the click",
                    "Legitimate: Help button still opens the help dialog",
                    "Base and desktop widths unchanged",
                ),
                created_at=datetime.now(UTC),
            )
            fix_view = FixPlanView(
                plan=fix,
                plan_sha256=fix_plan_hash(fix),
                allowed_paths=list(fix.allowed_paths),
                provenance=SAMPLE_FIX,
            )
            provenance.append(SAMPLE_FIX)
        return record.view.model_copy(
            update={
                "base_sha": target.base_sha,
                "head_sha": target.head_sha,
                "status": status.value,
                "attribution": attribution.value,
                "not_tested_reason": report.plan.not_tested_reason,
                "attacks": list(report.plan.attacks),
                "rejected_attacks": [
                    f"{r.attack_id}: {'; '.join(r.reasons)}" for r in report.plan.rejected
                ],
                "plan_sha256": report.plan.plan_hash,
                "model_id": report.plan.model_id,
                "attempts": attempts,
                "findings": list(report.findings),
                "fix_plan": fix_view,
                "events": list(report.events),
                "provenance": provenance,
            }
        )

    def append_event(self, run_id: str, event_type: str, payload: Payload) -> None:
        record = self.runs[run_id]
        seq = (record.view.events[-1].sequence + 1) if record.view.events else 1
        event = _event(run_id, seq, event_type, payload)
        record.view = record.view.model_copy(update={"events": [*record.view.events, event]})

    def summaries(self) -> list[GateRunSummary]:
        return [
            GateRunSummary(
                run_id=r.view.run_id,
                change_id=r.view.change_id,
                status=r.view.status,
                attribution=r.view.attribution,
                offline=_is_offline(r.view),
            )
            for r in sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)
        ]
