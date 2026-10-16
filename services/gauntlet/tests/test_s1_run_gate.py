"""Gate pipeline: frozen plan -> verified base/head environments -> attempts -> Finding."""

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from gauntlet.application.gate.run_gate import GateDependencies, GateRunReport, RunGateUseCase
from gauntlet.composition import GateTarget, build_gate, readiness
from gauntlet.domain import Attribution, GateStatus
from gauntlet.ports import EnvironmentUnavailableError
from gauntlet.settings import MissingSettingError, Secret, Settings

ROOT = Path(__file__).resolve().parents[3]
OFFLINE = Settings.from_env({})


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    repo = tmp_path_factory.mktemp("gate") / "cartwheel"
    out = subprocess.run(
        [sys.executable, "scripts/build_cartwheel_clean_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo, json.loads(out.stdout)


def run(target: GateTarget, tmp_path: Path, **kwargs: object) -> GateRunReport:
    async def scenario() -> GateRunReport:
        runtime = await build_gate(
            OFFLINE,
            target,
            model="scripted",
            sandbox="fake",
            browser="fake",
            artifact_root=tmp_path / "evidence",
        )
        use_case = runtime.use_case
        if kwargs:
            use_case = RunGateUseCase(replace(use_case._deps, **kwargs))  # noqa: SLF001
        try:
            return await use_case.execute(
                "run-s1",
                target.change(intent="Add a floating Help button"),
                target.fixture_checksum,
            )
        finally:
            await runtime.aclose()

    return asyncio.run(scenario())


def test_help_button_is_a_confirmed_introduced_regression(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    report = run(GateTarget.cartwheel(built[0]), tmp_path)
    assert report.overall is GateStatus.CONFIRMED_REGRESSION
    (finding,) = report.findings
    assert finding.attribution is Attribution.INTRODUCED
    assert (finding.head_reproductions, finding.head_attempts) == (2, 2)
    assert (finding.base_reproductions, finding.base_attempts) == (0, 2)
    assert finding.evidence_ids and finding.oracle_verdict_ids
    types = [event.event_type for event in report.events]
    # Freeze before any environment exists; findings only after all attempts.
    assert types[:3] == ["impact_mapped", "plan_frozen", "environments_ready"]
    assert types.count("attempt_recorded") == 4
    assert types[-2:] == ["finding_recorded", "run_completed"]
    assert report.events[1].payload["plan_hash"] == report.plan.plan_hash


def test_unrelated_clean_change_passes(built: tuple[Path, dict[str, str]], tmp_path: Path) -> None:
    target = replace(GateTarget.cartwheel(built[0]), clean_head_sha=built[1]["clean_sha"])
    report = run(target, tmp_path)
    assert report.overall is GateStatus.PASSED
    assert report.findings[0].head_attempts == 2


def test_unavailable_environments_are_environment_error(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    class DownSandbox:
        async def create(self, **_: object) -> None:
            raise EnvironmentUnavailableError("down")

        async def verify_fixture(self, *_: object) -> bool:
            return False

        async def destroy(self, *_: object) -> None:
            return None

    report = run(GateTarget.cartwheel(built[0]), tmp_path, sandbox=DownSandbox())
    assert report.overall is GateStatus.ENVIRONMENT_ERROR
    assert report.findings[0].head_attempts == 0


def test_attack_without_executor_is_not_tested(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    report = run(GateTarget.cartwheel(built[0]), tmp_path, routes={})
    assert report.overall is GateStatus.NOT_TESTED
    assert "no registered executor" in report.findings[0].limitations[0]


def test_single_attempt_per_side_is_refused() -> None:
    with pytest.raises(ValueError, match="two attempts"):
        RunGateUseCase(
            GateDependencies(
                plan_change=None,  # type: ignore[arg-type]
                sandbox=None,  # type: ignore[arg-type]
                routes={},
                store=None,  # type: ignore[arg-type]
                clock=lambda: None,  # type: ignore[arg-type, return-value]
                new_id=str,
                attempts_per_side=1,
            )
        )


def test_live_adapters_need_opt_in_and_named_keys(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    target = GateTarget.cartwheel(built[0])

    async def attempt(settings: Settings) -> None:
        await build_gate(
            settings,
            target,
            model="azure",
            sandbox="fake",
            browser="fake",
            artifact_root=tmp_path / "e",
        )

    with pytest.raises(MissingSettingError, match="RUN_LIVE_INTEGRATIONS"):
        asyncio.run(attempt(OFFLINE))
    live = Settings.from_env(
        {"RUN_LIVE_INTEGRATIONS": "1", "AZURE_OPENAI_API_KEY": "REPLACE_WITH_KEY"}
    )
    with pytest.raises(MissingSettingError, match="missing AZURE_OPENAI_ENDPOINT"):
        asyncio.run(attempt(live))
    with pytest.raises(ValueError, match="needs --sandbox daytona"):
        asyncio.run(
            build_gate(
                OFFLINE,
                target,
                model="scripted",
                sandbox="fake",
                browser="anchor",
                artifact_root=tmp_path / "e",
            )
        )


def test_settings_never_reveal_secrets() -> None:
    settings = Settings.from_env(
        {"ANCHOR_API_KEY": "sk-very-secret", "GAUNTLET_MODEL_PROVIDER": "azure"}
    )
    secret = settings.secret("ANCHOR_API_KEY")
    assert isinstance(secret, Secret)
    assert "sk-very-secret" not in repr(secret) + str(secret) + repr(settings)
    assert secret.reveal() == "sk-very-secret"
    assert settings.model_provider == "azure"
    assert "ANCHOR_API_KEY" not in readiness(settings)["anchor"]
    assert "sk-very-secret" not in json.dumps(readiness(settings))
    with pytest.raises(ValueError, match="GAUNTLET_MODEL_PROVIDER"):
        Settings.from_env({"GAUNTLET_MODEL_PROVIDER": "gpt"})
    assert Settings.from_env({"GAUNTLET_ANCHOR_REQUIRE_PROXY": "0"}).anchor_require_proxy is False
    assert Settings.from_env({}).anchor_require_proxy is True
