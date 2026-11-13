"""Layer visualization endpoints stub implementing docs/API_CONTRACTS.md §4.6-§4.8 (P0, WP-08)."""

from typing import Any

from fastapi import APIRouter, Query, Response

from app.core.errors import AppException
from app.models import LayerInfo

router = APIRouter(prefix="/layers", tags=["Layers"])


@router.get(
    "",
    response_model=list[LayerInfo],
    summary="List map layers",
    description="Returns display manifests for map layers configured for a region.",
)
async def list_layers(
    region_id: str | None = Query(default=None, description="Region identifier"),
) -> list[LayerInfo]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.get(
    "/{layer_id}/image",
    summary="Get raster layer image",
    description="Returns PNG image overlay covering the layer bounding box.",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image overlay covering LayerInfo.bounds",
        }
    },
)
async def get_layer_image(
    layer_id: str,
    region_id: str | None = Query(default=None, description="Region identifier"),
) -> Response:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.get(
    "/{layer_id}/features",
    summary="Get vector layer features",
    description="Returns GeoJSON FeatureCollection clipped to the region.",
    responses={
        200: {
            "content": {"application/geo+json": {}},
            "description": "GeoJSON FeatureCollection",
        }
    },
)
async def get_layer_features(
    layer_id: str,
    region_id: str | None = Query(default=None, description="Region identifier"),
) -> dict[str, Any]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
