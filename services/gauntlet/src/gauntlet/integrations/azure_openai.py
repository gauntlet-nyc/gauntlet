"""One Azure OpenAI chat-completions request over plain HTTPS; no provider SDK.

Development stand-in for the planner's model port while Bedrock access is pending. It is
not Bedrock sponsor evidence. Output is untrusted text: the planner validator decides.
"""

import re
from collections.abc import Mapping
from typing import Final
from urllib.parse import quote, urlsplit

import httpx

from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelRequest, ModelResponse

DEFAULT_API_VERSION: Final = "2024-10-21"
_MAX_RESPONSE_CHARS: Final = 128_000
_MAX_RESPONSE_BYTES: Final = 1_000_000
_SAFE_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DEPLOYMENT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_API_VERSION: Final = re.compile(r"^\d{4}-\d{2}-\d{2}(?:-preview)?$")
_AZURE_HOSTS: Final = (".openai.azure.com", ".cognitiveservices.azure.com")


def _endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value.rstrip("/"))
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Azure OpenAI endpoint is malformed") from None
    if (
        parsed.scheme != "https"
        or host is None
        or not host.endswith(_AZURE_HOSTS)
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.username is not None
    ):
        raise ValueError("Azure OpenAI endpoint must be an https://<resource> Azure host")
    return f"https://{host}"


class AzureOpenAIGateway:
    """Connect/read timeouts and one attempt; no redirects or proxy environment."""

    def __init__(
        self,
        *,
        endpoint: str,
        deployment: str,
        api_key: str,
        api_version: str = DEFAULT_API_VERSION,
        reasoning_model: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not _DEPLOYMENT.fullmatch(deployment):
            raise ValueError("Azure OpenAI deployment name is invalid")
        if not _API_VERSION.fullmatch(api_version):
            raise ValueError("Azure OpenAI API version is invalid")
        if not api_key.strip():
            raise ValueError("Azure OpenAI API key is required")
        self._url = (
            f"{_endpoint(endpoint)}/openai/deployments/{quote(deployment, safe='')}"
            f"/chat/completions?api-version={api_version}"
        )
        self._deployment = deployment
        self._api_key = api_key
        self._reasoning_model = reasoning_model
        self._transport = transport

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not 1 <= request.max_output_tokens <= 8192 or not 0 <= request.temperature <= 1:
            raise ValueError("Azure OpenAI inference limits are invalid")
        if (
            not request.system.strip()
            or not request.user.strip()
            or len(request.system) > 16_000
            or len(request.user) > 128_000
        ):
            raise ValueError("Azure OpenAI input exceeds configured bounds")
        body: dict[str, object] = {
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if not self._reasoning_model:
            # Reasoning deployments only accept their default temperature.
            body["temperature"] = request.temperature
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(60, connect=5),
            ) as client:
                response = await client.post(
                    self._url, json=body, headers={"api-key": self._api_key}
                )
        except httpx.HTTPError:
            # Exception text can include the endpoint or request; never surface it.
            raise EnvironmentUnavailableError("Azure OpenAI request failed") from None
        if response.status_code != 200 or len(response.content) > _MAX_RESPONSE_BYTES:
            raise EnvironmentUnavailableError(
                f"Azure OpenAI request failed with HTTP {response.status_code}"
            )
        try:
            raw = response.json()
        except ValueError:
            raise EnvironmentUnavailableError("Azure OpenAI response unusable") from None
        text = _completion_text(raw)
        request_id = response.headers.get("apim-request-id") or (
            raw.get("id") if isinstance(raw, Mapping) else None
        )
        trace_id = (
            request_id
            if isinstance(request_id, str) and _SAFE_REQUEST_ID.fullmatch(request_id)
            else None
        )
        return ModelResponse(text, f"azure-openai:{self._deployment}", trace_id)

    def close(self) -> None:
        """Each request owns its client; nothing stays open between calls."""


def _completion_text(raw: object) -> str:
    unusable = EnvironmentUnavailableError("Azure OpenAI response unusable")
    if not isinstance(raw, Mapping):
        raise unusable
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise unusable
    choice = choices[0]
    message = choice.get("message")
    if choice.get("finish_reason") != "stop" or not isinstance(message, Mapping):
        raise unusable
    text = message.get("content")
    if (
        message.get("role") != "assistant"
        or message.get("tool_calls")
        or not isinstance(text, str)
        or not text.strip()
        or len(text) > _MAX_RESPONSE_CHARS
    ):
        raise unusable
    return text


def create_azure_openai_gateway(
    environment: Mapping[str, str], *, transport: httpx.AsyncBaseTransport | None = None
) -> AzureOpenAIGateway:
    """Build from AZURE_OPENAI_* settings. Values are never echoed in errors."""
    try:
        return AzureOpenAIGateway(
            endpoint=environment["AZURE_OPENAI_ENDPOINT"],
            deployment=environment["AZURE_OPENAI_DEPLOYMENT"],
            api_key=environment["AZURE_OPENAI_API_KEY"],
            api_version=environment.get("AZURE_OPENAI_API_VERSION") or DEFAULT_API_VERSION,
            reasoning_model=environment.get("AZURE_OPENAI_REASONING_MODEL") == "1",
            transport=transport,
        )
    except KeyError as exc:
        raise ValueError(f"missing Azure OpenAI setting {exc.args[0]}") from None
