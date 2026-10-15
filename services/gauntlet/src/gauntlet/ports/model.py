"""LLM access (Bedrock in production). Returns raw text; callers own parsing and validation."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelRequest:
    system: str
    user: str
    max_output_tokens: int
    temperature: float = 0.0


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model_id: str
    trace_id: str | None = None


class ModelGateway(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Raise EnvironmentUnavailableError if the provider cannot be reached."""
        ...
