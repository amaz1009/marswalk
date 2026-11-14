"""Hillshade computation for map display.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.6:
- Standard illumination from azimuth 315 deg, altitude 45 deg on analysis grid.
- Visual aid with data class DERIVED; never used in safety calculations.
"""

import math

import numpy as np


def compute_hillshade(
    elevation: np.ndarray,
    dx: float,
    dy: float,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
    chunk_size: int = 2000,
) -> np.ndarray:
    """Compute shaded relief (hillshade) image for display.

    Per docs/SCIENCE_AND_SAFETY_SPEC.md section 4.6:
    Illumination from azimuth 315 deg, altitude 45 deg.
    Uses Horn (1981) partial derivatives for slope and aspect:
    - zenith_rad = radians(90 - altitude_deg)
    - azimuth_math = radians(360 - azimuth_deg + 90) % (2*pi)
    - aspect = atan2(dz/dy, -dz/dx)
    - shaded = 255 * (cos(zenith)*cos(slope) + sin(zenith)*sin(slope)*cos(azimuth_math - aspect))

    Args:
        elevation: 2D float32 array of elevations.
        dx: Cell spacing in x direction (metres).
        dy: Cell spacing in y direction (metres).
        azimuth_deg: Sun azimuth angle in degrees (default 315.0).
        altitude_deg: Sun altitude angle above horizon in degrees (default 45.0).
        chunk_size: Processing chunk size in rows.

    Returns:
        2D uint8 numpy array of values [0, 255], with 0 for NaN/nodata cells.
    """
    height, width = elevation.shape
    hillshade = np.zeros((height, width), dtype=np.uint8)

    if height < 3 or width < 3:
        return hillshade

    # Solar angles
    zenith_rad = math.radians(90.0 - altitude_deg)
    # Math azimuth measured counter-clockwise from east
    azimuth_math_rad = math.radians((360.0 - azimuth_deg + 90.0) % 360.0)

    cos_zenith = math.cos(zenith_rad)
    sin_zenith = math.sin(zenith_rad)

    denom_x = 8.0 * dx
    denom_y = 8.0 * dy

    for r_start in range(1, height - 1, chunk_size):
        r_end = min(r_start + chunk_size, height - 1)

        z_block = elevation[r_start - 1 : r_end + 1, :]

        a = z_block[:-2, :-2]
        b = z_block[:-2, 1:-1]
        c = z_block[:-2, 2:]
        d = z_block[1:-1, :-2]
        f = z_block[1:-1, 2:]
        g = z_block[2:, :-2]
        h = z_block[2:, 1:-1]
        i = z_block[2:, 2:]

        valid_mask = (
            ~np.isnan(a)
            & ~np.isnan(b)
            & ~np.isnan(c)
            & ~np.isnan(d)
            & ~np.isnan(f)
            & ~np.isnan(g)
            & ~np.isnan(h)
            & ~np.isnan(i)
        )

        dz_dx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / denom_x
        dz_dy = ((g + 2.0 * h + i) - (a + 2.0 * b + c)) / denom_y

        slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
        aspect_rad = np.arctan2(dz_dy, -dz_dx)

        illumination = cos_zenith * np.cos(slope_rad) + sin_zenith * np.sin(slope_rad) * np.cos(
            azimuth_math_rad - aspect_rad
        )

        # Rescale valid illumination to [1, 255]; 0 is strictly reserved for NODATA
        illum_valid = np.nan_to_num(illumination, nan=0.0)
        shaded = np.clip(1.0 + 254.0 * np.maximum(0.0, illum_valid), 1, 255).astype(np.uint8)
        shaded = np.where(valid_mask, shaded, 0)

        hillshade[r_start:r_end, 1:-1] = shaded

    return hillshade
