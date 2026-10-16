"""Authenticated registered revisions retain identity through the actual Gate pipeline."""

import asyncio
from dataclasses import replace

import pytest
from test_c3_api import GH_SECRET, _github_post, _pr, _webhook_client
from test_c3_api import client as api_client  # noqa: F401

from gauntlet.api.container import get_container
from gauntlet.api.services.gate import GateService
from gauntlet.application.gate.run_gate import GateRunReport, RunGateUseCase
from gauntlet.contracts import ChangeRequest
from gauntlet.intake.github import RepositoryBinding, RunRequested, handle_pull_request_event

pytestmark = pytest.mark.usefixtures("api_client")


def test_registered_webhook_returns_run_and_deduplicates_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _webhook_client(
        monkeypatch, GITHUB_WEBHOOK_SECRET=GH_SECRET, GAUNTLET_GITHUB_REPOSITORIES="demo/cartwheel"
    )
    refs = get_container().gate.manifests["help-button"]
    payload = _pr("demo/cartwheel", refs["base_sha"], refs["head_sha"])
    payload["pull_request"]["title"] = "Preserve this authenticated PR intent"
    first = _github_post(hook, payload, "registered-delivery-1").json()
    second = _github_post(hook, payload, "registered-delivery-2").json()
    assert first["run_id"] and first["run_id"] == second["run_id"]
    runs = hook.get("/gate/runs").json()
    assert len(runs) == 1
    view = hook.get(f"/gate/runs/{first['run_id']}").json()
    assert view["feature_intent"] == payload["pull_request"]["title"]
    assert (view["base_sha"], view["head_sha"]) == (refs["base_sha"], refs["head_sha"])
    assert view["attempts"]


def requested(service: GateService) -> RunRequested:
    refs = service.manifests["help-button"]
    result = handle_pull_request_event(
        _pr("demo/cartwheel", refs["base_sha"], refs["head_sha"]),
        {
            "demo/cartwheel": RepositoryBinding(
                "cartwheel", refs["target_id"], refs["fixture_id"], 37
            )
        },
    )
    assert isinstance(result, RunRequested)
    return result


@pytest.mark.asyncio
async def test_registered_request_preserves_budget_in_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GAUNTLET_GITHUB_REPOSITORIES", "demo/cartwheel")
    service = get_container().gate
    service.settings = replace(service.settings, github_repositories=("demo/cartwheel",))
    request = requested(service)

    original = RunGateUseCase.execute
    received = []

    async def execute(
        self: RunGateUseCase, run_id: str, change: ChangeRequest, checksum: str
    ) -> GateRunReport:
        received.append((run_id, change))
        return await original(self, run_id, change, checksum)

    monkeypatch.setattr(RunGateUseCase, "execute", execute)
    view, duplicate = await asyncio.gather(
        service.start_requested(request), service.start_requested(request)
    )
    assert view == duplicate
    assert received == [(request.run_id, request.change)]
    assert view.run_id == request.run_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("base_sha", "a" * 40),
        ("head_sha", "b" * 40),
        ("fixture_id", "wrong"),
        ("target_id", "wrong"),
        ("repository_id", "wrong"),
    ],
)
async def test_mismatched_request_never_starts(field: str, value: str) -> None:
    service = get_container().gate
    service.settings = replace(service.settings, github_repositories=("demo/cartwheel",))
    request = requested(service)
    request = replace(request, change=request.change.model_copy(update={field: value}))
    with pytest.raises(ValueError):
        await service.start_requested(request)
    assert service.runs == {}


@pytest.mark.asyncio
async def test_check_published_for_executed_registered_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gauntlet.api.routes.webhooks import _run_and_publish
    from gauntlet.integrations.github_app import GitHubAppCheckRunPublisher
    from gauntlet.ports import CheckRunReport

    service = get_container().gate
    service.settings = replace(service.settings, github_repositories=("demo/cartwheel",))
    request = requested(service)
    view = await service.start_requested(request)
    published = []

    class Publisher:
        async def publish(self, repo: str, head: str, run_id: str, report: CheckRunReport) -> str:
            published.append((repo, head, run_id, report.conclusion))
            return "check-registered"

    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(type(service.settings), "missing_env", lambda self, name: ())
    monkeypatch.setattr(GitHubAppCheckRunPublisher, "from_settings", lambda settings: Publisher())
    await _run_and_publish(request, "delivery-publish")
    assert published == [("demo/cartwheel", view.head_sha, request.run_id, "failure")]
    assert service.runs[request.run_id].view.events[-1].payload == {
        "check_run_id": "check-registered"
    }


@pytest.mark.asyncio
async def test_unbound_repository_never_starts() -> None:
    service = get_container().gate
    request = replace(requested(service), repository_full_name="unbound/repo")
    with pytest.raises(ValueError):
        await service.start_requested(request)
    assert service.runs == {}
