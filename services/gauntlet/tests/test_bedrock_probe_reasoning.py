"""The opt-in planner probe forwards the reasoning setting to Bedrock."""

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from conftest import DemoRepo

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.bedrock import BedrockConverseGateway


def test_probe_uses_reasoning_mode(
    demo_repo: DemoRepo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts/probe_p1_model_plan.py"
    spec = spec_from_file_location("probe_reasoning", script)
    assert spec is not None and spec.loader is not None
    probe = module_from_spec(spec)
    spec.loader.exec_module(probe)

    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def converse(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(kwargs)
            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"reasoningContent": {"reasoningText": {"text": "private"}}},
                            {"text": '{"attacks": []}'},
                        ],
                    }
                },
            }

        def close(self) -> None:
            pass

    client = Client()
    selected: list[bool] = []

    def gateway(
        *, model_id: str, region: str, reasoning_model: bool = False
    ) -> BedrockConverseGateway:
        selected.append(reasoning_model)
        return BedrockConverseGateway(client, model_id, reasoning_model=reasoning_model)

    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setenv("BEDROCK_REASONING_MODEL", "1")
    monkeypatch.setattr(probe.importlib.metadata, "version", lambda _: "1.43.114")
    monkeypatch.setattr(probe, "create_bedrock_gateway", gateway)
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=demo_repo.base,
        head_sha=demo_repo.ui_head,
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
    )
    change_path = tmp_path / "change.json"
    change_path.write_text(change.model_dump_json())
    output = tmp_path / "plan.json"
    result = probe.main(
        [
            "--repository",
            str(demo_repo.path),
            "--change-request",
            str(change_path),
            "--model-id",
            "us.openai.gpt-6-luna",
            "--region",
            "us-east-1",
            "--output",
            str(output),
            "--execute",
            "--authorize-spend",
        ]
    )
    capsys.readouterr()
    assert result == 0
    assert json.loads(output.read_text())["plan_hash"]
    assert selected == [True]
    assert len(client.calls) == 1
    assert "temperature" not in client.calls[0]["inferenceConfig"]


def test_invalid_reasoning_setting_is_reported_before_client_creation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts/probe_p1_model_plan.py"
    spec = spec_from_file_location("probe_invalid_reasoning", script)
    assert spec is not None and spec.loader is not None
    probe = module_from_spec(spec)
    spec.loader.exec_module(probe)
    monkeypatch.setenv("BEDROCK_REASONING_MODEL", "invalid")
    monkeypatch.setattr(
        probe, "create_bedrock_gateway", lambda **_: pytest.fail("client was constructed")
    )
    result = probe.main(["--provider", "bedrock"])
    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert "valid BEDROCK_REASONING_MODEL" in report["missing"]
