"""Azure OpenAI planning stays a bounded, validated, opt-in dev stand-in for Bedrock."""

import asyncio
import json

import httpx
import pytest
from conftest import DemoRepo
from fakes import StaticTargetCatalog
from test_a01c_live_planner import change, freeze_live_plan, main

from gauntlet.integrations.azure_openai import AzureOpenAIGateway, create_azure_openai_gateway
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelRequest

ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://demo-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "planner-gpt",
    "AZURE_OPENAI_API_KEY": "test-key-not-real",
}
REQUEST = ModelRequest(system="trusted instruction", user="untrusted json", max_output_tokens=64)


def completion(text: str, *, finish: str = "stop") -> dict[str, object]:
    return {
        "id": "chatcmpl-123",
        "choices": [
            {"finish_reason": finish, "message": {"role": "assistant", "content": text}}
        ],
    }


class Recorder:
    def __init__(self, status: int, body: object) -> None:
        self.status, self.body = status, body
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, json=self.body)

        return httpx.MockTransport(handle)


def test_request_shape_and_response_mapping() -> None:
    recorder = Recorder(200, completion('{"attacks": []}'))
    gateway = create_azure_openai_gateway(ENV, transport=recorder.transport())
    result = asyncio.run(gateway.complete(REQUEST))
    assert result.text == '{"attacks": []}'
    assert result.model_id == "azure-openai:planner-gpt"
    assert result.trace_id == "chatcmpl-123"
    sent = recorder.requests[0]
    assert str(sent.url) == (
        "https://demo-resource.openai.azure.com/openai/deployments/planner-gpt"
        "/chat/completions?api-version=2024-10-21"
    )
    assert sent.headers["api-key"] == "test-key-not-real"
    body = json.loads(sent.content)
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["max_completion_tokens"] == 64
    assert body["temperature"] == 0.0
    assert body["response_format"] == {"type": "json_object"}


def test_reasoning_deployments_omit_temperature() -> None:
    recorder = Recorder(200, completion("{}"))
    env = {**ENV, "AZURE_OPENAI_REASONING_MODEL": "1"}
    asyncio.run(create_azure_openai_gateway(env, transport=recorder.transport()).complete(REQUEST))
    assert "temperature" not in json.loads(recorder.requests[0].content)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"error": {"message": "test-key-not-real is invalid"}}),
        (200, completion("{}", finish="length")),
        (200, completion("   ")),
        (200, {"choices": []}),
        (200, ["not", "a", "mapping"]),
    ],
)
def test_unusable_responses_fail_closed_without_echoing(status: int, body: object) -> None:
    gateway = create_azure_openai_gateway(ENV, transport=Recorder(status, body).transport())
    with pytest.raises(EnvironmentUnavailableError) as error:
        asyncio.run(gateway.complete(REQUEST))
    assert "test-key-not-real" not in str(error.value)


def test_network_errors_hide_details() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret detail", request=request)

    gateway = create_azure_openai_gateway(ENV, transport=httpx.MockTransport(fail))
    with pytest.raises(EnvironmentUnavailableError) as error:
        asyncio.run(gateway.complete(REQUEST))
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://demo.openai.azure.com",
        "https://evil.example.com",
        "https://demo.openai.azure.com:8443",
        "https://demo.openai.azure.com/path",
        "https://user@demo.openai.azure.com",
    ],
)
def test_only_https_azure_resource_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError):
        create_azure_openai_gateway({**ENV, "AZURE_OPENAI_ENDPOINT": endpoint})


def test_missing_settings_name_the_key_not_the_value() -> None:
    with pytest.raises(ValueError, match="AZURE_OPENAI_API_KEY"):
        create_azure_openai_gateway({k: v for k, v in ENV.items() if k != "AZURE_OPENAI_API_KEY"})
    with pytest.raises(ValueError):
        AzureOpenAIGateway(endpoint=ENV["AZURE_OPENAI_ENDPOINT"], deployment="../x", api_key="k")


def test_azure_plan_goes_through_the_same_validator_and_freeze(demo_repo: DemoRepo) -> None:
    request = change(demo_repo)
    proposal = {
        "attack_id": "attack-ui-from-azure",
        "hypothesis": "The Help button may cover Checkout on narrow screens",
        "why_this_change": "The diff adds a fixed-position Help button",
        "expected_observation": "Checkout receives the click",
        "source_refs": [],
        "worker_kind": "ui",
        "target_id": request.target_id,
        "fixture_id": request.fixture_id,
        "steps": [{"action": "navigate", "path": "/checkout"}],
        "oracle_ids": ["ui.primary_action_reachable"],
        "max_actions": 4,
        "max_runtime_seconds": 90,
    }
    recorder = Recorder(200, completion(json.dumps({"attacks": [proposal]})))
    gateway = create_azure_openai_gateway(ENV, transport=recorder.transport())
    frozen, events = asyncio.run(
        freeze_live_plan(demo_repo.path, request, gateway, "trusted", StaticTargetCatalog())
    )
    # Uncited proposals are rejected exactly as they are for Bedrock.
    assert frozen.attacks == ()
    assert [item.attack_id for item in frozen.rejected] == ["attack[0]"]
    assert frozen.model_id == "azure-openai:planner-gpt"
    assert [event.event_type for event in events] == ["impact_mapped", "plan_frozen"]


def test_probe_reports_missing_azure_settings_without_spend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "REPLACE_WITH_KEY")
    assert main(["--provider", "azure"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["provider"] == "azure"
    assert report["sponsor_evidence"] is False
    assert {"AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"} <= set(report["missing"])
    assert "--region" not in report["missing"]


def test_foundry_v1_base_url_puts_deployment_in_the_body() -> None:
    recorder = Recorder(200, completion("{}"))
    env = {**ENV, "AZURE_OPENAI_ENDPOINT": "https://demo-res.services.ai.azure.com/openai/v1/"}
    asyncio.run(create_azure_openai_gateway(env, transport=recorder.transport()).complete(REQUEST))
    sent = recorder.requests[0]
    assert str(sent.url) == "https://demo-res.services.ai.azure.com/openai/v1/chat/completions"
    assert json.loads(sent.content)["model"] == "planner-gpt"


def test_other_paths_are_still_refused() -> None:
    with pytest.raises(ValueError):
        create_azure_openai_gateway(
            {**ENV, "AZURE_OPENAI_ENDPOINT": "https://demo-res.services.ai.azure.com/openai/v2"}
        )
