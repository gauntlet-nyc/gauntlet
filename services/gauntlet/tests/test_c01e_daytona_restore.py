"""Restore smoke uses real provider validation with fake runtime and HTTP transport."""

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.daytona.provider import RegisteredSnapshot, RegisteredTarget

ROOT = Path(__file__).resolve().parents[3]
STATE = b'{"synthetic_only":true}'
BASE, HEAD = "a" * 40, "b" * 40


def probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "restore", ROOT / "scripts/probe_b01_snapshot_restore.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Sandbox:
    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.id = f"env-{sha[0]}"

    async def checkout_sha(self, repo_path: str) -> str:
        return self.sha

    async def read_file(self, path: str) -> bytes:
        return STATE

    async def signed_preview_origin(self, port: int, expires_in_seconds: int) -> str:
        return f"https://signed-secret-{self.sha[0]}.preview.test"


class Runtime:
    def __init__(self, *, fail_head: bool = False, fail_delete: bool = False) -> None:
        self.fail_head = fail_head
        self.fail_delete = fail_delete
        self.deleted: list[str] = []
        self.closed = False

    async def create(self, snapshot: str, timeout: float) -> Sandbox:
        if snapshot == "head" and self.fail_head:
            raise RuntimeError("provider-secret")
        return Sandbox(BASE if snapshot == "base" else HEAD)

    async def delete(self, sandbox: Sandbox, timeout: float) -> None:
        self.deleted.append(sandbox.id)
        if self.fail_delete:
            raise RuntimeError("delete-secret")

    async def close(self) -> None:
        self.closed = True


class Health:
    async def check(self, origin: str, path: str) -> bool:
        return True


def run(runtime: Runtime, *, mismatch: bool = False, cancel: bool = False) -> dict[str, object]:
    target = RegisteredTarget(
        "cartwheel-fixture",
        "baseline-v1",
        "c" * 64,
        hashlib.sha256(STATE).hexdigest(),
        "/repo/fixture-state.json",
        "/repo",
        3000,
        ".preview.test",
        "/checkout",
        (RegisteredSnapshot(BASE, "base", "d" * 64), RegisteredSnapshot(HEAD, "head", "d" * 64)),
    )
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=BASE,
        head_sha=HEAD,
        fixture_id=target.fixture_id,
        target_id=target.target_id,
        max_cost_usd_cents=500,
    )

    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/build-info"
        if cancel:
            raise asyncio.CancelledError
        sha = BASE if request.url.host.startswith("signed-secret-a.") else HEAD
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(
                json.dumps(
                    {"schema_version": "1.0", "source_sha": "f" * 40 if mismatch else sha}
                ).encode()
            ),
        )

    return asyncio.run(
        probe().restore_pair(
            runtime, change, target, health=Health(), transport=httpx.MockTransport(response)
        )
    )


def test_verified_pair_is_cleaned_without_exposing_previews() -> None:
    runtime = Runtime()
    report = run(runtime)
    assert report["status"] == "passed"
    assert report["gate_status"] == "not_tested"
    assert len(report["restored"]) == 2
    assert runtime.deleted == ["env-b", "env-a"]
    assert runtime.closed
    assert "signed-secret" not in json.dumps(report)


@pytest.mark.parametrize("failure", ["receipt", "create", "cancel", "cleanup"])
def test_failures_clean_scoped_resources_and_report_sanitized(failure: str) -> None:
    runtime = Runtime(fail_head=failure == "create", fail_delete=failure == "cleanup")
    report = run(runtime, mismatch=failure == "receipt", cancel=failure == "cancel")
    assert report["status"] == "environment_error"
    assert runtime.closed
    assert "env-a" in runtime.deleted
    if failure != "create":
        assert "env-b" in runtime.deleted
    assert "secret" not in json.dumps(report)
    if failure == "cleanup":
        assert set(report["pending_sandbox_cleanup_ids"]) == {"env-a", "env-b"}


def test_preflight_does_not_require_anchor_or_expose_values() -> None:
    environment = {
        "RUN_LIVE_INTEGRATIONS": "1",
        "GAUNTLET_ALLOWED_TARGET_IDS": "cartwheel-fixture",
        "DAYTONA_API_KEY": "secret-value",
        "DAYTONA_API_URL": "https://example.test",
        "DAYTONA_TARGET": "test",
    }
    missing = probe().preflight(environment, spend_authorized=True, registration_present=True)
    assert missing == []
    environment["DAYTONA_API_KEY"] = "REPLACE_ME"
    assert probe().preflight(environment, spend_authorized=False, registration_present=False) == [
        "spend_authorization",
        "registration",
        "DAYTONA_API_KEY",
    ]


@pytest.mark.parametrize(
    "flags", [[], ["--execute"], ["--authorize-spend"], ["--execute", "--authorize-spend"]]
)
def test_cli_blocks_sdk_before_opt_in_and_valid_registration(
    flags: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = probe()
    registration = tmp_path / "invalid-registration.json"
    registration.write_text("{}")
    output = tmp_path / "out"
    for name, value in {
        "RUN_LIVE_INTEGRATIONS": "1",
        "GAUNTLET_ALLOWED_TARGET_IDS": "cartwheel-fixture",
        "DAYTONA_API_KEY": "secret-key",
        "DAYTONA_TARGET": "test",
        "DAYTONA_API_URL": "https://example.test",
    }.items():
        monkeypatch.setenv(name, value)

    def unexpected(**kwargs: object) -> None:
        raise AssertionError("SDK constructed before valid authorization/registration")

    monkeypatch.setattr(module.SdkDaytonaRuntime, "from_credentials", unexpected)
    code = module.main(["--registration", str(registration), "--output", str(output), *flags])
    assert code == (2 if "--execute" in flags else 0)
    report = capsys.readouterr().out
    assert "secret-key" not in report
    assert json.loads(report)["status"] == "not_tested"
    assert not output.exists()
