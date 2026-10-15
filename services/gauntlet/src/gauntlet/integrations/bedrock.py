"""One Bedrock Converse request with explicit SDK I/O and token limits."""

import asyncio
import importlib
import re
from collections.abc import Mapping
from typing import Protocol, cast

from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelRequest, ModelResponse

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_RESPONSE_CHARS = 128_000


class ConverseClient(Protocol):
    def converse(self, **kwargs: object) -> Mapping[str, object]: ...


def _validate_model_id(model_id: str) -> None:
    if not model_id or len(model_id) > 256 or any(ch.isspace() for ch in model_id):
        raise ValueError("Bedrock model ID must be a nonempty single token")


class BedrockConverseGateway:
    """SDK connect/read limits and one attempt; no total wall-clock deadline."""

    def __init__(self, client: ConverseClient, model_id: str) -> None:
        _validate_model_id(model_id)
        self._client = client
        self._model_id = model_id

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not 1 <= request.max_output_tokens <= 8192 or not 0 <= request.temperature <= 1:
            raise ValueError("Bedrock inference limits are invalid")
        if (
            not request.system.strip()
            or not request.user.strip()
            or len(request.system) > 16_000
            or len(request.user) > 128_000
        ):
            raise ValueError("Bedrock input exceeds configured bounds")
        try:
            raw = await asyncio.to_thread(
                self._client.converse,
                modelId=self._model_id,
                system=[{"text": request.system}],
                messages=[{"role": "user", "content": [{"text": request.user}]}],
                inferenceConfig={
                    "maxTokens": request.max_output_tokens,
                    "temperature": request.temperature,
                },
            )
        except Exception:
            # Provider exception strings can include prompt text, endpoints or credentials.
            raise EnvironmentUnavailableError("Bedrock Converse request failed") from None
        if not isinstance(raw, Mapping) or raw.get("stopReason") != "end_turn":
            raise EnvironmentUnavailableError("Bedrock Converse response unusable")
        output = raw.get("output")
        if not isinstance(output, Mapping):
            raise EnvironmentUnavailableError("Bedrock Converse response unusable")
        message = output.get("message")
        if not isinstance(message, Mapping) or message.get("role") != "assistant":
            raise EnvironmentUnavailableError("Bedrock Converse response unusable")
        blocks = message.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise EnvironmentUnavailableError("Bedrock Converse response unusable")
        texts: list[str] = []
        for block in blocks:
            if not isinstance(block, Mapping) or set(block) != {"text"}:
                raise EnvironmentUnavailableError("Bedrock Converse response unusable")
            text = block.get("text")
            if not isinstance(text, str):
                raise EnvironmentUnavailableError("Bedrock Converse response unusable")
            texts.append(text)
        response_text = "".join(texts)
        if not response_text.strip() or len(response_text) > _MAX_RESPONSE_CHARS:
            raise EnvironmentUnavailableError("Bedrock Converse response unusable")
        metadata = raw.get("ResponseMetadata")
        request_id = metadata.get("RequestId") if isinstance(metadata, Mapping) else None
        trace_id = (
            request_id
            if isinstance(request_id, str) and _SAFE_REQUEST_ID.fullmatch(request_id)
            else None
        )
        return ModelResponse(response_text, self._model_id, trace_id)

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                raise EnvironmentUnavailableError("Bedrock client close failed") from None


def create_bedrock_gateway(*, model_id: str, region: str) -> BedrockConverseGateway:
    """Construct the optional SDK client only after the caller's spend preflight."""
    _validate_model_id(model_id)
    if not region or not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
        raise ValueError("AWS region must be explicit")
    try:
        boto3 = importlib.import_module("boto3")
        botocore_config = importlib.import_module("botocore.config")
    except ImportError:
        raise EnvironmentUnavailableError("Bedrock SDK is not installed") from None
    config = botocore_config.Config(
        connect_timeout=5,
        read_timeout=60,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    client = boto3.client("bedrock-runtime", region_name=region, config=config)
    return BedrockConverseGateway(cast(ConverseClient, client), model_id)
