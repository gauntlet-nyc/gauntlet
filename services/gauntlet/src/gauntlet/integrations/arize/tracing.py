"""Gauntlet tracing: planner calls, worker steps, oracle verdicts and Recall replays.

Spans carry IDs, hashes, counts and verdicts only — never prompts, page text, historical
customer content or keys. Export failures never fail a run: they are counted and logged.
`tracer_from_settings` returns a `NoopTracer` when ARIZE_API_KEY/ARIZE_SPACE_ID are unset.
"""

import logging
import os
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

import httpx

from gauntlet.settings import IntegrationSettings

from .otlp_proto import AttrValue, ProtoSpan, encode_export_request

_log = logging.getLogger("gauntlet.integrations.arize")

# OpenInference span kinds understood by Arize.
SpanKind = Literal["LLM", "CHAIN", "TOOL", "EVALUATOR", "AGENT"]
_MAX_BUFFER: Final = 2048
_MAX_ATTR_CHARS: Final = 512


@dataclass
class SpanRecord:
    """A live span. Set attributes while it runs; status becomes ERROR if the body raises."""

    name: str
    kind: SpanKind
    trace_id: str  # 32 hex
    span_id: str  # 16 hex
    parent_span_id: str | None
    start_ns: int
    attributes: dict[str, AttrValue] = field(default_factory=dict)
    end_ns: int = 0
    error: str | None = None

    def set(self, key: str, value: AttrValue | None) -> None:
        if value is None:
            return
        if isinstance(value, str) and len(value) > _MAX_ATTR_CHARS:
            value = value[:_MAX_ATTR_CHARS]
        self.attributes[key] = value


class Tracer(Protocol):
    def span(
        self, name: str, kind: SpanKind, attributes: Mapping[str, AttrValue | None] | None = None
    ) -> AbstractAsyncContextManager[SpanRecord]: ...

    async def flush(self) -> None: ...

    @property
    def label(self) -> str: ...


AsyncSpanContext = AbstractAsyncContextManager[SpanRecord]


_current: ContextVar[SpanRecord | None] = ContextVar("gauntlet_span", default=None)


def current_trace_id() -> str | None:
    span = _current.get()
    return span.trace_id if span is not None else None


class _BaseTracer:
    def __init__(self) -> None:
        self.finished: list[SpanRecord] = []

    @asynccontextmanager
    async def _span(
        self, name: str, kind: SpanKind, attributes: Mapping[str, AttrValue | None] | None
    ) -> AsyncIterator[SpanRecord]:
        parent = _current.get()
        record = SpanRecord(
            name=name,
            kind=kind,
            trace_id=parent.trace_id if parent else os.urandom(16).hex(),
            span_id=os.urandom(8).hex(),
            parent_span_id=parent.span_id if parent else None,
            start_ns=time.time_ns(),
        )
        record.set("openinference.span.kind", kind)
        for key, value in (attributes or {}).items():
            record.set(key, value)
        token = _current.set(record)
        try:
            yield record
        except BaseException as exc:
            record.error = type(exc).__name__
            raise
        finally:
            _current.reset(token)
            record.end_ns = time.time_ns()
            self._finish(record)

    def span(
        self, name: str, kind: SpanKind, attributes: Mapping[str, AttrValue | None] | None = None
    ) -> AsyncSpanContext:
        return self._span(name, kind, attributes)

    def _finish(self, record: SpanRecord) -> None:
        raise NotImplementedError


class NoopTracer(_BaseTracer):
    """Keeps parent/child IDs consistent but exports nothing and keeps nothing."""

    label = "arize_disabled_noop"

    def _finish(self, record: SpanRecord) -> None:
        return None

    async def flush(self) -> None:
        return None


class OtlpTracer(_BaseTracer):
    """Buffers finished spans and posts OTLP/HTTP protobuf to Arize on `flush`."""

    label = "arize_otlp"

    def __init__(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str],
        project_name: str,
        service_name: str = "gauntlet",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._headers = {**headers, "Content-Type": "application/x-protobuf"}
        self._resource: dict[str, AttrValue] = {
            "service.name": service_name,
            "model_id": project_name,
            "openinference.project.name": project_name,
        }
        self._transport = transport
        self._timeout = timeout_seconds
        self.exported = 0
        self.dropped = 0

    def _finish(self, record: SpanRecord) -> None:
        if len(self.finished) >= _MAX_BUFFER:
            self.dropped += 1
            return
        self.finished.append(record)

    async def flush(self) -> None:
        if not self.finished:
            return
        batch, self.finished = self.finished, []
        body = encode_export_request(
            self._resource, "gauntlet", [_to_proto(span) for span in batch]
        )
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(self._endpoint, content=body, headers=self._headers)
        except httpx.HTTPError as exc:
            self.dropped += len(batch)
            _log.warning(
                "Arize export failed (%s); %d spans dropped", type(exc).__name__, len(batch)
            )
            return
        if response.status_code >= 300:
            self.dropped += len(batch)
            _log.warning("Arize export HTTP %d; %d spans dropped", response.status_code, len(batch))
            return
        self.exported += len(batch)


def _to_proto(span: SpanRecord) -> ProtoSpan:
    attributes = dict(span.attributes)
    if span.error:
        attributes["exception.type"] = span.error
    return ProtoSpan(
        trace_id=bytes.fromhex(span.trace_id),
        span_id=bytes.fromhex(span.span_id),
        parent_span_id=bytes.fromhex(span.parent_span_id) if span.parent_span_id else None,
        name=span.name,
        kind=3 if span.kind == "LLM" else 1,
        start_ns=span.start_ns,
        end_ns=span.end_ns or span.start_ns,
        attributes=attributes,
        status_code=2 if span.error else 1,
        status_message=span.error or "",
    )


def tracer_from_settings(settings: IntegrationSettings) -> NoopTracer | OtlpTracer:
    """Arize when configured AND live integrations are enabled; otherwise a labeled no-op."""
    if settings.arize is None or not settings.core.run_live_integrations:
        return NoopTracer()
    return OtlpTracer(
        endpoint=settings.arize.otlp_endpoint,
        headers={
            "space_id": settings.arize.space_id.reveal(),
            "api_key": settings.arize.api_key.reveal(),
        },
        project_name=settings.arize.project_name,
    )
