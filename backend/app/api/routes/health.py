"""Health endpoint implementing docs/API_CONTRACTS.md section 4.1."""

from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.models import HealthResponse, LlmMode
from app.services import region_service

router = APIRouter(tags=["Health"])


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
    if provider == "anthropic" and settings.ANTHROPIC_API_KEY.strip():
        llm_mode = LlmMode.ENABLED
        llm_provider = settings.MARSWALK_LLM_PROVIDER
    elif provider == "openai" and settings.OPENAI_API_KEY.strip():
        llm_mode = LlmMode.ENABLED
        llm_provider = settings.MARSWALK_LLM_PROVIDER
    else:
        llm_mode = LlmMode.DISABLED
        llm_provider = None

    regions_loaded, datasets_avail, datasets_unavail = region_service.get_data_counts()

    return HealthResponse(
        status="ok",
        version=__version__,
        llm_mode=llm_mode,
        llm_provider=llm_provider,
        regions_loaded=regions_loaded,
        datasets_available=datasets_avail,
        datasets_unavailable=datasets_unavail,
    )
