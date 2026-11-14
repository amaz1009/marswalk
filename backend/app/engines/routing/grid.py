"""Search window extraction and conservative analysis grid aggregation.

Implements AresNav SCIENCE_AND_SAFETY_SPEC.md section 4.4 and section 7.1:
- Search window bounding box derived from route points with 25% padding (at least 500 m).
- Windowed raster reading to avoid loading full regional rasters into memory.
- Ground spacing scaled per Decision D-013: dx_ground = |res_x| * cos(lat_mean).
- Analysis grid aggregation with fixed block factor 5 (ASSUMPTION):
  - Strict any-blocked: if any native cell in the block is blocked, the analysis cell is blocked.
  - Slope: block-max.
  - Roughness: block-max.
  - Elevation: block-mean.
  - Trailing rows and columns not divisible by 5 are trimmed at bottom and right.
"""

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

from app.engines.hazards.grid import HazardState, compute_hazard_grid
from app.engines.terrain.aggregate import aggregate_to_analysis_grid
from app.utils.coordinates import MARS_SPHERE_RADIUS_M

# Operational ASSUMPTIONS (per SCIENCE_AND_SAFETY_SPEC.md §7.1 and §4.4)
DEFAULT_WINDOW_PADDING_FRACTION: float = 0.25  # ASSUMPTION: 25% of bounding box extent
MIN_WINDOW_PADDING_METRES: float = 500.0  # ASSUMPTION: at least 500 m padding
DEFAULT_ANALYSIS_BLOCK_FACTOR: int = 5  # ASSUMPTION: 5x5 native cells per analysis cell


@dataclass
class WindowExtractionResult:
    """Result of extracting and aggregating terrain rasters to analysis grid resolution."""

    window: Window
    win_r0: int
    win_c0: int
    win_rows: int
    win_cols: int
    h_out: int
    w_out: int
    total_cells: int
    cell_size_m: float
    analysis_transform: Affine
    elevation: np.ndarray
    slope_max: np.ndarray
    roughness_max: np.ndarray
    hazard_states: np.ndarray
    native_hazard_states: np.ndarray
    dx_ground_m: float
    dy_ground_m: float
    mean_lat_deg: float
    is_grid_too_large: bool = False


def compute_bounding_window(
    points: Sequence[tuple[int, int]],
    full_height: int,
    full_width: int,
    pixel_size_m: float,
    padding_fraction: float = DEFAULT_WINDOW_PADDING_FRACTION,
    min_padding_m: float = MIN_WINDOW_PADDING_METRES,
) -> tuple[Window, int, int, int, int]:
    """Compute clamped bounding box window around integer pixel points with padding.

    Args:
        points: List of (row, col) coordinates on the full raster.
        full_height: Height of the full raster in pixels.
        full_width: Width of the full raster in pixels.
        pixel_size_m: Projected resolution in metres.
        padding_fraction: Fraction of bounding box extent to pad (default 0.25).
        min_padding_m: Minimum padding distance in metres (default 500.0 m).

    Returns:
        Tuple of (Window, win_r0, win_c0, win_rows, win_cols).
    """
    rows = [p[0] for p in points]
    cols = [p[1] for p in points]

    r_min, r_max = min(rows), max(rows)
    c_min, c_max = min(cols), max(cols)

    box_h_m = (r_max - r_min) * pixel_size_m
    box_w_m = (c_max - c_min) * pixel_size_m

    pad_r_m = max(padding_fraction * box_h_m, min_padding_m)
    pad_c_m = max(padding_fraction * box_w_m, min_padding_m)

    pad_r = int(math.ceil(pad_r_m / pixel_size_m))
    pad_c = int(math.ceil(pad_c_m / pixel_size_m))

    win_r0 = max(0, r_min - pad_r)
    win_r1 = min(full_height, r_max + pad_r + 1)
    win_c0 = max(0, c_min - pad_c)
    win_c1 = min(full_width, c_max + pad_c + 1)

    win_rows = win_r1 - win_r0
    win_cols = win_c1 - win_c0

    win = Window(win_c0, win_r0, win_cols, win_rows)
    return win, win_r0, win_c0, win_rows, win_cols


def extract_analysis_grid(
    dtm_reader: rasterio.io.DatasetReaderBase,
    slope_reader: rasterio.io.DatasetReaderBase,
    roughness_reader: rasterio.io.DatasetReaderBase,
    points: Sequence[tuple[int, int]],
    max_slope_deg: float,
    max_grid_cells: int = 4_000_000,
    block_factor: int = DEFAULT_ANALYSIS_BLOCK_FACTOR,
    padding_fraction: float = DEFAULT_WINDOW_PADDING_FRACTION,
    min_padding_m: float = MIN_WINDOW_PADDING_METRES,
) -> WindowExtractionResult:
    """Extract search window and aggregate to analysis grid resolution.

    Args:
        dtm_reader: Open rasterio reader for DTM elevation.
        slope_reader: Open rasterio reader for slope.
        roughness_reader: Open rasterio reader for roughness.
        points: List of (row, col) pixel coordinates on full raster for base, stops, destination.
        max_slope_deg: Maximum permissible traversal slope in degrees.
        max_grid_cells: Maximum permissible analysis grid cells (ARESNAV_MAX_GRID_CELLS).
        block_factor: Integer aggregation factor (default 5).
        padding_fraction: Fraction of extent for padding (default 0.25).
        min_padding_m: Minimum padding distance in metres (default 500.0).

    Returns:
        WindowExtractionResult.
    """
    full_h, full_w = dtm_reader.shape
    full_transform = dtm_reader.transform
    res_x = float(full_transform.a)
    res_y = float(-full_transform.e)

    win, win_r0, win_c0, win_rows, win_cols = compute_bounding_window(
        points=points,
        full_height=full_h,
        full_width=full_w,
        pixel_size_m=res_x,
        padding_fraction=padding_fraction,
        min_padding_m=min_padding_m,
    )

    # Output analysis grid dimensions (trimming trailing rows/cols not divisible by block_factor)
    h_out = win_rows // block_factor
    w_out = win_cols // block_factor
    total_cells = h_out * w_out

    # Guard: check analysis grid cell count against cap
    if total_cells > max_grid_cells:
        dummy_arr = np.zeros((1, 1), dtype=np.float32)
        dummy_haz = np.zeros((1, 1), dtype=np.uint8)
        return WindowExtractionResult(
            window=win,
            win_r0=win_r0,
            win_c0=win_c0,
            win_rows=win_rows,
            win_cols=win_cols,
            h_out=h_out,
            w_out=w_out,
            total_cells=total_cells,
            cell_size_m=res_x * block_factor,
            analysis_transform=full_transform,
            elevation=dummy_arr,
            slope_max=dummy_arr,
            roughness_max=dummy_arr,
            hazard_states=dummy_haz,
            native_hazard_states=dummy_haz,
            dx_ground_m=res_x,
            dy_ground_m=res_y,
            mean_lat_deg=0.0,
            is_grid_too_large=True,
        )

    # Perform windowed read
    win_elev = dtm_reader.read(1, window=win)
    win_slope = slope_reader.read(1, window=win)
    win_rough = roughness_reader.read(1, window=win)

    # Compute native hazard grid
    valid_mask = ~np.isnan(win_elev) & ~np.isnan(win_slope)
    native_haz_res = compute_hazard_grid(
        elevation=win_elev,
        slope=win_slope,
        max_slope_deg=max_slope_deg,
        exclusion_mask=None,
        valid_mask=valid_mask,
    )
    native_haz = native_haz_res.states

    # Aggregate terrain arrays using conservative aggregate_to_analysis_grid
    agg = aggregate_to_analysis_grid(
        native_elevation=win_elev,
        native_slope=win_slope,
        native_roughness=win_rough,
        block_size=block_factor,
        min_valid_fraction=0.90,
    )

    # Compute strict any-blocked hazard reduction
    h_trim = h_out * block_factor
    w_trim = w_out * block_factor
    haz_blocks = (
        native_haz[:h_trim, :w_trim]
        .reshape(h_out, block_factor, w_out, block_factor)
        .transpose(0, 2, 1, 3)
        .reshape(h_out, w_out, block_factor * block_factor)
    )

    # Priority determination for strict any-blocked:
    # 1: IMPASSABLE_NODATA (Priority 1)
    # 3: IMPASSABLE_EXCLUSION (Priority 2)
    # 2: IMPASSABLE_SLOPE (Priority 3)
    strict_hazard = np.zeros((h_out, w_out), dtype=np.uint8)
    strict_hazard[np.any(haz_blocks == 2, axis=-1)] = HazardState.IMPASSABLE_SLOPE
    strict_hazard[np.any(haz_blocks == 3, axis=-1)] = HazardState.IMPASSABLE_EXCLUSION
    strict_hazard[np.any(haz_blocks == 1, axis=-1)] = HazardState.IMPASSABLE_NODATA

    # Also mark any cell failing 90% validity rule as IMPASSABLE_NODATA
    invalid_cells = ~agg["is_valid"]
    strict_hazard[invalid_cells] = HazardState.IMPASSABLE_NODATA

    # Compute ground spacing scaled by cos(mean_lat) per Decision D-013
    row_indices = np.arange(win_r0, win_r0 + h_trim)
    ys = full_transform.f + (row_indices + 0.5) * full_transform.e
    lats_rad = ys / MARS_SPHERE_RADIUS_M
    mean_lat_rad = float(np.mean(lats_rad))
    mean_lat_deg = math.degrees(mean_lat_rad)

    dx_ground = res_x * math.cos(mean_lat_rad)
    dy_ground = res_y
    mean_spacing = (dx_ground + dy_ground) / 2.0
    cell_size_m = mean_spacing * block_factor

    analysis_transform = Affine(
        full_transform.a * block_factor,
        0.0,
        full_transform.c + win_c0 * full_transform.a,
        0.0,
        full_transform.e * block_factor,
        full_transform.f + win_r0 * full_transform.e,
    )

    return WindowExtractionResult(
        window=win,
        win_r0=win_r0,
        win_c0=win_c0,
        win_rows=win_rows,
        win_cols=win_cols,
        h_out=h_out,
        w_out=w_out,
        total_cells=total_cells,
        cell_size_m=cell_size_m,
        analysis_transform=analysis_transform,
        elevation=agg["elevation"],
        slope_max=agg["slope_max"],
        roughness_max=agg["roughness_max"],
        hazard_states=strict_hazard,
        native_hazard_states=native_haz,
        dx_ground_m=dx_ground,
        dy_ground_m=dy_ground,
        mean_lat_deg=mean_lat_deg,
        is_grid_too_large=False,
    )
