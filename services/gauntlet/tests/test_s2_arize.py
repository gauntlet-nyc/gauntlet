"""Arize tracing: OTLP protobuf shape, no-op when unset, export never fails a run."""

import asyncio
import struct
from typing import Any

import httpx
import pytest

from gauntlet.contracts import ReplayResult
from gauntlet.integrations.arize import (
    NoopTracer,
    OtlpTracer,
    TracedModelGateway,
    TracedReplayEngine,
    tracer_from_settings,
)
from gauntlet.integrations.arize.experiments import record_counterfactual_experiment
from gauntlet.ports.model import ModelRequest, ModelResponse
from gauntlet.settings import load_settings

KEY = "synthetic-arize-key-123456"


def _decode(data: bytes) -> list[tuple[int, Any]]:
    """Tiny protobuf reader: list of (field, value); length-delimited values stay bytes."""
    out: list[tuple[int, Any]] = []
    i = 0
    while i < len(data):
        key, i = _varint(data, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(data, i)
        elif wire == 1:
            value = struct.unpack("<Q", data[i : i + 8])[0]
            i += 8
        elif wire == 2:
            length, i = _varint(data, i)
            value = data[i : i + length]
            i += length
        else:
            raise AssertionError(f"unexpected wire type {wire}")
        out.append((field, value))
    return out


def _varint(data: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        byte = data[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7


def _spans(body: bytes) -> list[dict[str, Any]]:
    ((_, resource_spans),) = _decode(body)
    fields = dict(_decode(resource_spans))
    scope_spans = _decode(fields[2])
    spans = []
    for field, raw in scope_spans:
        if field != 2:
            continue
        span_fields = _decode(raw)
        attrs = {}
        for f, kv in span_fields:
            if f == 9:
                kvf = dict(_decode(kv))
                attrs[kvf[1].decode()] = dict(_decode(kvf[2]))
        plain = {f: v for f, v in span_fields if f != 9}
        spans.append(
            {
                "name": plain[5].decode(),
                "trace": plain[1],
                "span": plain[2],
                "parent": plain.get(4),
                "attrs": attrs,
                "status": dict(_decode(plain[15])),
            }
        )
    return spans


class _Model:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(text='{"attacks": []}', model_id="gpt-test")


def test_noop_when_arize_unset_or_live_disabled() -> None:
    assert isinstance(tracer_from_settings(load_settings({})), NoopTracer)
    configured = {"ARIZE_API_KEY": KEY, "ARIZE_SPACE_ID": "space-1"}
    assert isinstance(tracer_from_settings(load_settings(configured)), NoopTracer)
    live = tracer_from_settings(load_settings({**configured, "RUN_LIVE_INTEGRATIONS": "1"}))
    assert isinstance(live, OtlpTracer)


def test_export_shape_nesting_and_headers() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    tracer = OtlpTracer(
        endpoint="https://otlp.example/v1/traces",
        headers={"space_id": "space-1", "api_key": KEY},
        project_name="gauntlet-test",
        transport=httpx.MockTransport(handle),
    )

    async def scenario() -> None:
        async with tracer.span("gate.run", "CHAIN", {"gauntlet.run_id": "run-1"}):
            gateway = TracedModelGateway(_Model(), tracer)
            await gateway.complete(
                ModelRequest(system="secret system", user="u", max_output_tokens=10)
            )
        await tracer.flush()

    asyncio.run(scenario())
    request = seen[0]
    assert request.headers["content-type"] == "application/x-protobuf"
    assert request.headers["api_key"] == KEY
    spans = _spans(request.content)
    by_name = {s["name"]: s for s in spans}
    root, llm = by_name["gate.run"], by_name["gate.plan.model_call"]
    assert llm["trace"] == root["trace"] and llm["parent"] == root["span"]
    assert root["parent"] is None
    assert llm["attrs"]["llm.model_name"][1] == b"gpt-test"
    assert llm["attrs"]["openinference.span.kind"][1] == b"LLM"
    assert b"secret system" not in request.content  # prompt text is hashed, never sent
    assert root["status"][3] == 1
    assert tracer.exported == 2


def test_export_failure_is_counted_not_raised() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    tracer = OtlpTracer(
        endpoint="https://otlp.example/v1/traces",
        headers={},
        project_name="p",
        transport=httpx.MockTransport(boom),
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError):
            async with tracer.span("gate.run", "CHAIN"):
                raise RuntimeError("worker failed")
        await tracer.flush()

    asyncio.run(scenario())
    assert tracer.dropped == 1 and tracer.exported == 0


def test_replay_and_experiment_spans() -> None:
    bodies: list[bytes] = []
    tracer = OtlpTracer(
        endpoint="https://otlp.example/v1/traces",
        headers={},
        project_name="p",
        transport=httpx.MockTransport(lambda r: (bodies.append(r.content), httpx.Response(200))[1]),
    )

    class _Engine:
        async def replay(self, spec: object) -> ReplayResult:
            return ReplayResult(replay_id="rp-1", status="matched", observed_action="refund")

    control = ReplayResult(replay_id="rp-control", status="matched", observed_action="refund")
    counter = ReplayResult(replay_id="rp-cf", status="different", observed_action="deny")

    async def scenario() -> None:
        record = await record_counterfactual_experiment(
            tracer,
            experiment_id="exp-1",
            decision_id="dec-1",
            control=control,
            counterfactual=counter,
            control_matches=True,
            material_change=True,
            verdict="tainted",
        )
        assert record.variants == 2
        await tracer.flush()

    asyncio.run(scenario())
    names = {s["name"] for s in _spans(bodies[0])}
    assert names == {
        "recall.experiment",
        "recall.experiment.control",
        "recall.experiment.counterfactual",
        "recall.experiment.eval",
    }
    assert TracedReplayEngine  # wrapper exported for composition
