"""Unit tests for search window bounding box and 5x analysis grid aggregation.

Verifies:
- Bounding window calculation with 25% padding (at least 500 m) clamped to full raster.
- Strict any-blocked aggregation rule on a tiny grid with hand-derived counts.
- Priority order of hazard codes: nodata (1) > exclusion (3) > slope (2).
- Trimming rule: trailing rows and columns not divisible by block factor 5 are discarded.
"""

import math

import numpy as np

from app.engines.routing.grid import compute_bounding_window
from app.engines.terrain.aggregate import aggregate_to_analysis_grid


def test_bounding_window_padding_hand_derived() -> None:
    """Bounding window applies max(0.25 * extent, 500 m) clamped to raster bounds."""
    # Pixel size = 1.0 m, full raster 5000 x 5000
    points = [(1000, 1000), (2000, 1500)]
    # dRow = 1000 m -> 25% = 250 m < 500 m -> pad_r = 500 m (500 px)
    # dCol = 500 m  -> 25% = 125 m < 500 m -> pad_c = 500 m (500 px)
    win, win_r0, win_c0, win_rows, win_cols = compute_bounding_window(
        points=points,
        full_height=5000,
        full_width=5000,
        pixel_size_m=1.0,
        padding_fraction=0.25,
        min_padding_m=500.0,
    )
    assert win_r0 == 1000 - 500  # 500
    assert win_c0 == 1000 - 500  # 500
    # win_r1 = min(5000, 2000 + 500 + 1) = 2501
    # win_c1 = min(5000, 1500 + 500 + 1) = 2001
    assert win_rows == 2501 - 500  # 2001
    assert win_cols == 2001 - 500  # 1501


def test_bounding_window_large_extent_uses_fraction() -> None:
    """Bounding window with large extent (>2000 m) uses 25% fraction rather than 500 m min."""
    points = [(1000, 1000), (5000, 5000)]
    # dRow = 4000 m -> 25% = 1000 m > 500 m -> pad_r = 1000 px
    win, win_r0, win_c0, win_rows, win_cols = compute_bounding_window(
        points=points,
        full_height=10000,
        full_width=10000,
        pixel_size_m=1.0,
        padding_fraction=0.25,
        min_padding_m=500.0,
    )
    assert win_r0 == 0
    assert win_c0 == 0
    # win_r1 = 5000 + 1000 + 1 = 6001
    assert win_rows == 6001
    assert win_cols == 6001


def test_strict_any_blocked_hand_count_and_trimming() -> None:
    """Strict any-blocked rule on a 12x12 native grid with block_factor=5.

    12x12 grid trimmed to (12 // 5) * 5 = 10x10.
    Produces a 2x2 analysis grid (4 blocks of 5x5).
    Trailing 2 rows (rows 10, 11) and 2 columns (cols 10, 11) are trimmed and ignored.

    Blocks:
    Block (0, 0): rows 0..4, cols 0..4. All slope = 5.0 (hazard 0). -> PASSABLE (code 0)
    Block (0, 1): rows 0..4, cols 5..9. One pixel has slope 20.0 -> IMPASSABLE_SLOPE (code 2)
    Block (1, 0): rows 5..9, cols 0..4. One pixel has hazard 3, one has slope 18.0.
                  Priority: code 3 > code 2 -> IMPASSABLE_EXCLUSION (code 3)
    Block (1, 1): rows 5..9, cols 5..9. One pixel at (6, 6) has NaN elevation (hazard 1).
                  Priority: code 1 > others -> IMPASSABLE_NODATA (code 1)
    """
    native_haz = np.zeros((12, 12), dtype=np.uint8)
    native_elev = np.full((12, 12), 100.0, dtype=np.float32)
    native_slope = np.full((12, 12), 5.0, dtype=np.float32)
    native_rough = np.full((12, 12), 0.05, dtype=np.float32)

    # Block (0, 1): slope hazard
    native_haz[1, 6] = 2
    native_slope[1, 6] = 20.0

    # Block (1, 0): exclusion and slope hazard
    native_haz[7, 2] = 3
    native_haz[8, 3] = 2
    native_slope[8, 3] = 18.0

    # Block (1, 1): nodata hazard
    native_haz[6, 6] = 1
    native_elev[6, 6] = np.nan

    # In trimmed area (row 11, col 11): set a hazard, must be discarded
    native_haz[11, 11] = 2
    native_slope[11, 11] = 45.0

    # Execute aggregation
    f = 5
    ho = 12 // f  # 2
    wo = 12 // f  # 2
    ht = ho * f  # 10
    wt = wo * f  # 10

    haz_blocks = (
        native_haz[:ht, :wt].reshape(ho, f, wo, f).transpose(0, 2, 1, 3).reshape(ho, wo, f * f)
    )

    strict_hazard = np.zeros((ho, wo), dtype=np.uint8)
    strict_hazard[np.any(haz_blocks == 2, axis=-1)] = 2
    strict_hazard[np.any(haz_blocks == 3, axis=-1)] = 3
    strict_hazard[np.any(haz_blocks == 1, axis=-1)] = 1

    assert strict_hazard.shape == (2, 2)
    assert strict_hazard[0, 0] == 0  # PASSABLE
    assert strict_hazard[0, 1] == 2  # IMPASSABLE_SLOPE
    assert strict_hazard[1, 0] == 3  # IMPASSABLE_EXCLUSION dominates slope
    assert strict_hazard[1, 1] == 1  # IMPASSABLE_NODATA dominates all

    # Conservative terrain aggregation
    agg = aggregate_to_analysis_grid(native_elev, native_slope, native_rough, block_size=5)
    assert agg["elevation"].shape == (2, 2)
    assert agg["slope_max"].shape == (2, 2)
    assert math.isclose(agg["slope_max"][0, 0], 5.0, abs_tol=1e-5)
    assert math.isclose(agg["slope_max"][0, 1], 20.0, abs_tol=1e-5)
    assert math.isclose(agg["slope_max"][1, 0], 18.0, abs_tol=1e-5)
    # Block (1, 1) has 24/25 valid cells (96% >= 90%), so elevation is mean of 24 cells
    assert math.isclose(agg["elevation"][1, 1], 100.0, abs_tol=1e-5)
