"""Route planning endpoints stub implementing docs/API_CONTRACTS.md §4.12 (P0, WP-11)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import RoutePlanRequest, RoutePlanResponse

router = APIRouter(prefix="/routes", tags=["Routes"])


@router.post(
    "/plan",
    response_model=RoutePlanResponse,
    summary="Plan multi-objective traverse routes",
    description="Computes optimized traverse routes across risk, balanced, and science profiles.",
)
async def plan_routes(request: RoutePlanRequest) -> RoutePlanResponse:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
