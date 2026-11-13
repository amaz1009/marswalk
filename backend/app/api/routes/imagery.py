"""Surface imagery endpoints stub implementing docs/API_CONTRACTS.md §4.15-§4.16 (P1, WP-15)."""

from fastapi import APIRouter, Query, Response

from app.core.errors import AppException
from app.models import SurfaceImage

router = APIRouter(prefix="/imagery", tags=["Imagery"])


@router.get(
    "/surface",
    response_model=list[SurfaceImage],
    summary="Query surface imagery",
    description="Returns ground-level rover images proximate to a coordinate, sorted by distance.",
)
async def query_surface_imagery(
    region_id: str = Query(..., description="Region identifier"),
    lat: float = Query(
        ..., description="Latitude in planetocentric degrees [-90, 90]", ge=-90.0, le=90.0
    ),
    lon: float = Query(..., description="Longitude in east-positive degrees [0, 360)"),
    radius_m: float = Query(default=1000.0, description="Search radius in metres", gt=0.0),
) -> list[SurfaceImage]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.get(
    "/surface/{image_id}/file",
    summary="Download surface image file",
    description="Returns JPEG/PNG binary image bytes for a surface image.",
    responses={
        200: {
            "content": {"image/jpeg": {}, "image/png": {}},
            "description": "Binary image file bytes",
        }
    },
)
async def get_surface_image_file(image_id: str) -> Response:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
