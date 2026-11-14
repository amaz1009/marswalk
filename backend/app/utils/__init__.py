"""Coordinate and geodesy utilities for AresNav.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.
"""

from app.utils.coordinates import (
    MARS_ELLIPSOID_WKT,
    MARS_EQUATORIAL_RADIUS_M,
    MARS_INVERSE_FLATTENING,
    MARS_POLAR_RADIUS_M,
    MARS_SPHERE_RADIUS_M,
    MARS_SPHERE_WKT,
    MarsCoordinateTransformer,
    build_mars_equirectangular_wkt,
    east_to_west_longitude,
    normalize_longitude,
    planetocentric_to_planetographic,
    planetographic_to_planetocentric,
    validate_coordinates,
    validate_latitude,
    validate_longitude,
    west_to_east_longitude,
)
from app.utils.geodesy import (
    haversine_distance,
    initial_bearing,
    interpolate_great_circle,
    wrap_longitude_difference,
)

__all__ = [
    "MARS_SPHERE_RADIUS_M",
    "MARS_EQUATORIAL_RADIUS_M",
    "MARS_POLAR_RADIUS_M",
    "MARS_INVERSE_FLATTENING",
    "MARS_SPHERE_WKT",
    "MARS_ELLIPSOID_WKT",
    "validate_latitude",
    "validate_longitude",
    "validate_coordinates",
    "normalize_longitude",
    "west_to_east_longitude",
    "east_to_west_longitude",
    "planetographic_to_planetocentric",
    "planetocentric_to_planetographic",
    "build_mars_equirectangular_wkt",
    "MarsCoordinateTransformer",
    "haversine_distance",
    "initial_bearing",
    "interpolate_great_circle",
    "wrap_longitude_difference",
]
