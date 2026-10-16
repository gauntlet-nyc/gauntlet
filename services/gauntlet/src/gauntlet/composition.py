"""Composition root: pick fake / local / live adapters from settings and wire the use cases.

The only place that imports concrete adapters. Every runtime carries labels saying which
adapters ran, so a report can never present an offline simulation as a live provider run.
Live adapters need RUN_LIVE_INTEGRATIONS=1 plus their keys; a missing key raises
``MissingSettingError("missing NAME")`` and never falls back silently.
"""

import json
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, cast
from uuid import uuid4

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.application.gate.attempts import OracleAttemptExecutor
from gauntlet.application.gate.run_gate import GateDependencies, RunGateUseCase, WorkerRoute
from gauntlet.application.gate.targets import StaticTargetCatalog, profile_from_manifest
from gauntlet.contracts import ChangeRequest, WorkerKind
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.integrations.fake.simulated_ui import SimulatedBrowserProvider, cartwheel_layouts
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.scripted_model import ScriptedModelGateway, UiProbe
from gauntlet.planning import AttackPlanner, PlanningLimits
from gauntlet.ports import (
    ArtifactStore,
    BrowserProvider,
    MemoryReader,
    ModelGateway,
    RunStore,
    SandboxProvider,
)
from gauntlet.settings import (
    ANCHOR_KEYS,
    ANCHOR_PROXY_KEYS,
    AZURE_KEYS,
    BEDROCK_KEYS,
    DAYTONA_KEYS,
    LOCAL_ORIGIN_KEYS,
    ModelProvider,
    Settings,
)
from gauntlet.verification.registry import RegisteredOracleRegistry
from gauntlet.verification.stored_browser import StoredBrowserOracle
from gauntlet.workers.ui import UIWorker

GateSandbox = Literal["fake", "local", "daytona"]
GateBrowser = Literal["fake", "local", "anchor"]

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
CARTWHEEL_MANIFEST: Final = REPO_ROOT / "apps/cartwheel/fixture-manifest.v1.json"
PLANNER_PROMPT: Final = REPO_ROOT / "docs/prompts/p1-ui-planner.md"
CHROMIUM: Final = Path("/opt/pw-browsers/chromium")

_COMPATIBLE: Final[Mapping[GateBrowser, GateSandbox]] = {
    "fake": "fake",
    "local": "local",
    "anchor": "daytona",
}


@dataclass(frozen=True)
class GateTarget:
    """Trusted target registration loaded from the committed synthetic manifest."""

    manifest: Mapping[str, Any]
    repository_path: Path
    primary_route: str = "/checkout"
    primary_test_id: str = "checkout-primary-action"
    clean_head_sha: str | None = None
    """Set to compare base against the unrelated clean product-copy commit instead."""

    @property
    def target_id(self) -> str:
        return str(self.manifest["target_id"])

    @property
    def fixture_id(self) -> str:
        return str(self.manifest["fixture_id"])

    @property
    def fixture_checksum(self) -> str:
        return str(self.manifest["fixture_checksum_sha256"])

    @property
    def base_sha(self) -> str:
        return str(self.manifest["git_refs"]["base_sha"])

    @property
    def head_sha(self) -> str:
        return self.clean_head_sha or str(self.manifest["git_refs"]["head_sha"])

    def change(self, *, intent: str | None = None) -> ChangeRequest:
        return ChangeRequest(
            repository_id="cartwheel",
            base_sha=self.base_sha,
            head_sha=self.head_sha,
            fixture_id=self.fixture_id,
            target_id=self.target_id,
            max_cost_usd_cents=500,
            feature_intent=intent,
        )

    @classmethod
    def cartwheel(cls, repository_path: Path) -> "GateTarget":
        return cls(json.loads(CARTWHEEL_MANIFEST.read_text()), repository_path)


@dataclass
class GateRuntime:
    use_case: RunGateUseCase
    store: RunStore
    artifacts: ArtifactStore
    labels: dict[str, str]
    stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def aclose(self) -> None:
        await self.stack.aclose()


def build_model_gateway(
    provider: ModelProvider, settings: Settings, target: GateTarget
) -> tuple[ModelGateway, str]:
    if provider == "scripted":
        probe = UiProbe(route=target.primary_route, primary_test_id=target.primary_test_id)
        return ScriptedModelGateway(ui=probe), "offline_scripted"
    settings.require_live(provider)
    if provider == "azure":
        from gauntlet.integrations.azure_openai import DEFAULT_API_VERSION, AzureOpenAIGateway

        for name in AZURE_KEYS:
            settings.require(name)
        return (
            AzureOpenAIGateway(
                endpoint=settings.require("AZURE_OPENAI_ENDPOINT"),
                deployment=settings.require("AZURE_OPENAI_DEPLOYMENT"),
                api_key=settings.secret("AZURE_OPENAI_API_KEY").reveal(),
                api_version=settings.optional("AZURE_OPENAI_API_VERSION") or DEFAULT_API_VERSION,
                reasoning_model=settings.flag("AZURE_OPENAI_REASONING_MODEL"),
            ),
            "live_azure_openai",
        )
    from gauntlet.integrations.bedrock import create_bedrock_gateway

    for name in BEDROCK_KEYS:
        settings.require(name)
    return (
        create_bedrock_gateway(
            model_id=settings.require("BEDROCK_MODEL_ID"), region=settings.require("AWS_REGION")
        ),
        "live_bedrock",
    )


def _planner_registry(target: GateTarget) -> RegisteredOracleRegistry:
    return RegisteredOracleRegistry(
        plans=(), primary_targets={target.target_id: target.primary_test_id}, evidence=()
    )


async def build_gate(
    settings: Settings,
    target: GateTarget,
    *,
    model: ModelProvider,
    sandbox: GateSandbox,
    browser: GateBrowser,
    artifact_root: Path,
    memory: MemoryReader | None = None,
) -> GateRuntime:
    if _COMPATIBLE[browser] != sandbox:
        raise ValueError(
            f"--browser {browser} needs --sandbox {_COMPATIBLE[browser]} "
            "(the browser must reach the sandbox's preview origin)"
        )
    stack = AsyncExitStack()
    try:
        gateway, model_label = build_model_gateway(model, settings, target)
        artifacts = LocalArtifactStore(artifact_root)
        collector = BrowserEvidenceCollector(artifacts)
        sandbox_port, sandbox_label, preview_suffix = _build_sandbox(sandbox, settings, target)
        browser_port, browser_label = await _build_browser(
            browser, settings, target, collector, stack, preview_suffix
        )
        store = FakeRunStore(initial_sequence=0)
        registry = _planner_registry(target)
        primary = {target.target_id: target.primary_test_id}
        ui_route = WorkerRoute(
            OracleAttemptExecutor(
                UIWorker(browser_port, registry),
                StoredBrowserOracle(artifacts, primary_targets=primary),
                artifacts,
            )
        )
        routes: dict[WorkerKind, WorkerRoute] = {"ui": ui_route}
        plan = PlanChangeUseCase(
            PlanChangeDependencies(
                inspector=GitRepositoryInspector({"cartwheel": target.repository_path}),
                planner=AttackPlanner(
                    gateway, registry, PLANNER_PROMPT.read_text(), PlanningLimits()
                ),
                store=store,
                targets=StaticTargetCatalog(profile_from_manifest(target.manifest)),
                clock=lambda: datetime.now(UTC),
                new_event_id=lambda: f"event-{uuid4().hex}",
                memory=memory,
            )
        )
        use_case = RunGateUseCase(
            GateDependencies(
                plan_change=plan,
                sandbox=sandbox_port,
                routes=routes,
                store=store,
                clock=lambda: datetime.now(UTC),
                new_id=lambda prefix: f"{prefix}-{uuid4().hex}",
            )
        )
        labels = {
            "model": model_label,
            "sandbox": sandbox_label,
            "browser": browser_label,
            "run_store": "in_memory",
            "artifact_store": "local_write_once",
        }
        return GateRuntime(use_case, store, artifacts, labels, stack)
    except BaseException:
        await stack.aclose()
        raise


def _build_sandbox(
    kind: GateSandbox, settings: Settings, target: GateTarget
) -> tuple[SandboxProvider, str, str | None]:
    if kind == "fake":
        fixture = Fixture(
            target.fixture_id,
            target.fixture_checksum,
            frozenset({target.base_sha, target.head_sha}),
        )
        return FakeSandboxProvider({target.target_id: fixture}), "offline_fake", None
    if kind == "local":
        from gauntlet.integrations.local_sandbox import PreStartedLocalSandbox

        base_origin, head_origin = (settings.require(name) for name in LOCAL_ORIGIN_KEYS)
        return (
            PreStartedLocalSandbox(
                target_id=target.target_id,
                fixture_id=target.fixture_id,
                fixture_checksum=target.fixture_checksum,
                revisions={target.base_sha: base_origin, target.head_sha: head_origin},
            ),
            "local_prestarted",
            None,
        )
    settings.require_live("Daytona")
    from gauntlet.execution.provider_smoke_config import load_registration
    from gauntlet.integrations.daytona import DaytonaSandboxProvider
    from gauntlet.integrations.daytona.sdk import HttpxHealthProbe, SdkDaytonaRuntime

    for name in DAYTONA_KEYS:
        settings.require(name)
    registration_path = Path(settings.require("GAUNTLET_DAYTONA_REGISTRATION"))
    _, registered = load_registration(registration_path, target.manifest)
    runtime = SdkDaytonaRuntime.from_credentials(
        api_key=settings.secret("DAYTONA_API_KEY").reveal(),
        api_url=settings.optional("DAYTONA_API_URL") or "https://app.daytona.io/api",
        target=settings.require("DAYTONA_TARGET"),
    )
    provider = DaytonaSandboxProvider(
        runtime, {registered.target_id: registered}, HttpxHealthProbe()
    )
    return provider, "live_daytona", registered.preview_domain_suffix


async def _build_browser(
    kind: GateBrowser,
    settings: Settings,
    target: GateTarget,
    collector: BrowserEvidenceCollector,
    stack: AsyncExitStack,
    preview_suffix: str | None,
) -> tuple[BrowserProvider, str]:
    if kind == "fake":
        layouts = cartwheel_layouts(
            target.base_sha, target.head_sha, head_adds_help=target.clean_head_sha is None
        )
        return SimulatedBrowserProvider(layouts, collector), "offline_simulated_layout"
    if kind == "local":
        from playwright.async_api import async_playwright

        from gauntlet.integrations.local_browser import LocalBrowserProvider, PlaywrightBrowser

        playwright = await stack.enter_async_context(async_playwright())
        executable = settings.optional("GAUNTLET_CHROMIUM_PATH") or (
            str(CHROMIUM) if CHROMIUM.exists() else None
        )
        browser = await playwright.chromium.launch(executable_path=executable, headless=True)
        stack.push_async_callback(browser.close)
        return (
            LocalBrowserProvider(cast(PlaywrightBrowser, browser), collector),
            "local_headless_chromium",
        )
    settings.require_live("Anchor")
    from gauntlet.integrations.anchor import provider as anchor_provider
    from gauntlet.integrations.anchor.sdk import SdkAnchorRuntime

    for name in ANCHOR_KEYS:
        settings.require(name)
    api_key = settings.secret("ANCHOR_API_KEY").reveal()
    if settings.anchor_require_proxy:
        for name in ANCHOR_PROXY_KEYS:
            settings.require(name)
        runtime: Any = SdkAnchorRuntime.from_credentials(
            api_key=api_key,
            proxy_server=settings.require("ANCHOR_PROXY_SERVER"),
            proxy_username=settings.require("ANCHOR_PROXY_USERNAME"),
            proxy_password=settings.secret("ANCHOR_PROXY_PASSWORD").reveal(),
        )
        label = "live_anchor_with_egress_proxy"
    else:
        # GAUNTLET_ANCHOR_REQUIRE_PROXY=0: weaker isolation, documented in docs/SECURITY.md.
        without_proxy = getattr(SdkAnchorRuntime, "without_proxy", None)
        if without_proxy is None:
            raise RuntimeError(
                "this Anchor adapter build has no proxy-less mode; set "
                "GAUNTLET_ANCHOR_REQUIRE_PROXY=1 with ANCHOR_PROXY_* or update the adapter"
            )
        runtime = without_proxy(api_key=api_key)
        label = "live_anchor_no_egress_proxy"
    if preview_suffix is None:
        raise ValueError("Anchor needs the Daytona preview domain suffix")
    anchor = anchor_provider.AnchorBrowserProvider(
        runtime, collector, preview_domain_suffix=preview_suffix
    )
    return anchor, label


def readiness(settings: Settings) -> dict[str, tuple[str, ...]]:
    """Missing variable NAMES per live adapter (never values), for the run report."""
    anchor = ANCHOR_KEYS + (ANCHOR_PROXY_KEYS if settings.anchor_require_proxy else ())
    return {
        "azure": settings.missing(*AZURE_KEYS),
        "bedrock": settings.missing(*BEDROCK_KEYS),
        "daytona": settings.missing(*DAYTONA_KEYS, "GAUNTLET_DAYTONA_REGISTRATION"),
        "anchor": settings.missing(*anchor),
        "local": settings.missing(*LOCAL_ORIGIN_KEYS),
    }
