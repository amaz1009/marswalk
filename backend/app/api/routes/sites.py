"""Site evaluation endpoints stub implementing docs/API_CONTRACTS.md §4.17 (P1, WP-19)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import SiteEvaluation, SiteEvaluationRequest

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.post(
    "/evaluate",
    response_model=list[SiteEvaluation],
    summary="Evaluate candidate sites",
    description="Multi-criteria assessment and ranking of candidate landing or base locations.",
)
async def evaluate_sites(request: SiteEvaluationRequest) -> list[SiteEvaluation]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
