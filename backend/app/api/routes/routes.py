"""Route planning endpoints implementing docs/API_CONTRACTS.md §4.12 (P0, WP-11)."""

from fastapi import APIRouter

from app.models import RoutePlanRequest, RoutePlanResponse
from app.services.route_service import get_route_service

router = APIRouter(prefix="/routes", tags=["Routes"])


@router.post(
    "/plan",
    response_model=RoutePlanResponse,
    summary="Plan multi-objective traverse routes",
    description="Computes optimized traverse routes across risk, balanced, and science profiles.",
)
def plan_routes(request: RoutePlanRequest) -> RoutePlanResponse:
    """Execute multi-objective traverse route optimization."""
    return get_route_service().plan_traverse(request)
