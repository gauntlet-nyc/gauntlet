"""Gate run composition for the API, over Session 1's RunGateUseCase (gauntlet.composition).

Adapters are chosen from settings: live (Azure/Bedrock planner, Daytona, Anchor) only when
RUN_LIVE_INTEGRATIONS=1 and that adapter's env vars are set; otherwise the labelled offline
adapters (scripted planner, fake sandbox, simulated layout browser). Every attempt still goes
through the real planner/validator, plan freeze, UI worker, stored-evidence oracle and pair
verdict. The refund-tool change runs the AI-agent route: the fixture's own tool code per
revision in the local tool world, judged by the ledger oracle.
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

from gauntlet.application.gate import ApprovalScope, AuthenticatedReviewer, fix_plan_hash
from gauntlet.application.gate.learn import LearnFromGateUseCase
from gauntlet.application.gate.repair import ReleaseVerdict
from gauntlet.application.gate.run_gate import GateRunReport
from gauntlet.composition import (
    GateRuntime,
    GateTarget,
    RepairRuntime,
    build_gate,
    build_repair,
    readiness,
    refund_verification_suite,
)
from gauntlet.contracts import ApprovalDecision, ApprovalRecord, AttackSpec, FixPlan, RunEvent
from gauntlet.domain import CONFIRMED_GATE_STATUSES, Attribution, GateStatus
from gauntlet.integrations.fake.memory import InMemoryTemporalMemory
from gauntlet.ports.errors import PortError
from gauntlet.settings import MissingSettingError, Settings

from ..schemas import (
    AttemptView,
    ChangeOption,
    FileDiff,
    FixPlanView,
    GateRunSummary,
    GateRunView,
    Provenance,
    RepairCheckView,
    RepairView,
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
    "local_tool_world": "Local tool world: the fixture's own tool code per revision (not Daytona)",
    "not_used": "Not used by this attack",
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
        True,
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


REFUND_FIX_DIFF = """--- a/api/src/tools/request_refund.ts
+++ b/api/src/tools/request_refund.ts
@@ -17,6 +17,9 @@
   if (!order) {
     throw new Error("unknown order");
   }
+  if (order.ownerId !== ctx.actorId) {
+    throw new Error("forbidden: order belongs to another customer");
+  }
   if (ctx.ledger.hasRefund(order.id)) {
     throw new Error("order already refunded");
   }
"""

# change_id -> (allowed path, diff, rationale, verification plan)
SAMPLE_FIXES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "help-button": (
        "src/components/FloatingHelp.module.css",
        SAMPLE_FIX_DIFF,
        "Keep the Help button above the Checkout action at every width.",
        (
            "Replay the frozen attack on the patched head: Checkout receives the click",
            "Legitimate: Help button still opens the help dialog",
            "Base and desktop widths unchanged",
        ),
    ),
    "refund-tool": (
        "api/src/tools/request_refund.ts",
        REFUND_FIX_DIFF,
        "Enforce order ownership in the tool itself; the conversation is not an authority.",
        (
            "Replay the frozen cross-owner attack on the patched head: ledger shows no refund",
            "Legitimate: an owner can still refund their own order once",
            "Node test api/test/refund.test.ts passes",
        ),
    ),
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
        text = "".join(difflib.unified_diff(before, after, f"a/{rel}", f"b/{rel}"))
        if text:
            diffs.append(FileDiff(path=rel, unified_diff=text))
    return diffs


def _load_builder(name: str) -> ModuleType:
    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / f"scripts/{name}.py")
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


def _repair_provenance(labels: dict[str, str]) -> list[Provenance]:
    text = {
        "offline_scripted_fix": "OFFLINE scripted fix proposer (no model call)",
        "local_git_worktree": "Patch applied in a fresh local git worktree; never pushed",
        "in_memory": "Single-use approval store in API memory",
    }
    return [
        Provenance(
            provider=f"{part}:{label}",
            mode="live" if label.startswith("live_") else "offline_fixture",
            live=label.startswith("live_"),
            label=text.get(label, label),
        )
        for part, label in labels.items()
    ]


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
class RepairContext:
    """Live objects the repair loop needs after the Gate run (refund-tool only)."""

    gate: GateRuntime
    repair: RepairRuntime
    target: GateTarget
    attack: AttackSpec
    plan: FixPlan
    approval_id: str | None = None


@dataclass
class GateRunRecord:
    view: GateRunView
    created_at: datetime
    artifacts: dict[str, tuple[str, bytes]] = field(default_factory=dict)
    repair: RepairContext | None = None


@dataclass
class GateService:
    settings: ApiSettings
    manifests: dict[str, dict[str, str]]
    runs: dict[str, GateRunRecord] = field(default_factory=dict)
    memory: Any = field(default_factory=InMemoryTemporalMemory)
    """MemoryReader + MemoryWriter (+ all()); SurrealDB Agent Memory when live."""
    memory_label: str = InMemoryTemporalMemory.label
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

    def _fixture_repo(self, kind: str) -> tuple[Path, dict[str, str]]:
        """Build each deterministic Cartwheel checkout once per process."""
        if self._fixture is None:
            self._fixture = {}
        if kind not in self._fixture:
            root = Path(tempfile.mkdtemp(prefix=f"gauntlet-api-{kind}-")) / "cartwheel"
            if kind == "refund":
                refs = _load_builder("build_cartwheel_refund_fixture").build_refund(root)
            else:
                refs = _load_builder("build_cartwheel_clean_fixture").build_clean(root)
            self._fixture[kind] = (root, refs)
        repo, refs = self._fixture[kind]
        return repo, refs

    @staticmethod
    def missing(core: Settings, adapter: str) -> tuple[str, ...]:
        return readiness(core)[adapter]

    @staticmethod
    def adapters(core: Settings, change_id: str = "help-button") -> tuple[str, str, str]:
        """Live only where RUN_LIVE_INTEGRATIONS=1 and that adapter's keys are all set.

        Without Daytona/Anchor, pre-started local Cartwheel servers (CARTWHEEL_BASE_ORIGIN /
        CARTWHEEL_HEAD_ORIGIN) give a real local-Chromium run for the Help-button change.
        Otherwise the offline fake sandbox and simulated layout browser run.
        """
        ready = readiness(core)
        live = core.run_live_integrations
        model: str = core.model_provider
        if model != "scripted" and not (live and not ready[model]):
            model = "scripted"
        if change_id != "refund-tool" and live and not ready["daytona"] and not ready["anchor"]:
            return model, "daytona", "anchor"
        if change_id == "refund-tool":
            return model, "fake", "fake"  # AI-agent attacks run in the local tool world
        if change_id == "help-button" and not ready["local"]:
            return model, "local", "local"
        return model, "fake", "fake"

    @classmethod
    def uses_live_provider(cls, core: Settings, change_id: str) -> bool:
        """True when this run would call a paid/remote provider (model, Daytona or Anchor)."""
        model, sandbox, browser = cls.adapters(core, change_id)
        return model != "scripted" or sandbox == "daytona" or browser == "anchor"

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
        except (MissingSettingError, RuntimeError, ValueError, ImportError) as exc:
            record.view = self._not_tested(record.view, f"Run could not start: {exc}.", "setup")
        return record.view

    async def _execute(self, change: ChangeDef, record: GateRunRecord) -> GateRunView:
        run_id = record.view.run_id
        core = Settings.from_env()
        model, sandbox, browser = self.adapters(core, change.change_id)
        if change.change_id == "refund-tool":
            repo, refs = self._fixture_repo("refund")
            target = GateTarget.cartwheel_refund(repo)
            if (refs["refund_base_sha"], refs["refund_head_sha"]) != (
                target.base_sha,
                target.head_sha,
            ):
                raise RuntimeError("rebuilt refund fixture SHAs differ from the pinned manifest")
        else:
            repo, refs = self._fixture_repo("ui")
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
            memory=self.memory,
        )
        keep_open = False
        try:
            report = await runtime.use_case.execute(
                run_id, target.change(intent=change.feature_intent), target.fixture_checksum
            )
            keep_open = await self._prepare_repair(record, runtime, target, report, core, model)
        finally:
            if not keep_open:
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
        used = next(
            (
                str(e.payload.get("memory_fact_ids") or "")
                for e in report.events
                if e.event_type == "plan_frozen"
            ),
            "",
        )
        written = await self._remember(report, target)
        attribution = confirmed[0].attribution if confirmed else Attribution.UNKNOWN
        provenance = [*_provenance(runtime.labels), TEMPLATE_DIFF]
        fix_view = None
        if record.repair is not None:
            context = record.repair
            fix_view = FixPlanView(
                plan=context.plan,
                plan_sha256=fix_plan_hash(context.plan),
                allowed_paths=list(context.plan.allowed_paths),
                provenance=_repair_provenance(context.repair.labels)[0],
                repairable=True,
            )
            provenance.append(fix_view.provenance)
        elif (sample := SAMPLE_FIXES.get(change.change_id)) and (
            status is GateStatus.CONFIRMED_REGRESSION
        ):
            path, diff, rationale, test_plan = sample
            fix = FixPlan(
                fix_plan_id=f"{run_id}:fix-001",
                run_id=run_id,
                finding_id=confirmed[0].finding_id,
                base_sha=target.head_sha,
                allowed_paths=(path,),
                unified_diff=diff,
                rationale=rationale,
                test_plan=test_plan,
                created_at=datetime.now(UTC),
            )
            fix_view = FixPlanView(
                plan=fix,
                plan_sha256=fix_plan_hash(fix),
                allowed_paths=list(fix.allowed_paths),
                provenance=SAMPLE_FIX,
                repairable=False,
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
                "memory_fact_ids_used": [f for f in used.split(",") if f],
                "memory_facts_written": written,
                "events": list(report.events),
                "provenance": provenance,
            }
        )

    async def _remember(self, report: GateRunReport, target: GateTarget) -> list[str]:
        """Session 1's P7 learner: confirmed findings become provenance-backed facts."""
        try:
            facts = await LearnFromGateUseCase(self.memory, lambda: datetime.now(UTC)).remember(
                report
            )
        except PortError:
            return []  # this exact finding on this commit is already remembered (append-only)
        return [f.fact_id for f in facts]

    async def _prepare_repair(
        self,
        record: GateRunRecord,
        runtime: GateRuntime,
        target: GateTarget,
        report: GateRunReport,
        core: Settings,
        model: str,
    ) -> bool:
        """For confirmed AI-agent findings, freeze a real fix proposal for human review."""
        if "ai_agent" not in runtime.routes:
            return False
        confirmed = [
            o for o in report.outcomes if o.finding.status is GateStatus.CONFIRMED_REGRESSION
        ]
        if not confirmed:
            return False
        outcome = confirmed[0]
        repair = build_repair(core, target, runtime, model=model)  # type: ignore[arg-type]
        plan, _ = await repair.use_case.propose(
            record.view.run_id, outcome.finding, outcome.attack, target.head_sha
        )
        record.repair = RepairContext(runtime, repair, target, outcome.attack, plan)
        return True

    async def record_fix_approval(
        self,
        record: GateRunRecord,
        decision: ApprovalDecision,
        reviewer: AuthenticatedReviewer,
    ) -> ApprovalRecord:
        """Approvals for repairable plans go to the repair loop's own single-use store."""
        context = record.repair
        if context is None:
            raise ValueError("this run has no repairable fix plan")
        approval = await context.repair.approvals.record(
            ApprovalScope(
                run_id=record.view.run_id,
                target_id=context.target.target_id,
                fixture_id=context.target.fixture_id,
                current_plan_sha256=fix_plan_hash(context.plan),
                allowed_paths=context.plan.allowed_paths,
            ),
            decision,
            reviewer,
        )
        if approval.decision == "approved":
            context.approval_id = approval.approval_id
        return approval

    async def run_repair(self, run_id: str) -> GateRunView:
        """Apply the approved plan in a fresh worktree and re-verify. Review-only output."""
        record = self.runs[run_id]
        context = record.repair
        if context is None:
            raise ValueError("this run has no repairable fix plan")
        if context.approval_id is None:
            raise PermissionError("approve the fix plan hash before running the repair")
        report = await context.repair.use_case.execute(
            context.approval_id,
            context.plan,
            target_id=context.target.target_id,
            fixture_id=context.target.fixture_id,
            fixture_checksum=context.target.fixture_checksum,
            suite=refund_verification_suite(context.target, context.attack),
        )
        context.approval_id = None  # spent by authorize()
        repair_view = RepairView(
            approval_id=report.approval_id,
            patched_sha=report.patched_sha,
            touched_paths=list(report.touched_paths),
            checks=[
                RepairCheckView(name=c.name, passed=c.passed, detail=c.detail)
                for c in report.checks
            ],
            verdict=report.verdict.value,
            note=report.note,
            provenance=_repair_provenance(context.repair.labels),
        )
        record.view = record.view.model_copy(update={"repair": repair_view})
        self.append_event(
            run_id,
            "repair_verified"
            if report.verdict is ReleaseVerdict.FIX_VERIFIED_REVIEW_REQUIRED
            else "repair_not_verified",
            {
                "approval_id": report.approval_id,
                "patched_sha": report.patched_sha,
                "release_verdict": report.verdict.value,
            },
        )
        return record.view

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
