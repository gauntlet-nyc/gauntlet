"""Bedrock planning stays typed, diff-cited, and opt-in."""

import asyncio
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from conftest import DemoRepo
from fakes import StaticTargetCatalog

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.contracts import ChangeImpactMap, ChangeRequest
from gauntlet.integrations.bedrock import BedrockConverseGateway, create_bedrock_gateway
from gauntlet.planning import compute_plan_hash
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelRequest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts/probe_p1_model_plan.py"
_SPEC = spec_from_file_location("probe_p1_model_plan", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("planner probe script could not be loaded")
probe_p1_model_plan = module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe_p1_model_plan)
freeze_live_plan = probe_p1_model_plan.freeze_live_plan
main = probe_p1_model_plan.main


def response(text: str, *, request_id: str = "request-123") -> dict[str, object]:
    return {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "ResponseMetadata": {"RequestId": request_id},
    }


class RecordingClient:
    def __init__(self, result: dict[str, object] | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def converse(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def change(repo: DemoRepo) -> ChangeRequest:
    return ChangeRequest(
        repository_id="cartwheel",
        base_sha=repo.base,
        head_sha=repo.ui_head,
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
    )


def test_gateway_sends_one_text_only_converse_request() -> None:
    client = RecordingClient(response('{"attacks": []}'))
    gateway = BedrockConverseGateway(client, "test-model")
    result = asyncio.run(
        gateway.complete(ModelRequest("trusted instruction", "untrusted diff", 500, 0.0))
    )
    assert result.text == '{"attacks": []}'
    assert result.model_id == "test-model"
    assert result.trace_id == "request-123"
    assert client.calls == [
        {
            "modelId": "test-model",
            "system": [{"text": "trusted instruction"}],
            "messages": [{"role": "user", "content": [{"text": "untrusted diff"}]}],
            "inferenceConfig": {"maxTokens": 500, "temperature": 0.0},
        }
    ]


def test_installed_boto3_converse_service_model_accepts_the_gateway_request() -> None:
    boto3 = pytest.importorskip("boto3")
    from botocore.config import Config
    from botocore.stub import Stubber

    client = boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="offline",
        aws_secret_access_key="offline",
        config=Config(connect_timeout=5, read_timeout=60, retries={"total_max_attempts": 1}),
    )
    stubber = Stubber(client)
    stubber.add_response(
        "converse",
        {
            **response('{"attacks": []}'),
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "metrics": {"latencyMs": 1},
        },
        {
            "modelId": "test-model",
            "system": [{"text": "system"}],
            "messages": [{"role": "user", "content": [{"text": "user"}]}],
            "inferenceConfig": {"maxTokens": 100, "temperature": 0.0},
        },
    )
    with stubber:
        result = asyncio.run(
            BedrockConverseGateway(client, "test-model").complete(
                ModelRequest("system", "user", 100)
            )
        )
        stubber.assert_no_pending_responses()
    assert result.text == '{"attacks": []}'
    client.close()


@pytest.mark.parametrize(
    "bad_response",
    [
        {**response("{}"), "stopReason": "max_tokens"},
        {
            **response("{}"),
            "output": {
                "message": {"role": "assistant", "content": [{"toolUse": {"name": "shell"}}]}
            },
        },
        {**response("{}"), "output": {"message": {"role": "user", "content": [{"text": "{}"}]}}},
        {**response("{}"), "output": {"message": {"role": "assistant", "content": []}}},
    ],
)
def test_gateway_rejects_incomplete_or_nontext_responses(bad_response: dict[str, object]) -> None:
    gateway = BedrockConverseGateway(RecordingClient(bad_response), "test-model")
    with pytest.raises(EnvironmentUnavailableError, match="Bedrock Converse response unusable"):
        asyncio.run(gateway.complete(ModelRequest("system", "user", 100)))


def test_gateway_sanitizes_provider_failure_and_unsafe_request_id() -> None:
    failing = BedrockConverseGateway(
        RecordingClient(RuntimeError("private credential or prompt")), "test-model"
    )
    with pytest.raises(EnvironmentUnavailableError, match="Bedrock Converse request failed") as exc:
        asyncio.run(failing.complete(ModelRequest("system", "user", 100)))
    assert "private" not in str(exc.value)
    invalid_id = BedrockConverseGateway(
        RecordingClient(response("{}", request_id="secret token with spaces")), "test-model"
    )
    result = asyncio.run(invalid_id.complete(ModelRequest("system", "user", 100)))
    assert result.trace_id is None


def test_gateway_rejects_oversized_input_before_a_paid_call() -> None:
    client = RecordingClient(response("{}"))
    gateway = BedrockConverseGateway(client, "test-model")
    with pytest.raises(ValueError, match="input exceeds"):
        asyncio.run(gateway.complete(ModelRequest("system", "x" * 128_001, 100)))
    assert client.calls == []


def test_gateway_rejects_malformed_raw_response() -> None:
    class InvalidClient:
        def converse(self, **kwargs: object) -> object:
            return ["not a response mapping"]

    gateway = BedrockConverseGateway(InvalidClient(), "test-model")  # type: ignore[arg-type]
    with pytest.raises(EnvironmentUnavailableError, match="Bedrock Converse response unusable"):
        asyncio.run(gateway.complete(ModelRequest("system", "user", 100)))


def test_real_diff_plan_composition_freezes_only_valid_model_proposals(demo_repo: DemoRepo) -> None:
    request = change(demo_repo)
    impact = asyncio.run(
        GitRepositoryInspector({"cartwheel": demo_repo.path}).inspect_change(request)
    )
    ref = next(surface for surface in impact.surfaces if surface.kind == "style").source_refs[0]
    proposal = {
        "attack_id": "attack-ui-from-model",
        "hypothesis": "Fixed control could cover a primary action at a narrow width",
        "why_this_change": "The cited changed line adds fixed positioning",
        "expected_observation": "The primary action receives the click",
        "source_refs": [ref.model_dump(mode="json")],
        "worker_kind": "ui",
        "target_id": request.target_id,
        "fixture_id": request.fixture_id,
        "steps": [
            {"action": "navigate", "path": "/checkout"},
            {"action": "resize", "width": 375, "height": 812},
            {"action": "inspect", "target": "checkout-primary-action"},
            {"action": "click", "target": "checkout-primary-action"},
        ],
        "oracle_ids": ["ui.primary_action_reachable"],
        "max_actions": 4,
        "max_runtime_seconds": 90,
    }
    rejected = {
        **proposal,
        "attack_id": "attack-uncited",
        "source_refs": [
            {"path": "README.md", "sha": request.head_sha, "start_line": 1, "end_line": 1}
        ],
    }
    client = RecordingClient(response(json.dumps({"attacks": [proposal, rejected]})))
    frozen, events = asyncio.run(
        freeze_live_plan(
            demo_repo.path,
            request,
            BedrockConverseGateway(client, "test-model"),
            "trusted instruction",
            StaticTargetCatalog(),
        )
    )
    assert [attack.attack_id for attack in frozen.attacks] == ["attack-ui-from-model"]
    assert [item.attack_id for item in frozen.rejected] == ["attack-uncited"]
    assert len(frozen.plan_hash) == 64
    assert [event.event_type for event in events] == ["impact_mapped", "plan_frozen"]
    assert events[-1].payload["plan_hash"] == frozen.plan_hash
    assert events[-1].trace_id == "request-123"
    assert "untrusted" in str(client.calls[0]["messages"])


def test_preflight_never_constructs_a_client_or_reads_a_change_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.delenv("RUN_LIVE_INTEGRATIONS", raising=False)
    missing = tmp_path / "missing-change.json"
    result = main(["--change-request", str(missing), "--repository", str(tmp_path)])
    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert report["status"] == "not_tested"
    assert "RUN_LIVE_INTEGRATIONS=1" in report["missing"]
    assert report["plan_hash"] is None


def test_preflight_rejects_existing_output_before_spend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")
    monkeypatch.setattr(
        probe_p1_model_plan,
        "create_bedrock_gateway",
        lambda **_: pytest.fail("client constructed before preflight"),
    )
    output = tmp_path / "existing.json"
    output.write_text("existing frozen plan")
    result = main(
        [
            "--repository",
            str(tmp_path),
            "--change-request",
            str(tmp_path / "missing.json"),
            "--model-id",
            "test-model",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert "unused --output" in report["missing"]
    assert output.read_text() == "existing frozen plan"


@pytest.mark.parametrize("invalid_output", ["dangling_symlink", "parent_is_file"])
def test_preflight_rejects_unusable_output_before_client_construction(
    invalid_output: str,
    demo_repo: DemoRepo,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")
    monkeypatch.setattr(
        probe_p1_model_plan,
        "create_bedrock_gateway",
        lambda **_: pytest.fail("client constructed with unusable output"),
    )
    change_path = tmp_path / "change.json"
    change_path.write_text(change(demo_repo).model_dump_json())
    if invalid_output == "dangling_symlink":
        output = tmp_path / "dangling.json"
        output.symlink_to(tmp_path / "missing.json")
    else:
        parent = tmp_path / "regular-file"
        parent.write_text("not a directory")
        output = parent / "frozen.json"
    result = main(
        [
            "--repository",
            str(demo_repo.path),
            "--change-request",
            str(change_path),
            "--model-id",
            "test-model",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert report["status"] == "not_tested"
    assert report["plan_hash"] is None
    if invalid_output == "dangling_symlink":
        assert output.is_symlink()
    else:
        assert parent.read_text() == "not a directory"


def test_reserved_output_is_removed_when_client_construction_fails(
    demo_repo: DemoRepo,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")

    reserved_at_construction: list[bool] = []

    def failed_client(**kwargs: object) -> None:
        reserved_at_construction.append(output.exists())
        raise RuntimeError("private error")

    monkeypatch.setattr(probe_p1_model_plan, "create_bedrock_gateway", failed_client)
    change_path = tmp_path / "change.json"
    change_path.write_text(change(demo_repo).model_dump_json())
    output = tmp_path / "reserved.json"
    result = main(
        [
            "--repository",
            str(demo_repo.path),
            "--change-request",
            str(change_path),
            "--model-id",
            "test-model",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 1
    assert report["status"] == "environment_error"
    assert reserved_at_construction == [True]
    assert not output.exists()


def test_factory_rejects_invalid_model_id_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto3 = pytest.importorskip("boto3")
    calls: list[object] = []
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError, match="model ID"):
        create_bedrock_gateway(model_id="bad model id", region="us-east-1")
    assert calls == []


def test_execute_writes_reproducible_frozen_inputs_and_closes_client(
    demo_repo: DemoRepo,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class ClosableClient(RecordingClient):
        closed = False

        def close(self) -> None:
            self.closed = True

    client = ClosableClient(response('{"attacks": []}'))
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")
    monkeypatch.setattr(
        probe_p1_model_plan,
        "create_bedrock_gateway",
        lambda **_: BedrockConverseGateway(client, "test-model"),
    )
    change_path = tmp_path / "change.json"
    change_path.write_text(change(demo_repo).model_dump_json())
    output = tmp_path / "frozen.json"
    result = main(
        [
            "--repository",
            str(demo_repo.path),
            "--change-request",
            str(change_path),
            "--model-id",
            "test-model",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    capsys.readouterr()
    report = json.loads(output.read_text())
    assert result == 0
    assert report["status"] == "not_tested"
    assert report["gate_status"] == "not_tested"
    assert report["planner_version"] == "planner.v1"
    assert report["change"] == change(demo_repo).model_dump(mode="json")
    assert report["plan_hash"] == compute_plan_hash(
        ChangeRequest.model_validate(report["change"]),
        ChangeImpactMap.model_validate(report["impact"]),
        (),
    )
    assert client.closed


def test_execute_reports_rejected_model_proposal_without_accepting_an_attack(
    demo_repo: DemoRepo,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    client = RecordingClient(response('{"attacks": [{"attack_id": "invalid"}]}'))
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")
    monkeypatch.setattr(
        probe_p1_model_plan,
        "create_bedrock_gateway",
        lambda **_: BedrockConverseGateway(client, "test-model"),
    )
    change_path = tmp_path / "change.json"
    change_path.write_text(change(demo_repo).model_dump_json())
    output = tmp_path / "rejected.json"
    result = main(
        [
            "--repository",
            str(demo_repo.path),
            "--change-request",
            str(change_path),
            "--model-id",
            "test-model",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    capsys.readouterr()
    report = json.loads(output.read_text())
    assert result == 0
    assert report["status"] == "rejected"
    assert report["accepted_attacks"] == 0
    assert report["rejected_attacks"] == 1
    assert report["attacks"] == []
    assert report["gate_status"] == "not_tested"
