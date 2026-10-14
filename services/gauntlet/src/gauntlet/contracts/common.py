"""Base wire models and immutable evidence references."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"


class EvidenceRef(StrictDTO):
    artifact_id: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    media_type: str = Field(min_length=1)
    created_at: datetime
    trace_id: str | None = None


class SourceRef(StrictDTO):
    path: str = Field(min_length=1)
    sha: str = Field(min_length=7)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str | None = None
