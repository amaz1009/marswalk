"""Region endpoints stub implementing docs/API_CONTRACTS.md §4.2-§4.3 (P0, WP-08)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import RegionDetail, RegionSummary

router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get(
    "",
    response_model=list[RegionSummary],
    summary="List exploration regions",
    description="Returns high-level summaries of all supported Mars exploration regions.",
)
async def list_regions() -> list[RegionSummary]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.get(
    "/{region_id}",
    response_model=RegionDetail,
    summary="Get region details",
    description="Returns CRS, analysis configuration, layers, and science targets for a region.",
)
async def get_region(region_id: str) -> RegionDetail:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
