"""Terrain sampling routines.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.1:
- Continuous rasters: Bilinear interpolation. If any of the 4 contributing
  cells is NaN, the result is NaN.
- Categorical rasters: Nearest neighbour.
"""

from typing import Union

import numpy as np


def sample_bilinear(
    data: np.ndarray,
    row: Union[float, np.ndarray],
    col: Union[float, np.ndarray],
) -> Union[float, np.ndarray]:
    """Sample continuous raster data using bilinear interpolation.

    Per docs/SCIENCE_AND_SAFETY_SPEC.md section 4.1:
    If any of the 4 contributing cells is NaN or out of bounds, the result is NaN.

    Args:
        data: 2D numpy array of elevations or continuous values.
        row: Continuous row index (float or array of floats).
        col: Continuous col index (float or array of floats).

    Returns:
        Interpolated value(s) with NaN for invalid or out-of-bounds positions.
    """
    is_scalar = np.isscalar(row) and np.isscalar(col)
    r_arr = np.asarray(row, dtype=np.float64)
    c_arr = np.asarray(col, dtype=np.float64)

    height, width = data.shape

    # Identify base indices
    r0 = np.floor(r_arr).astype(np.int64)
    c0 = np.floor(c_arr).astype(np.int64)
    r1 = r0 + 1
    c1 = c0 + 1

    dr = r_arr - r0
    dc = c_arr - c0

    # Bounds check for the 4 required cells: [0, height-1] and [0, width-1]
    valid_mask = (r0 >= 0) & (r1 < height) & (c0 >= 0) & (c1 < width)

    # Allocate output filled with NaN
    out = np.full(r_arr.shape, np.nan, dtype=np.float64)

    if not np.any(valid_mask):
        return float(out) if is_scalar else out

    # Extract valid coordinates
    v_r0 = r0[valid_mask]
    v_c0 = c0[valid_mask]
    v_r1 = r1[valid_mask]
    v_c1 = c1[valid_mask]
    v_dr = dr[valid_mask]
    v_dc = dc[valid_mask]

    # Gather 4 cell values
    v00 = data[v_r0, v_c0]
    v01 = data[v_r0, v_c1]
    v10 = data[v_r1, v_c0]
    v11 = data[v_r1, v_c1]

    # NaN propagation rule (spec section 4.1):
    # If any of the 4 contributing cells is NaN, the result is NaN.
    cells_valid = ~np.isnan(v00) & ~np.isnan(v01) & ~np.isnan(v10) & ~np.isnan(v11)

    interp_vals = (
        (1.0 - v_dr) * (1.0 - v_dc) * v00
        + (1.0 - v_dr) * v_dc * v01
        + v_dr * (1.0 - v_dc) * v10
        + v_dr * v_dc * v11
    )

    # Where any cell is NaN, result must remain NaN
    interp_vals = np.where(cells_valid, interp_vals, np.nan)

    out[valid_mask] = interp_vals
    return float(out) if is_scalar else out


def sample_nearest(
    data: np.ndarray,
    row: Union[float, np.ndarray],
    col: Union[float, np.ndarray],
) -> Union[float, np.ndarray]:
    """Sample categorical/discrete raster data using nearest neighbour interpolation.

    Per docs/SCIENCE_AND_SAFETY_SPEC.md section 4.1.

    Args:
        data: 2D numpy array.
        row: Continuous row index (float or array of floats).
        col: Continuous col index (float or array of floats).

    Returns:
        Nearest cell value(s) with NaN for out-of-bounds positions.
    """
    is_scalar = np.isscalar(row) and np.isscalar(col)
    r_arr = np.asarray(row, dtype=np.float64)
    c_arr = np.asarray(col, dtype=np.float64)

    height, width = data.shape

    r_nearest = np.rint(r_arr).astype(np.int64)
    c_nearest = np.rint(c_arr).astype(np.int64)

    valid_mask = (r_nearest >= 0) & (r_nearest < height) & (c_nearest >= 0) & (c_nearest < width)

    out = np.full(r_arr.shape, np.nan, dtype=np.float64)
    if np.any(valid_mask):
        out[valid_mask] = data[r_nearest[valid_mask], c_nearest[valid_mask]]

    return float(out) if is_scalar else out
