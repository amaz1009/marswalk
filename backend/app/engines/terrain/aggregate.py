"""Conservative aggregation from native DTM resolution to analysis grid.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.4:
- Elevation: Mean of valid native cells.
- Slope: Maximum native slope in the cell (mean also stored).
- Roughness: Maximum native roughness in the cell.
- Validity rule: Cell is valid only if >= 90 % of its native cells are valid.
  Avoids routing over gaps.
"""

from typing import Dict

import numpy as np


def aggregate_to_analysis_grid(
    native_elevation: np.ndarray,
    native_slope: np.ndarray,
    native_roughness: np.ndarray,
    block_size: int = 1,
    min_valid_fraction: float = 0.90,
) -> Dict[str, np.ndarray]:
    """Conservatively aggregate native rasters to analysis grid resolution.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.4:
    - When analysis cell size is larger than native post spacing (block_size > 1):
        - Elevation: Mean of valid native cells.
        - Slope: Maximum native slope (mean slope also computed and returned).
        - Roughness: Maximum native roughness.
        - Validity: Cell valid only if fraction of valid native cells >= 90%.
          Otherwise all aggregated outputs are NaN.
    - When block_size == 1:
        - 1:1 mapping directly; cells with valid data are valid (100% >= 90%),
          NaN cells are invalid.

    Args:
        native_elevation: 2D float32 array of native elevations.
        native_slope: 2D float32 array of native slopes in degrees.
        native_roughness: 2D float32 array of native roughness in metres.
        block_size: Integer aggregation factor (e.g. 5 means 5x5 native cells per analysis cell).
        min_valid_fraction: Minimum required fraction of valid cells (default 0.90 per
            spec section 4.4).

    Returns:
        Dictionary containing:
        - "elevation": 2D float32 array of aggregated elevations (mean of valid).
        - "slope_max": 2D float32 array of aggregated slopes (conservative maximum).
        - "slope_mean": 2D float32 array of mean slopes across valid native cells.
        - "roughness_max": 2D float32 array of aggregated roughness (conservative maximum).
        - "valid_fraction": 2D float32 array of fraction of valid native cells [0.0, 1.0].
        - "is_valid": 2D boolean array where valid_fraction >= min_valid_fraction.
    """
    height, width = native_elevation.shape

    if block_size <= 1:
        # 1:1 mapping
        is_valid = ~np.isnan(native_elevation) & ~np.isnan(native_slope)
        valid_frac = np.where(is_valid, 1.0, 0.0).astype(np.float32)

        return {
            "elevation": np.where(is_valid, native_elevation, np.nan).astype(np.float32),
            "slope_max": np.where(is_valid, native_slope, np.nan).astype(np.float32),
            "slope_mean": np.where(is_valid, native_slope, np.nan).astype(np.float32),
            "roughness_max": np.where(is_valid, native_roughness, np.nan).astype(np.float32),
            "valid_fraction": valid_frac,
            "is_valid": is_valid,
        }

    # Trim to multiple of block_size
    h_out = height // block_size
    w_out = width // block_size

    h_trim = h_out * block_size
    w_trim = w_out * block_size

    elev_trim = native_elevation[:h_trim, :w_trim]
    slope_trim = native_slope[:h_trim, :w_trim]
    rough_trim = native_roughness[:h_trim, :w_trim]

    # Reshape into blocks of shape (h_out, block_size, w_out, block_size)
    # Transpose to (h_out, w_out, block_size, block_size) and flatten block axis
    def reshape_blocks(arr: np.ndarray) -> np.ndarray:
        return (
            arr.reshape(h_out, block_size, w_out, block_size)
            .transpose(0, 2, 1, 3)
            .reshape(h_out, w_out, block_size * block_size)
        )

    elev_blocks = reshape_blocks(elev_trim)
    slope_blocks = reshape_blocks(slope_trim)
    rough_blocks = reshape_blocks(rough_trim)

    n_cells_per_block = block_size * block_size

    # Validity rule per spec section 4.4:
    # Cell is valid only if >= 90 % of its native cells are valid
    valid_mask = ~np.isnan(elev_blocks)
    valid_counts = np.sum(valid_mask, axis=-1)
    valid_frac = (valid_counts / float(n_cells_per_block)).astype(np.float32)

    cell_is_valid = valid_frac >= min_valid_fraction

    # 1. Elevation: Mean of valid native cells
    with np.errstate(divide="ignore", invalid="ignore"):
        elev_sum = np.nansum(elev_blocks, axis=-1)
        elev_mean = np.where(valid_counts > 0, elev_sum / valid_counts, np.nan)

    # 2. Slope: Maximum native slope in the cell (mean also stored)
    # Using np.nanmax; where all cells are NaN, returns all-NaN
    with np.errstate(invalid="ignore"):
        slope_max = np.nanmax(slope_blocks, axis=-1)
        slope_sum = np.nansum(slope_blocks, axis=-1)
        slope_valid_count = np.sum(~np.isnan(slope_blocks), axis=-1)
        slope_mean = np.where(slope_valid_count > 0, slope_sum / slope_valid_count, np.nan)

    # 3. Roughness: Maximum native roughness in the cell
    with np.errstate(invalid="ignore"):
        rough_max = np.nanmax(rough_blocks, axis=-1)

    # Apply 90% validity rule: invalid cells become NaN
    agg_elev = np.where(cell_is_valid, elev_mean, np.nan).astype(np.float32)
    agg_slope_max = np.where(cell_is_valid, slope_max, np.nan).astype(np.float32)
    agg_slope_mean = np.where(cell_is_valid, slope_mean, np.nan).astype(np.float32)
    agg_rough_max = np.where(cell_is_valid, rough_max, np.nan).astype(np.float32)

    return {
        "elevation": agg_elev,
        "slope_max": agg_slope_max,
        "slope_mean": agg_slope_mean,
        "roughness_max": agg_rough_max,
        "valid_fraction": valid_frac,
        "is_valid": cell_is_valid,
    }
