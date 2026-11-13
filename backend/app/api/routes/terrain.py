"""Terrain sampling endpoints stub implementing docs/API_CONTRACTS.md §4.9-§4.10 (P0, WP-08)."""

from fastapi import APIRouter, Query

from app.core.errors import AppException
from app.models import PointInspection, ProfileRequest, ProfileResponse

router = APIRouter(prefix="/terrain", tags=["Terrain"])


@router.get(
    "/point",
    response_model=PointInspection,
    summary="Inspect terrain at coordinate",
    description="Returns multi-layer sampled values and contextual safety data at a point.",
)
async def inspect_point(
    region_id: str = Query(..., description="Region identifier"),
    lat: float = Query(
        ..., description="Latitude in planetocentric degrees [-90, 90]", ge=-90.0, le=90.0
    ),
    lon: float = Query(..., description="Longitude in east-positive degrees [0, 360)"),
) -> PointInspection:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.post(
    "/profile",
    response_model=ProfileResponse,
    summary="Compute cross-section profile",
    description="Samples elevation and slope along an ordered polyline path.",
)
async def compute_profile(request: ProfileRequest) -> ProfileResponse:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
