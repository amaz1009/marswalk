"""Layer visualization endpoints implementing docs/API_CONTRACTS.md section 4.6-4.8 (P0, WP-08)."""

from typing import Any

from fastapi import APIRouter, Query, Response

from app.models import LayerInfo
from app.services import layer_service

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
    return layer_service.list_layers(region_id=region_id)


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
    png_bytes = layer_service.render_layer_png(layer_id=layer_id, region_id=region_id)
    return Response(content=png_bytes, media_type="image/png")


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
    return layer_service.get_layer_features(layer_id=layer_id, region_id=region_id)
