"""Dev-grade reviewer authentication (demo only).

Identity comes only from the server-side GAUNTLET_REVIEWER_TOKENS table, never from a request
body or a client-asserted header. With no table configured every approval request is refused.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from gauntlet.application.gate import AuthenticatedReviewer

from .settings import get_settings


def authenticated_reviewer(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedReviewer:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="reviewer authentication required")
    reviewer = get_settings().reviewer_for(token)
    if reviewer is None:
        raise HTTPException(status_code=401, detail="reviewer authentication required")
    return AuthenticatedReviewer(reviewer_id=reviewer.reviewer_id, channel=reviewer.channel)


Reviewer = Annotated[AuthenticatedReviewer, Depends(authenticated_reviewer)]
