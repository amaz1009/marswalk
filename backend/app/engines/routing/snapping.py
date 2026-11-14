"""Endpoint passability validation and conservative snapping.

Implements AresNav Ruling C-03:
- If an endpoint (base, destination or stop) falls on an impassable analysis cell,
  snap ONLY if the native cell at the requested point is passable (native hazard code 0).
- Search concentric Chebyshev rings up to 3 analysis cells.
- Select candidate with minimum Euclidean cell distance, tie-breaking by (row, col).
- Never snap out of a natively blocked or nodata cell.
- Formulate standardized snap report strings for route.limitations.
"""

import math
from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine

from app.engines.hazards.grid import HazardState
from app.models.geometry import GeoPoint
from app.utils.coordinates import MarsCoordinateTransformer


@dataclass
class SnapResult:
    """Result of validating and snapping an endpoint on the analysis grid."""

    label: str
    requested_point: GeoPoint
    requested_full_cell: tuple[int, int]
    requested_analysis_cell: tuple[int, int]
    used_point: GeoPoint
    used_analysis_cell: tuple[int, int]
    is_snapped: bool
    snap_distance_m: float
    snap_message: str | None
    is_natively_blocked: bool
    is_within_tolerance: bool
    failure_reason: str | None = None


def resolve_and_snap_endpoint(
    label: str,
    point: GeoPoint,
    full_transform: Affine,
    win_r0: int,
    win_c0: int,
    block_factor: int,
    analysis_hazard: np.ndarray,
    native_hazard: np.ndarray,
    cell_size_m: float,
    crs_transformer: MarsCoordinateTransformer,
    max_search_ring: int = 3,
) -> SnapResult:
    """Resolve an endpoint to the analysis grid and snap if locally blocked by aggregation.

    Args:
        label: Point label ('base', 'destination', or stop name).
        point: Requested GeoPoint (lat, lon).
        full_transform: Affine transform of the full native raster.
        win_r0: Row offset of search window in full native raster.
        win_c0: Column offset of search window in full native raster.
        block_factor: Integer block aggregation factor (e.g. 5).
        analysis_hazard: 2D array of HazardState on the analysis grid.
        native_hazard: 2D array of HazardState on the native search window.
        cell_size_m: Metric resolution of an analysis cell.
        crs_transformer: MarsCoordinateTransformer instance.
        max_search_ring: Maximum ring distance to search (default 3).

    Returns:
        SnapResult dataclass.
    """
    # 1. Project GeoPoint to native raster coordinates
    x_proj, y_proj = crs_transformer.transform(point.lon, point.lat)
    inv_full = ~full_transform
    c_full_float, r_full_float = inv_full @ (x_proj, y_proj)
    r_full = int(math.floor(r_full_float))
    c_full = int(math.floor(c_full_float))

    # 2. Map to native window coordinates
    r_win = r_full - win_r0
    c_win = c_full - win_c0

    native_h, native_w = native_hazard.shape
    if not (0 <= r_win < native_h and 0 <= c_win < native_w):
        return SnapResult(
            label=label,
            requested_point=point,
            requested_full_cell=(r_full, c_full),
            requested_analysis_cell=(-1, -1),
            used_point=point,
            used_analysis_cell=(-1, -1),
            is_snapped=False,
            snap_distance_m=0.0,
            snap_message=None,
            is_natively_blocked=True,
            is_within_tolerance=False,
            failure_reason=(
                f"Endpoint '{label}' (lat {point.lat:.6f}, lon {point.lon:.6f}) falls "
                f"outside the search window."
            ),
        )

    native_code = int(native_hazard[r_win, c_win])

    # 3. Map to analysis grid coordinates
    r_agg = r_win // block_factor
    c_agg = c_win // block_factor

    agg_h, agg_w = analysis_hazard.shape
    if not (0 <= r_agg < agg_h and 0 <= c_agg < agg_w):
        return SnapResult(
            label=label,
            requested_point=point,
            requested_full_cell=(r_full, c_full),
            requested_analysis_cell=(r_agg, c_agg),
            used_point=point,
            used_analysis_cell=(r_agg, c_agg),
            is_snapped=False,
            snap_distance_m=0.0,
            snap_message=None,
            is_natively_blocked=True,
            is_within_tolerance=False,
            failure_reason=(f"Endpoint '{label}' falls on trimmed margin outside analysis grid."),
        )

    analysis_code = int(analysis_hazard[r_agg, c_agg])

    # Case A: Analysis cell is passable -> No snap needed
    if analysis_code == HazardState.PASSABLE:
        return SnapResult(
            label=label,
            requested_point=point,
            requested_full_cell=(r_full, c_full),
            requested_analysis_cell=(r_agg, c_agg),
            used_point=point,
            used_analysis_cell=(r_agg, c_agg),
            is_snapped=False,
            snap_distance_m=0.0,
            snap_message=None,
            is_natively_blocked=False,
            is_within_tolerance=True,
        )

    # Case B: Analysis cell is impassable. Check native passability.
    # Ruling C-03: Snap ONLY if the native cell at the requested point is passable (code 0)
    if native_code != HazardState.PASSABLE:
        haz_name = (
            HazardState(native_code).name
            if native_code in HazardState._value2member_map_
            else str(native_code)
        )
        return SnapResult(
            label=label,
            requested_point=point,
            requested_full_cell=(r_full, c_full),
            requested_analysis_cell=(r_agg, c_agg),
            used_point=point,
            used_analysis_cell=(r_agg, c_agg),
            is_snapped=False,
            snap_distance_m=0.0,
            snap_message=None,
            is_natively_blocked=True,
            is_within_tolerance=False,
            failure_reason=(
                f"Route point '{label}' lies on a natively impassable cell ({haz_name}). "
                f"Snapping is prohibited for natively blocked endpoints."
            ),
        )

    # Case C: Native cell is passable, but analysis cell was blocked by block-max aggregation.
    # Search concentric rings 1..max_search_ring for passable analysis cells.
    candidates = []
    for ring in range(1, max_search_ring + 1):
        for dr in range(-ring, ring + 1):
            for dc in range(-ring, ring + 1):
                if max(abs(dr), abs(dc)) == ring:
                    nr = r_agg + dr
                    nc = c_agg + dc
                    if 0 <= nr < agg_h and 0 <= nc < agg_w:
                        if analysis_hazard[nr, nc] == HazardState.PASSABLE:
                            dist = math.hypot(dr, dc)
                            candidates.append((dist, nr, nc))

    if not candidates:
        return SnapResult(
            label=label,
            requested_point=point,
            requested_full_cell=(r_full, c_full),
            requested_analysis_cell=(r_agg, c_agg),
            used_point=point,
            used_analysis_cell=(r_agg, c_agg),
            is_snapped=False,
            snap_distance_m=0.0,
            snap_message=None,
            is_natively_blocked=False,
            is_within_tolerance=False,
            failure_reason=(
                f"No passable analysis cell within {max_search_ring} cells of endpoint "
                f"'{label}' (requested lat {point.lat:.6f}, lon {point.lon:.6f}) "
                f"within the analysis window."
            ),
        )

    # Tie-break: lowest Euclidean distance, then lowest row, then lowest col
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    best_dist_cells, best_r_agg, best_c_agg = candidates[0]

    # Compute used geographic point from the center of the snapped analysis cell
    # Snapped cell on full native grid:
    snapped_native_r = win_r0 + best_r_agg * block_factor + block_factor // 2
    snapped_native_c = win_c0 + best_c_agg * block_factor + block_factor // 2
    used_x, used_y = full_transform @ (snapped_native_c + 0.5, snapped_native_r + 0.5)
    used_lon, used_lat = crs_transformer.inverse_transform(used_x, used_y)
    used_point = GeoPoint(lat=round(float(used_lat), 6), lon=round(float(used_lon), 6))

    snap_dist_m = float(best_dist_cells * cell_size_m)
    snap_msg = (
        f"Endpoint '{label}' snapped {snap_dist_m:.1f} m from requested "
        f"({point.lat:.6f}, {point.lon:.6f}) to usable "
        f"({used_point.lat:.6f}, {used_point.lon:.6f}) "
        f"due to localized obstacle in 5x5 analysis cell."
    )

    return SnapResult(
        label=label,
        requested_point=point,
        requested_full_cell=(r_full, c_full),
        requested_analysis_cell=(r_agg, c_agg),
        used_point=used_point,
        used_analysis_cell=(best_r_agg, best_c_agg),
        is_snapped=True,
        snap_distance_m=snap_dist_m,
        snap_message=snap_msg,
        is_natively_blocked=False,
        is_within_tolerance=True,
    )
