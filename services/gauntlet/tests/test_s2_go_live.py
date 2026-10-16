"""Go-live check: names only, sanitized failures, cleanup of anything a probe creates."""

import asyncio
import sys
from types import SimpleNamespace

import pytest

from gauntlet.execution import go_live_probes
from gauntlet.execution.go_live import exit_code, render, run_check
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import load_settings

SECRET = "synthetic-anchor-key-0123456789"
ENV = {
    "RUN_LIVE_INTEGRATIONS": "1",
    "ANCHOR_API_KEY": SECRET,
    "GAUNTLET_ANCHOR_REQUIRE_PROXY": "0",
    "ARIZE_API_KEY": "arize-key-0123456789",
    "ARIZE_SPACE_ID": "space-1",
    "DAYTONA_API_KEY": "daytona-key-0123456789",
    "DAYTONA_TARGET": "us",
}


def test_config_only_lists_missing_names_never_values() -> None:
    results = asyncio.run(run_check(ENV, load_settings(ENV), probe=False, probes={}))
    by = {r.sponsor: r for r in results}
    assert by["anchor"].status == "ready" and by["daytona"].status == "ready"
    assert by["github_app"].status == "missing" and "GITHUB_APP_ID" in by["github_app"].detail
    text = render(results, probed=False)
    assert SECRET not in text and "configuration only" in text
    assert exit_code(results) == 0


def test_probe_results_are_sanitized_and_exit_nonzero() -> None:
    async def ok(settings: object) -> str:
        return "fine"

    async def leaky(settings: object) -> str:
        raise RuntimeError(f"401 for key {SECRET}")

    async def ours(settings: object) -> str:
        raise EnvironmentUnavailableError(f"Arize rejected {SECRET}")

    async def slow(settings: object) -> str:
        await asyncio.sleep(5)
        return "never"

    probes = {"anchor": leaky, "arize": ours, "daytona": slow}
    results = asyncio.run(
        run_check(ENV, load_settings(ENV), probe=True, probes=probes, timeout_seconds=0.05)
    )
    by = {r.sponsor: r for r in results}
    assert by["anchor"].detail == "RuntimeError"  # foreign message dropped entirely
    assert by["arize"].detail == "EnvironmentUnavailableError: Arize rejected ***"
    assert by["daytona"].status == "probe_failed" and "TimeoutError" in by["daytona"].detail
    assert SECRET not in render(results, probed=True)
    assert exit_code(results) == 1
    probes_ok = {"anchor": ok, "arize": ok, "daytona": ok}
    results = asyncio.run(run_check(ENV, load_settings(ENV), probe=True, probes=probes_ok))
    assert exit_code(results) == 0


def test_probe_needs_live_flag() -> None:
    env = {**ENV, "RUN_LIVE_INTEGRATIONS": "0"}
    results = asyncio.run(run_check(env, load_settings(env), probe=True, probes={}))
    assert {r.status for r in results if r.sponsor == "anchor"} == {"not_probed"}


class _FakeAnchor:
    instances: list["_FakeAnchor"] = []

    def __init__(self, *, api_key: str, max_retries: int, timeout: float) -> None:
        self.created: list[dict[str, object]] = []
        self.deleted: list[str] = []
        self.closed = False
        self.fail_after_create = False
        self.sessions = self
        _FakeAnchor.instances.append(self)

    async def create_session(self, **kwargs: object) -> SimpleNamespace:
        self.created.append(kwargs)
        return SimpleNamespace(data=SimpleNamespace(id="anchor-probe-1"))

    async def delete_session(self, session_id: str, *, timeout: float) -> None:
        self.deleted.append(session_id)

    async def close(self) -> None:
        self.closed = True


def test_anchor_probe_creates_then_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAnchor.instances.clear()
    monkeypatch.setitem(
        sys.modules, "anchorbrowser", SimpleNamespace(AsyncAnchorbrowser=_FakeAnchor)
    )
    detail = asyncio.run(go_live_probes.probe_anchor(load_settings(ENV)))
    client = _FakeAnchor.instances[0]
    assert client.deleted == ["anchor-probe-1"] and client.closed
    assert "proxy" not in client.created[0]["session"]  # type: ignore[operator]
    assert "WITHOUT egress proxy" in detail


def test_anchor_probe_reports_undeleted_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class Stuck(_FakeAnchor):
        async def delete_session(self, session_id: str, *, timeout: float) -> None:
            raise RuntimeError("500")

    monkeypatch.setitem(sys.modules, "anchorbrowser", SimpleNamespace(AsyncAnchorbrowser=Stuck))
    with pytest.raises(EnvironmentUnavailableError, match="anchor-probe-1 was created but NOT"):
        asyncio.run(go_live_probes.probe_anchor(load_settings(ENV)))


def test_daytona_probe_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Snapshots:
        async def list(self, page: int, limit: int) -> SimpleNamespace:
            calls.append(f"list:{page}:{limit}")
            return SimpleNamespace(total=3)

    class Client:
        def __init__(self, config: object) -> None:
            self.snapshot = Snapshots()

        async def close(self) -> None:
            calls.append("close")

    fake = SimpleNamespace(AsyncDaytona=Client, DaytonaConfig=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "daytona", fake)
    detail = asyncio.run(go_live_probes.probe_daytona(load_settings(ENV)))
    assert calls == ["list:1:1", "close"] and detail == "3 snapshots visible"
