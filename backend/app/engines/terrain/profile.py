"""Elevation profile extraction along polyline paths.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.5:
- Samples spaced along polyline at sample_spacing_m (default: analysis cell size),
  using great-circle interpolation between vertices.
- Reports cumulative horizontal distance, elevation (bilinear sampling, section 4.1),
  and slope (nearest analysis cell, section 4.1).
"""

import math
from typing import Any, List, Tuple

import numpy as np

from app.engines.terrain.sampling import sample_bilinear, sample_nearest
from app.models.geometry import GeoPoint
from app.models.terrain import ProfilePoint

# Mars IAU 2000 sphere radius in metres (docs/SCIENCE_AND_SAFETY_SPEC.md section 2.1)
MARS_SPHERE_RADIUS_M: float = 3_396_190.0


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    radius: float = MARS_SPHERE_RADIUS_M,
) -> float:
    """Compute great-circle distance in metres on a sphere (spec section 2.4)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lon_deg = (lon2 - lon1 + 180.0) % 360.0 - 180.0
    delta_lambda = math.radians(delta_lon_deg)

    h = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(h)))


def interpolate_great_circle_points(
    p1: GeoPoint,
    p2: GeoPoint,
    sample_spacing_m: float,
    radius_m: float = MARS_SPHERE_RADIUS_M,
) -> List[Tuple[GeoPoint, float]]:
    """Generate intermediate points along great-circle arc between two coordinates.

    Uses spherical interpolation (slerp) on Mars sphere (spec section 2.4, section 4.5).

    Args:
        p1: Start coordinate.
        p2: End coordinate.
        sample_spacing_m: Nominal distance between samples in metres.
        radius_m: Sphere radius in metres.

    Returns:
        List of tuples (GeoPoint, segment_distance_from_p1).
    """
    lat1_rad = math.radians(p1.lat)
    lon1_rad = math.radians(p1.lon)
    lat2_rad = math.radians(p2.lat)
    lon2_rad = math.radians(p2.lon)

    # Segment angular distance delta = distance / R
    seg_dist_m = haversine_distance_m(p1.lat, p1.lon, p2.lat, p2.lon, radius=radius_m)
    if seg_dist_m < 1e-6:
        return [(p1, 0.0)]

    delta = seg_dist_m / radius_m
    sin_delta = math.sin(delta)

    # Number of steps along segment
    n_steps = max(1, int(math.ceil(seg_dist_m / sample_spacing_m)))

    points: List[Tuple[GeoPoint, float]] = []
    for step in range(n_steps):
        frac = step / float(n_steps)
        d_from_p1 = frac * seg_dist_m

        if sin_delta < 1e-12:
            points.append((p1, d_from_p1))
            continue

        a = math.sin((1.0 - frac) * delta) / sin_delta
        b = math.sin(frac * delta) / sin_delta

        x = a * math.cos(lat1_rad) * math.cos(lon1_rad) + b * math.cos(lat2_rad) * math.cos(
            lon2_rad
        )
        y = a * math.cos(lat1_rad) * math.sin(lon1_rad) + b * math.cos(lat2_rad) * math.sin(
            lon2_rad
        )
        z = a * math.sin(lat1_rad) + b * math.sin(lat2_rad)

        lat_interp = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
        lon_interp = math.degrees(math.atan2(y, x)) % 360.0

        points.append((GeoPoint(lat=lat_interp, lon=lon_interp), d_from_p1))

    return points


def compute_elevation_profile(
    points: List[GeoPoint],
    elevation_grid: np.ndarray,
    slope_grid: np.ndarray,
    transform: Any,
    crs: Any,
    sample_spacing_m: float = 1.0,
    radius_m: float = MARS_SPHERE_RADIUS_M,
) -> List[ProfilePoint]:
    """Extract elevation and slope samples along a polyline.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.5:
    - Samples are spaced along polyline at sample_spacing_m using great-circle interpolation.
    - Each sample reports cumulative horizontal distance, elevation (bilinear), slope (nearest).

    Args:
        points: List of 2 or more vertices.
        elevation_grid: 2D float32 array of elevations.
        slope_grid: 2D float32 array of slopes.
        transform: Rasterio Affine transform for grid coordinates.
        crs: CRS of the grid.
        sample_spacing_m: Distance between samples along polyline in metres.
        radius_m: Sphere radius in metres.

    Returns:
        List of ProfilePoint objects.
    """
    if len(points) < 2:
        raise ValueError("Profile requires at least 2 points.")

    import pyproj

    # Build transformer from geographic (lat, lon) to grid projected CRS
    geo_crs = pyproj.CRS.from_proj4(f"+proj=longlat +R={radius_m} +no_defs")
    proj_crs = pyproj.CRS.from_user_input(crs)
    transformer = pyproj.Transformer.from_crs(geo_crs, proj_crs, always_xy=True)

    # Invert affine transform to get row, col from projected x, y
    inv_transform = ~transform

    profile_samples: List[ProfilePoint] = []
    cumulative_dist_m = 0.0

    for i in range(len(points) - 1):
        p_start = points[i]
        p_end = points[i + 1]

        seg_points = interpolate_great_circle_points(
            p_start, p_end, sample_spacing_m=sample_spacing_m, radius_m=radius_m
        )
        seg_len_m = haversine_distance_m(
            p_start.lat, p_start.lon, p_end.lat, p_end.lon, radius=radius_m
        )

        for pt, d_seg in seg_points:
            total_dist = cumulative_dist_m + d_seg

            # Convert point to projected grid (x, y)
            proj_x, proj_y = transformer.transform(pt.lon, pt.lat)
            # Convert to raster continuous col, row
            col_f, row_f = inv_transform * (proj_x, proj_y)

            # Sample elevation via bilinear interpolation (section 4.1)
            elev_val = sample_bilinear(elevation_grid, row_f, col_f)
            # Sample slope via nearest neighbour (section 4.1)
            slope_val = sample_nearest(slope_grid, row_f, col_f)

            profile_samples.append(
                ProfilePoint(
                    distance_m=round(total_dist, 3),
                    point=pt,
                    elevation_m=None if np.isnan(elev_val) else round(float(elev_val), 3),
                    slope_deg=None if np.isnan(slope_val) else round(float(slope_val), 3),
                )
            )

        cumulative_dist_m += seg_len_m

    # Include final point
    p_last = points[-1]
    proj_x, proj_y = transformer.transform(p_last.lon, p_last.lat)
    col_f, row_f = inv_transform * (proj_x, proj_y)
    elev_val = sample_bilinear(elevation_grid, row_f, col_f)
    slope_val = sample_nearest(slope_grid, row_f, col_f)

    profile_samples.append(
        ProfilePoint(
            distance_m=round(cumulative_dist_m, 3),
            point=p_last,
            elevation_m=None if np.isnan(elev_val) else round(float(elev_val), 3),
            slope_deg=None if np.isnan(slope_val) else round(float(slope_val), 3),
        )
    )

    return profile_samples
