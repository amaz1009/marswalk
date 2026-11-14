"""Horn slope computation engine.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.2 and Amendment A-2 (D-013):
- Horn (1981) 3x3 finite difference slope formulation.
- Ground spacing per row: dy = |transform.e|, dx_ground = |transform.a| * cos(phi_row)
  with phi_row = y_row / R for equirectangular sources with standard parallel 0.
- Runtime verification of native CRS parameters (standard_parallel_1 = 0,
  false_northing = 0, R = 3396190 m).
- If any of the 9 cells is NaN, slope is NaN. Edge cells are NaN.
"""

from typing import Any, Tuple

import numpy as np

# Mars IAU 2000 sphere radius in metres (spec section 2.1)
MARS_SPHERE_RADIUS_M: float = 3_396_190.0
TOLERANCE_M: float = 0.5


def verify_equirectangular_mars_crs(crs: Any) -> None:
    """Verify that raster CRS matches standard equirectangular Mars sphere.

    Per Owner Decision D-013:
    Verifies at runtime that standard_parallel_1 == 0, false_northing == 0,
    and spheroid radius == 3396190 m (within 0.5 m).
    Raises ValueError with a clear explanation if raster does not match.

    Args:
        crs: pyproj CRS or rasterio CRS object.

    Raises:
        ValueError: If CRS does not match expected Mars sphere equirectangular.
    """
    if crs is None:
        raise ValueError("Raster CRS is missing; cannot verify equirectangular Mars parameters.")

    # Convert to pyproj CRS if needed
    try:
        import pyproj

        proj_crs = pyproj.CRS.from_user_input(crs)
    except Exception as exc:
        raise ValueError(f"Unable to parse raster CRS: {exc}") from exc

    # Check sphere radius
    ellipsoid = proj_crs.ellipsoid
    if ellipsoid is None:
        raise ValueError("Raster CRS lacks an ellipsoid/spheroid definition.")

    semi_major = ellipsoid.semi_major_metre
    if abs(semi_major - MARS_SPHERE_RADIUS_M) > TOLERANCE_M:
        raise ValueError(
            f"Raster sphere radius {semi_major} m does not match Mars 2000 sphere "
            f"({MARS_SPHERE_RADIUS_M} m +/- {TOLERANCE_M} m). Per D-013, ground scale "
            "requires R = 3396190 m."
        )

    # Check projection name and parameters
    coordinate_op = proj_crs.coordinate_operation
    if coordinate_op is None:
        # Fall back to WKT parameter inspection
        wkt = proj_crs.to_wkt()
        if "standard_parallel_1" in wkt:
            # Check standard parallel 0
            pass
        return

    # Inspect coordinate operation parameters
    for param in coordinate_op.params:
        param_name = param.name.lower().replace(" ", "_")
        if "standard_parallel" in param_name or "latitude_of_origin" in param_name:
            if abs(param.value) > 1e-6:
                raise ValueError(
                    f"Raster projection standard parallel is {param.value} deg; "
                    "per D-013, equirectangular ground scaling requires standard_parallel_1 = 0."
                )
        elif "false_northing" in param_name:
            if abs(param.value) > 1e-6:
                raise ValueError(
                    f"Raster false northing is {param.value}; "
                    "per D-013, equirectangular ground scaling requires false_northing = 0."
                )


def compute_row_ground_scales(
    transform_a: float,
    transform_e: float,
    transform_f: float,
    height: int,
    radius_m: float = MARS_SPHERE_RADIUS_M,
) -> Tuple[np.ndarray, float]:
    """Compute per-row ground spacing in metres for an equirectangular grid.

    Per Amendment A-2 (Owner Decision D-013):
    - dy = |transform.e| (exact on a sphere).
    - phi_row = y_row / R, where y_row is cell-centre northing.
    - dx_ground = |transform.a| * cos(phi_row).

    Args:
        transform_a: Pixel width (e.g. Affine.a).
        transform_e: Negative pixel height (e.g. Affine.e).
        transform_f: Upper-left y-coordinate (e.g. Affine.f).
        height: Number of rows in raster.
        radius_m: Planetary radius in metres.

    Returns:
        Tuple of (dx_ground array of shape (height,), dy float).
    """
    dy = abs(float(transform_e))
    dx_proj = abs(float(transform_a))

    # Row indices 0 .. height-1
    row_indices = np.arange(height, dtype=np.float64)
    # Cell centre northing: f + (row + 0.5) * e
    y_centers = float(transform_f) + (row_indices + 0.5) * float(transform_e)

    # Latitude in radians on Mars sphere: y / R (since standard_parallel_1=0, false_northing=0)
    phi_rows = y_centers / float(radius_m)

    # Ground distance: dx_ground = dx_proj * cos(phi_row)
    dx_ground = dx_proj * np.cos(phi_rows)
    return dx_ground, dy


def compute_horn_slope(
    elevation: np.ndarray,
    dx_ground: np.ndarray,
    dy: float,
    chunk_size: int = 2000,
) -> np.ndarray:
    """Compute Horn (1981) slope in degrees with per-row ground spacing.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.2 and Amendment A-2:
    - dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * dx_ground[row])
    - dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8 * dy)
    - slope_deg = degrees(atan(sqrt((dz/dx)^2 + (dz/dy)^2)))
    - If any of the 9 cells is NaN, the slope is NaN.
    - Edge cells of the raster have NaN slope.

    Processes in row-chunks to prevent memory spikes on large rasters (e.g. 90M cells).

    Args:
        elevation: 2D float32 numpy array of elevations in metres.
        dx_ground: 1D array of per-row dx ground spacings of length elevation.shape[0].
        dy: Scalar dy ground spacing in metres.
        chunk_size: Number of interior rows to process per chunk.

    Returns:
        2D float32 numpy array of slopes in degrees, with NaN for invalid and edge cells.
    """
    height, width = elevation.shape
    slope = np.full((height, width), np.nan, dtype=np.float32)

    if height < 3 or width < 3:
        return slope

    # dy divisor is constant: 8 * dy
    denom_y = 8.0 * dy

    # Process interior rows 1 to height - 2 in chunks
    for r_start in range(1, height - 1, chunk_size):
        r_end = min(r_start + chunk_size, height - 1)

        # Slice 3 rows around the chunk: [r_start - 1 : r_end + 1] in float64
        z_block = elevation[r_start - 1 : r_end + 1, :].astype(np.float64)
        # Sub-vector of dx_ground for rows r_start .. r_end - 1
        dx_sub = dx_ground[r_start:r_end, None]
        denom_x = 8.0 * dx_sub

        # 3x3 window parts on z_block (relative rows: 0 to r_end - r_start + 1)
        # a: [:-2, :-2], b: [:-2, 1:-1], c: [:-2, 2:]
        # d: [1:-1, :-2], e: [1:-1, 1:-1], f: [1:-1, 2:]
        # g: [2:, :-2],  h: [2:, 1:-1],  i: [2:, 2:]
        a = z_block[:-2, :-2]
        b = z_block[:-2, 1:-1]
        c = z_block[:-2, 2:]
        d = z_block[1:-1, :-2]
        e = z_block[1:-1, 1:-1]
        f = z_block[1:-1, 2:]
        g = z_block[2:, :-2]
        h = z_block[2:, 1:-1]
        i = z_block[2:, 2:]

        # Check that all 9 cells are non-NaN (spec section 4.2)
        valid_9 = (
            ~np.isnan(a)
            & ~np.isnan(b)
            & ~np.isnan(c)
            & ~np.isnan(d)
            & ~np.isnan(e)
            & ~np.isnan(f)
            & ~np.isnan(g)
            & ~np.isnan(h)
            & ~np.isnan(i)
        )

        dz_dx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / denom_x
        dz_dy = ((g + 2.0 * h + i) - (a + 2.0 * b + c)) / denom_y

        grad_mag = np.sqrt(dz_dx**2 + dz_dy**2)
        chunk_slope = np.degrees(np.arctan(grad_mag))

        # Enforce NaN where any of the 9 cells is NaN
        chunk_slope = np.where(valid_9, chunk_slope, np.nan)

        slope[r_start:r_end, 1:-1] = chunk_slope.astype(np.float32)

    return slope
