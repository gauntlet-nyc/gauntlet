"""Reviewer authentication. Identity comes only from a server-side token table, never from a
request body or a client-asserted header. With no table configured every request is refused."""

import hmac
import json
import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ValidationError

from gauntlet.application.gate import AuthenticatedReviewer
from gauntlet.contracts import ApprovalChannel

TOKENS_ENV = "GAUNTLET_REVIEWER_TOKENS"


class _TokenEntry(BaseModel):
    reviewer_id: str
    channel: ApprovalChannel


def _load_table() -> dict[str, _TokenEntry]:
    raw = os.environ.get(TOKENS_ENV, "")
    if not raw:
        return {}
    try:
        return {t: _TokenEntry.model_validate(e) for t, e in json.loads(raw).items()}
    except (ValueError, AttributeError, ValidationError):
        return {}


def authenticated_reviewer(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedReviewer:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="reviewer authentication required")
    match: _TokenEntry | None = None
    for known, entry in _load_table().items():
        if hmac.compare_digest(known.encode(), token.encode()):
            match = entry
    if match is None:
        raise HTTPException(status_code=401, detail="reviewer authentication required")
    return AuthenticatedReviewer(reviewer_id=match.reviewer_id, channel=match.channel)


Reviewer = Annotated[AuthenticatedReviewer, Depends(authenticated_reviewer)]
