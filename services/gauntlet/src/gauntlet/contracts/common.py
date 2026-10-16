"""Base wire model, constrained scalar types and immutable evidence references."""

from typing import Annotated, Literal, Self
from urllib.parse import unquote

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_TEXT = 5000
MAX_ITEMS = 100

Identifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{7,64}$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
OracleId = Annotated[str, Field(max_length=128, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")]
VersionTag = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
]
ShortText = Annotated[str, Field(min_length=1, max_length=2500)]
UtcDatetime = AwareDatetime


def _reject_unsafe_relative_path(value: str) -> str:
    if value.startswith(("/", "~")) or "\\" in value or ":" in value:
        raise ValueError("path must be repository-relative")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("path must not contain empty, '.' or '..' segments")
    return value


MAX_PERCENT_DECODE_ROUNDS = 3


def _reject_non_route_path(value: str) -> str:
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise ValueError("route must not contain control characters")
    path = value.split("#", 1)[0].split("?", 1)[0]
    # Browsers and servers percent-decode paths, so check what the path becomes, not only how
    # it is spelled: /%2e%2e/admin resolves to /admin and /%2f%2fhost to //host.
    for _ in range(MAX_PERCENT_DECODE_ROUNDS):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    else:
        raise ValueError("route is over-encoded")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        raise ValueError("route must not contain control characters")
    if not value.startswith("/") or path.startswith("//") or "\\" in path:
        raise ValueError("route must be an origin-relative path such as /checkout")
    if any(ch.isspace() for ch in value.split("#", 1)[0].split("?", 1)[0]):
        raise ValueError("route must not contain literal whitespace")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise ValueError("route must not contain '.' or '..' segments")
    return value


RelativePath = Annotated[
    str, Field(min_length=1, max_length=512), AfterValidator(_reject_unsafe_relative_path)
]
RoutePath = Annotated[
    str, Field(min_length=1, max_length=2048), AfterValidator(_reject_non_route_path)
]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"


class EvidenceRef(StrictDTO):
    artifact_id: Identifier
    sha256: Sha256Hex
    media_type: str = Field(min_length=1, max_length=128)
    created_at: UtcDatetime
    trace_id: Identifier | None = None


class SourceRef(StrictDTO):
    path: RelativePath
    sha: GitSha
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: Sha256Hex | None = None

    @model_validator(mode="after")
    def lines_ordered(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class MissingInput(StrictDTO):
    """A replay/historical input that was not recorded, and why. Missing never means safe."""

    field: Identifier
    reason: ShortText
    critical: bool
