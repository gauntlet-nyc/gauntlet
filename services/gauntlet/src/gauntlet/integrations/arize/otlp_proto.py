"""Hand-written protobuf encoding of the OTLP `ExportTraceServiceRequest` subset we emit.

No protobuf/OTel SDK dependency. Field numbers follow opentelemetry-proto v1:
trace/v1/trace.proto, common/v1/common.proto, resource/v1/resource.proto.
"""

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

AttrValue = str | bool | int | float


def _varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _len(field: int, payload: bytes) -> bytes:
    return _key(field, 2) + _varint(len(payload)) + payload


def _str(field: int, value: str) -> bytes:
    return _len(field, value.encode("utf-8"))


def _fixed64(field: int, value: int) -> bytes:
    return _key(field, 1) + struct.pack("<Q", value)


def any_value(value: AttrValue) -> bytes:
    if isinstance(value, bool):
        return _key(2, 0) + _varint(int(value))
    if isinstance(value, int):
        return _key(3, 0) + _varint(value)
    if isinstance(value, float):
        return _key(4, 1) + struct.pack("<d", value)
    return _str(1, value)


def key_value(key: str, value: AttrValue) -> bytes:
    return _str(1, key) + _len(2, any_value(value))


def _attributes(field: int, attributes: Mapping[str, AttrValue]) -> bytes:
    return b"".join(_len(field, key_value(k, v)) for k, v in sorted(attributes.items()))


@dataclass(frozen=True)
class ProtoSpan:
    trace_id: bytes  # 16 bytes
    span_id: bytes  # 8 bytes
    parent_span_id: bytes | None
    name: str
    kind: int  # 1 internal, 3 client
    start_ns: int
    end_ns: int
    attributes: Mapping[str, AttrValue]
    status_code: int  # 0 unset, 1 ok, 2 error
    status_message: str = ""


def encode_span(span: ProtoSpan) -> bytes:
    out = _len(1, span.trace_id) + _len(2, span.span_id)
    if span.parent_span_id:
        out += _len(4, span.parent_span_id)
    out += _str(5, span.name) + _key(6, 0) + _varint(span.kind)
    out += _fixed64(7, span.start_ns) + _fixed64(8, span.end_ns)
    out += _attributes(9, span.attributes)
    status = b""
    if span.status_message:
        status += _str(2, span.status_message)
    status += _key(3, 0) + _varint(span.status_code)
    return out + _len(15, status)


def encode_export_request(
    resource: Mapping[str, AttrValue], scope_name: str, spans: Sequence[ProtoSpan]
) -> bytes:
    resource_msg = _attributes(1, resource)
    scope_msg = _str(1, scope_name)
    scope_spans = _len(1, scope_msg) + b"".join(_len(2, encode_span(s)) for s in spans)
    resource_spans = _len(1, resource_msg) + _len(2, scope_spans)
    return _len(1, resource_spans)
