"""Port wrappers that add spans without changing behaviour. Composition decides to wrap.

Each wrapper delegates exactly once and re-raises errors unchanged; tracing never decides
anything. Only IDs, hashes, counts and verdict enums are recorded.
"""

import hashlib
from collections.abc import Sequence

from gauntlet.contracts import (
    AttackSpec,
    Observation,
    OracleVerdict,
    ReplayResult,
    ReplaySpec,
    WorkerKind,
)
from gauntlet.ports.model import ModelGateway, ModelRequest, ModelResponse
from gauntlet.ports.oracle import OracleDescriptor, TrustedOracleRegistry
from gauntlet.ports.replay import ReplayEngine
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.ports.worker import TestWorker

from .tracing import Tracer


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TracedModelGateway:
    def __init__(self, inner: ModelGateway, tracer: Tracer, *, purpose: str = "gate.plan") -> None:
        self._inner = inner
        self._tracer = tracer
        self._purpose = purpose

    async def complete(self, request: ModelRequest) -> ModelResponse:
        async with self._tracer.span(
            f"{self._purpose}.model_call",
            "LLM",
            {
                "gauntlet.purpose": self._purpose,
                "llm.invocation_parameters.max_output_tokens": request.max_output_tokens,
                "llm.invocation_parameters.temperature": float(request.temperature),
                "gauntlet.prompt_sha256": _sha(request.system + "\n" + request.user),
            },
        ) as span:
            response = await self._inner.complete(request)
            span.set("llm.model_name", response.model_id)
            span.set("gauntlet.output_sha256", _sha(response.text))
            span.set("gauntlet.output_chars", len(response.text))
            span.set("gauntlet.provider_trace_id", response.trace_id)
            return response


class TracedWorker:
    def __init__(self, inner: TestWorker, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer

    @property
    def kind(self) -> WorkerKind:
        return self._inner.kind

    async def run(self, spec: AttackSpec, environment: EnvironmentHandle) -> Observation:
        async with self._tracer.span(
            f"gate.worker.{self._inner.kind}",
            "TOOL",
            {
                "gauntlet.attack_id": spec.attack_id,
                "gauntlet.environment_id": environment.environment_id,
                "gauntlet.source_sha": environment.source_sha,
                "gauntlet.step_count": len(spec.steps),
            },
        ) as span:
            observation = await self._inner.run(spec, environment)
            span.set("gauntlet.observation_id", observation.observation_id)
            span.set("gauntlet.observation_status", observation.status)
            span.set("gauntlet.actions_recorded", len(observation.action_log))
            span.set("gauntlet.evidence_count", len(observation.evidence_ids))
            return observation


class TracedOracleRegistry:
    """Registry wrapper; `evaluate` is synchronous in the port, so spans are recorded after."""

    def __init__(self, inner: TrustedOracleRegistry, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer
        self.pending: list[OracleVerdict] = []

    def is_registered(self, oracle_id: str) -> bool:
        return self._inner.is_registered(oracle_id)

    def descriptors(self) -> Sequence[OracleDescriptor]:
        return self._inner.descriptors()

    def descriptor(self, oracle_id: str) -> OracleDescriptor:
        return self._inner.descriptor(oracle_id)

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        verdict = self._inner.evaluate(oracle_id, observation)
        self.pending.append(verdict)
        return verdict

    async def record_pending(self) -> None:
        """Emit one EVALUATOR span per verdict produced since the last call."""
        verdicts, self.pending = self.pending, []
        for verdict in verdicts:
            async with self._tracer.span(
                "gate.oracle.verdict",
                "EVALUATOR",
                {
                    "gauntlet.oracle_id": verdict.oracle_id,
                    "gauntlet.oracle_kind": verdict.oracle_kind,
                    "gauntlet.criterion_version": verdict.criterion_version,
                    "gauntlet.observation_id": verdict.observation_id,
                    "gauntlet.verdict_id": verdict.verdict_id,
                    "eval.label": verdict.outcome,
                },
            ):
                pass


class TracedReplayEngine:
    def __init__(self, inner: ReplayEngine, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer

    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        async with self._tracer.span(
            f"recall.replay.{spec.mode}",
            "CHAIN",
            {
                "gauntlet.replay_id": spec.replay_id,
                "gauntlet.replay_mode": spec.mode,
                "gauntlet.decision_id": spec.decision_id,
                "gauntlet.source_sha": spec.source_sha,
                "gauntlet.fixture_checksum": spec.fixture_checksum,
            },
        ) as span:
            result = await self._inner.replay(spec)
            span.set("gauntlet.replay_status", result.status)
            span.set("gauntlet.observed_action", result.observed_action)
            span.set("gauntlet.limitations", len(result.limitations))
            return result
