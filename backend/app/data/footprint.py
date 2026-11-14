"""Footprint extraction and named feature spatial containment evaluation.

Implements requirements:
- Compute and record HiRISE DTM footprint from real raster bounds
- Test whether named areas fall inside the footprint
- Never hard-code boxwork coordinates: where the data cannot show it,
  record UNKNOWN
"""

from typing import Any

from app.models.geometry import GeoBounds


def compute_raster_footprint(
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    is_projected: bool = False,
    transform_to_latlon: Any = None,
) -> GeoBounds:
    """Compute geographic bounds (planetocentric lon/lat) from raster extent.

    If raster is already in geographic coordinates (lon, lat), assigns directly.
    If projected in metres, uses transformer to obtain geographic corners.
    """
    if not is_projected or transform_to_latlon is None:
        return GeoBounds(
            lat_min=min_y,
            lat_max=max_y,
            lon_min=min_x,
            lon_max=max_x,
        )

    # Transform 4 corners
    lons, lats = transform_to_latlon([min_x, max_x, min_x, max_x], [min_y, min_y, max_y, max_y])
    return GeoBounds(
        lat_min=float(min(lats)),
        lat_max=float(max(lats)),
        lon_min=float(min(lons)),
        lon_max=float(max(lons)),
    )


def point_in_footprint(lat: float, lon: float, footprint: GeoBounds) -> bool:
    """Return True if (lat, lon) is inside the footprint bounding box."""
    return (
        footprint.lat_min <= lat <= footprint.lat_max
        and footprint.lon_min <= lon <= footprint.lon_max
    )


def evaluate_named_area_in_footprint(
    area_name: str,
    verified_coordinates: tuple[float, float] | None,
    footprint: GeoBounds | None,
) -> dict[str, Any]:
    """Evaluate whether a named feature lies inside the computed raster footprint.

    Per Scientific Integrity rules:
    - Never hard-code boxwork coordinates.
    - If coordinates are not verified from ingested data, record status 'UNKNOWN'.
    - If raster footprint is not yet computed, record status 'UNKNOWN'.
    """
    if footprint is None:
        return {
            "area_name": area_name,
            "status": "UNKNOWN",
            "reason": "Footprint cannot be determined: primary DTM raster is not yet processed.",
            "is_inside": None,
        }

    if verified_coordinates is None:
        return {
            "area_name": area_name,
            "status": "UNKNOWN",
            "reason": (
                "Boxwork feature coordinates are not verified from a cited data source; "
                "containment cannot be evaluated without verified feature coordinates. "
                "Per Scientific Integrity rules, feature coordinates are never hard-coded."
            ),
            "is_inside": None,
        }

    lat, lon = verified_coordinates
    inside = point_in_footprint(lat, lon, footprint)
    inside_str = "falls inside" if inside else "falls outside"
    return {
        "area_name": area_name,
        "status": "DETERMINED",
        "reason": f"Point ({lat}, {lon}) {inside_str} DTM footprint.",
        "is_inside": inside,
    }
