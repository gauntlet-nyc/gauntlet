"""Sponsor-proof panel data: which adapter produces what, and whether it has ever run live."""

from fastapi import APIRouter

from ..container import get_container
from ..schemas import SponsorStatus
from ..services.sponsors import sponsor_statuses

router = APIRouter(prefix="/sponsors", tags=["sponsors"])


@router.get("")
async def list_sponsors() -> list[SponsorStatus]:
    return sponsor_statuses(get_container().settings)
