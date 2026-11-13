"""Health endpoint implementing docs/API_CONTRACTS.md §4.1."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = "ok"
    version: str
    llm_mode: Literal["DISABLED", "ENABLED"]
    llm_provider: str | None = None
    regions_loaded: int = 0
    datasets_available: int = 0
    datasets_unavailable: int = 0


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns server status, version, LLM configuration mode, and loaded data counts.",
)
async def get_health() -> HealthResponse:
    """Return service health status and configuration."""
    settings = get_settings()

    provider = settings.MARSWALK_LLM_PROVIDER.strip().lower()
    if provider and provider != "none":
        llm_mode: Literal["DISABLED", "ENABLED"] = "ENABLED"
        llm_provider = settings.MARSWALK_LLM_PROVIDER
    else:
        llm_mode = "DISABLED"
        llm_provider = None

    return HealthResponse(
        status="ok",
        version=__version__,
        llm_mode=llm_mode,
        llm_provider=llm_provider,
        regions_loaded=0,
        datasets_available=0,
        datasets_unavailable=0,
    )
