from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    mode: str
    provider_integrations: str


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", mode="offline-demo", provider_integrations="offline-tested, live NOT RUN"
    )
