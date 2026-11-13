"""Geodesy, distance, bearing, and great-circle interpolation for Mars.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.4.
All distances use the IAU 2000 Mars sphere (R = 3,396,190 m).
Uses Mars datums only; no terrestrial coordinate systems.
"""

import math

from app.utils.coordinates import (
    MARS_SPHERE_RADIUS_M,
    normalize_longitude,
    validate_latitude,
    validate_longitude,
)


def wrap_longitude_difference(dlon_deg: float) -> float:
    """Wrap longitude difference into (-180, 180] degrees.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.4.
    """
    if math.isnan(dlon_deg) or math.isinf(dlon_deg):
        raise ValueError(f"Longitude difference must be finite, got {dlon_deg}")
    wrapped = (dlon_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0:
        wrapped = 180.0
    return wrapped


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    radius: float = MARS_SPHERE_RADIUS_M,
) -> float:
    """Compute great-circle distance between two points on the Mars sphere in metres.

    Formula (docs/SCIENCE_AND_SAFETY_SPEC.md §2.4):
    Δφ = φ2 − φ1, Δλ = λ2 − λ1 (radians)
    h = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
    d = 2 · R · asin( min(1, sqrt(h)) )
    """
    validate_latitude(lat1)
    validate_latitude(lat2)
    validate_longitude(lon1)
    validate_longitude(lon2)

    if math.isnan(radius) or math.isinf(radius) or radius <= 0.0:
        raise ValueError(f"Radius must be positive and finite, got {radius}")

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlon_deg = wrap_longitude_difference(lon2 - lon1)
    dlambda = math.radians(dlon_deg)

    h = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    # Clamp to [0, 1] for numerical stability
    h = max(0.0, min(1.0, h))
    return 2.0 * radius * math.asin(math.sqrt(h))


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute initial course/bearing from point 1 to point 2 in degrees clockwise from north.

    Returns bearing in [0, 360).
    Formula (docs/SCIENCE_AND_SAFETY_SPEC.md §2.4):
    θ = atan2( sin Δλ · cos φ2, cos φ1 · sin φ2 − sin φ1 · cos φ2 · cos Δλ )
    """
    validate_latitude(lat1)
    validate_latitude(lat2)
    validate_longitude(lon1)
    validate_longitude(lon2)

    # Identical points return 0.0 convention
    if lat1 == lat2 and wrap_longitude_difference(lon2 - lon1) == 0.0:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon_deg = wrap_longitude_difference(lon2 - lon1)
    dlambda = math.radians(dlon_deg)

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)

    theta_deg = math.degrees(math.atan2(y, x))
    bearing = (theta_deg + 360.0) % 360.0
    if bearing == 0.0:
        bearing = 0.0
    return bearing


def interpolate_great_circle(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    fraction: float,
) -> tuple[float, float]:
    """Interpolate intermediate coordinate along the great circle arc using Slerp.

    Args:
        lat1: Start latitude in degrees.
        lon1: Start longitude in degrees.
        lat2: End latitude in degrees.
        lon2: End longitude in degrees.
        fraction: Path fraction in [0.0, 1.0], where 0.0 is start and 1.0 is end.

    Returns:
        tuple[float, float]: (lat, lon) in planetocentric degrees and east-positive [0, 360).
    """
    validate_latitude(lat1)
    validate_latitude(lat2)
    validate_longitude(lon1)
    validate_longitude(lon2)

    if math.isnan(fraction) or math.isinf(fraction) or fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"Interpolation fraction must be in [0.0, 1.0], got {fraction}")

    norm_lon1 = normalize_longitude(lon1)
    norm_lon2 = normalize_longitude(lon2)

    if fraction == 0.0:
        return lat1, norm_lon1
    if fraction == 1.0:
        return lat2, norm_lon2

    phi1 = math.radians(lat1)
    lam1 = math.radians(norm_lon1)
    phi2 = math.radians(lat2)
    lam2 = math.radians(norm_lon2)

    # Unit Cartesian vectors
    v1 = (math.cos(phi1) * math.cos(lam1), math.cos(phi1) * math.sin(lam1), math.sin(phi1))
    v2 = (math.cos(phi2) * math.cos(lam2), math.cos(phi2) * math.sin(lam2), math.sin(phi2))

    # Dot product = cos(angular distance)
    dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    dot = max(-1.0, min(1.0, dot))

    # Coincident points
    if math.isclose(dot, 1.0, rel_tol=1e-12, abs_tol=1e-12):
        return lat1, norm_lon1

    # Antipodal points: infinite great circles exist; interpolate along prime meridian convention
    if math.isclose(dot, -1.0, rel_tol=1e-12, abs_tol=1e-12):
        mid_lat = lat1 + fraction * (lat2 - lat1)
        return mid_lat, norm_lon1

    omega = math.acos(dot)
    sin_omega = math.sin(omega)

    a = math.sin((1.0 - fraction) * omega) / sin_omega
    b = math.sin(fraction * omega) / sin_omega

    vx = a * v1[0] + b * v2[0]
    vy = a * v1[1] + b * v2[1]
    vz = a * v1[2] + b * v2[2]

    # Convert back to spherical coordinates
    r = math.sqrt(vx * vx + vy * vy + vz * vz)
    lat_interp = math.degrees(math.asin(vz / r))
    lon_interp = normalize_longitude(math.degrees(math.atan2(vy, vx)))

    return lat_interp, lon_interp
