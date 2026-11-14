"""Region endpoints implementing docs/API_CONTRACTS.md section 4.2-4.3 (P0, WP-08)."""

from fastapi import APIRouter

from app.models import RegionDetail, RegionSummary
from app.services import region_service

router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get(
    "",
    response_model=list[RegionSummary],
    summary="List exploration regions",
    description="Returns high-level summaries of all supported Mars exploration regions.",
)
async def list_regions() -> list[RegionSummary]:
    return region_service.list_regions()


@router.get(
    "/{region_id}",
    response_model=RegionDetail,
    summary="Get region details",
    description="Returns CRS, analysis configuration, layers, and science targets for a region.",
)
async def get_region(region_id: str) -> RegionDetail:
    return region_service.get_region_detail(region_id)
