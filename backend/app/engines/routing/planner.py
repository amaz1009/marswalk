"""EVA route planning engine across multi-objective profiles.

Implements the complete traverse optimization workflow defined in
AresNav SCIENCE_AND_SAFETY_SPEC.md section 7:
- Route point placement without snapping or moving (section 7.1)
- Search window bounding box derivation with 25% padding (at least 500 m) (section 7.1)
- Fallback to full grid if within ARESNAV_MAX_GRID_CELLS, else GRID_TOO_LARGE (section 7.1)
- Multi-objective profiles: LOWEST_RISK, BALANCED, MAX_SCIENCE (section 7.3)
- Omission of MAX_SCIENCE when science-interest layer is absent (section 7.3)
- Multi-leg sequential routing with optional return-to-base leg (section 7.6)
- Duplicate route detection setting identical_to (section 7.7)
- Comprehensive route statistics (section 7.8)
"""

import math
from dataclasses import dataclass, field
from typing import Any, Sequence, Union

import numpy as np

from app.engines.hazards.grid import HazardState
from app.engines.routing.astar import run_astar
from app.engines.routing.cost import (
    PROFILE_WEIGHTS,
    ObjectiveWeights,
    precompute_cell_cost_factors,
)
from app.models.enums import PlanStatus, RouteObjective
from app.models.eva import OmittedObjective, StatSummary
from app.models.geometry import GeoPoint
from app.models.terrain import ProfilePoint
from app.utils.geodesy import haversine_distance


@dataclass
class PlannedLeg:
    """Traverse segment between two consecutive stops or bases."""

    from_label: str
    to_label: str
    path_cells: list[tuple[int, int]]
    path_points: list[GeoPoint]
    horizontal_distance_m: float
    surface_distance_m: float
    ascent_m: float
    descent_m: float
    walk_time_s: float


@dataclass
class PlannedRouteTotals:
    """Aggregated metrics for an entire planned route."""

    horizontal_distance_m: float
    surface_distance_m: float
    ascent_m: float
    descent_m: float
    walk_time_s: float


@dataclass
class PlannedRoute:
    """Complete computed route for an optimization profile."""

    route_id: str
    objective: RouteObjective
    identical_to: str | None
    legs: list[PlannedLeg]
    path: list[GeoPoint]
    full_path_cells: list[tuple[int, int]]
    elevation_profile: list[ProfilePoint]
    slope_stats: StatSummary
    roughness_stats: StatSummary
    fraction_above_warning_slope: float
    max_distance_from_base_m: float
    primary_coverage_fraction: float
    totals: PlannedRouteTotals


@dataclass
class PlanOutcome:
    """Overall outcome of route planning."""

    status: PlanStatus
    blocking_reason: str | None = None
    blocking_point: str | None = None
    blocking_leg: str | None = None
    is_grid_too_large: bool = False
    geo_referenced: bool = False
    routes: list[PlannedRoute] = field(default_factory=list)
    omitted_objectives: list[OmittedObjective] = field(default_factory=list)


def resolve_point_to_cell(
    point: Union[GeoPoint, tuple[int, int], tuple[float, float]],
    transform: Any = None,
    crs_transformer: Any = None,
) -> tuple[int, int]:
    """Convert input point coordinate into (row, col) grid cell index.

    Route points are placed in the cell that contains them. They are not moved.

    Args:
        point: GeoPoint, (lat, lon), or (row, col) tuple.
        transform: Optional rasterio Affine transform.
        crs_transformer: Optional MarsCoordinateTransformer.

    Returns:
        (row, col) integer cell indices.

    Raises:
        ValueError: If transform or crs_transformer is provided without the other,
            or if a GeoPoint / geographic coordinate is provided without both.
    """
    has_transform = transform is not None
    has_crs = crs_transformer is not None
    if has_transform != has_crs:
        raise ValueError(
            "Both 'transform' and 'crs_transformer' must be provided together, or neither."
        )

    if isinstance(point, GeoPoint):
        if not (has_transform and has_crs):
            raise ValueError(
                "Cannot resolve GeoPoint to grid cell without both "
                "'transform' and 'crs_transformer'."
            )
        lat, lon = point.lat, point.lon
    elif isinstance(point, tuple) and len(point) == 2:
        val0, val1 = point
        # Integer tuple is direct grid (row, col)
        if isinstance(val0, (int, np.integer)) and isinstance(val1, (int, np.integer)):
            return int(val0), int(val1)
        # Float tuple requires spatial referencing
        if not (has_transform and has_crs):
            raise ValueError(
                "Cannot resolve geographic coordinate tuple to grid cell without both "
                "'transform' and 'crs_transformer'."
            )
        lat, lon = float(val0), float(val1)
    else:
        raise TypeError(f"Unsupported point type: {type(point)}")

    proj_x, proj_y = crs_transformer.transform(lon, lat)
    col_f, row_f = ~transform @ (proj_x, proj_y)
    return int(math.floor(row_f)), int(math.floor(col_f))


def cell_to_geopoint(
    row: int,
    col: int,
    transform: Any = None,
    crs_transformer: Any = None,
) -> GeoPoint | None:
    """Convert grid cell (row, col) to cell-centre GeoPoint.

    Args:
        row: Grid cell row index.
        col: Grid cell column index.
        transform: Optional rasterio Affine transform.
        crs_transformer: Optional MarsCoordinateTransformer.

    Returns:
        GeoPoint if spatially referenced, or None in grid-only mode.

    Raises:
        ValueError: If transform or crs_transformer is provided without the other.
    """
    has_transform = transform is not None
    has_crs = crs_transformer is not None
    if has_transform != has_crs:
        raise ValueError(
            "Both 'transform' and 'crs_transformer' must be provided together, or neither."
        )

    if has_transform and has_crs:
        proj_x, proj_y = transform * (col + 0.5, row + 0.5)
        lon, lat = crs_transformer.inverse_transform(proj_x, proj_y)
        return GeoPoint(lat=lat, lon=lon)

    return None


def compute_route_statistics(
    full_path_cells: list[tuple[int, int]],
    elevation: np.ndarray,
    slope: np.ndarray,
    roughness: np.ndarray,
    cell_size_m: float,
    warning_slope_deg: float,
    base_geopoint: GeoPoint | None = None,
    path_geopoints: list[GeoPoint] | None = None,
    base_cell: tuple[int, int] | None = None,
) -> tuple[StatSummary, StatSummary, float, float, float]:
    """Compute slope/roughness statistics and EVA metrics along a path.

    Returns:
        tuple: (slope_stats, roughness_stats, fraction_above_warning_slope,
                max_distance_from_base_m, primary_coverage_fraction)
    """
    if not full_path_cells:
        empty_stat = StatSummary(max=None, mean=None, p95=None, units="degrees")
        empty_r = StatSummary(max=None, mean=None, p95=None, units="m")
        return empty_stat, empty_r, 0.0, 0.0, 1.0

    slopes = [float(slope[r, c]) for r, c in full_path_cells]
    roughnesses = [float(roughness[r, c]) for r, c in full_path_cells]

    slope_stats = StatSummary(
        max=float(np.max(slopes)),
        mean=float(np.mean(slopes)),
        p95=float(np.percentile(slopes, 95)),
        units="degrees",
    )
    roughness_stats = StatSummary(
        max=float(np.max(roughnesses)),
        mean=float(np.mean(roughnesses)),
        p95=float(np.percentile(roughnesses, 95)),
        units="m",
    )

    # Fraction of horizontal length above warning slope
    total_h_dist = 0.0
    warning_h_dist = 0.0
    ortho_dist = float(cell_size_m)
    diag_dist = float(cell_size_m * math.sqrt(2.0))

    for i in range(len(full_path_cells) - 1):
        r_a, c_a = full_path_cells[i]
        r_b, c_b = full_path_cells[i + 1]
        is_diag = (abs(r_b - r_a) == 1) and (abs(c_b - c_a) == 1)
        dh = diag_dist if is_diag else ortho_dist
        total_h_dist += dh

        if float(slope[r_b, c_b]) > warning_slope_deg:
            warning_h_dist += dh

    fraction_above_warning = float(warning_h_dist / total_h_dist) if total_h_dist > 0.0 else 0.0

    # Max distance from base: great-circle if georeferenced, or Euclidean grid distance in metres
    if base_geopoint is not None and path_geopoints:
        max_dist = 0.0
        for pt in path_geopoints:
            d = haversine_distance(base_geopoint.lat, base_geopoint.lon, pt.lat, pt.lon)
            if d > max_dist:
                max_dist = d
    elif base_cell is not None and full_path_cells:
        base_r, base_c = base_cell
        max_dist = max(
            math.hypot((r - base_r) * cell_size_m, (c - base_c) * cell_size_m)
            for r, c in full_path_cells
        )
    else:
        max_dist = 0.0

    # Primary coverage fraction: valid cells on path
    valid_count = sum(1 for r, c in full_path_cells if not math.isnan(float(elevation[r, c])))
    primary_coverage = float(valid_count / len(full_path_cells)) if full_path_cells else 1.0

    return slope_stats, roughness_stats, fraction_above_warning, max_dist, primary_coverage


def plan_routes(
    elevation: np.ndarray,
    slope: np.ndarray,
    roughness: np.ndarray,
    hazard_states: np.ndarray,
    base: Union[GeoPoint, tuple[int, int]],
    destination: Union[GeoPoint, tuple[int, int]],
    stops: Sequence[Union[GeoPoint, tuple[int, int]]] | None = None,
    stop_labels: Sequence[str] | None = None,
    base_label: str = "base",
    destination_label: str = "destination",
    cell_size_m: float = 1.0,
    transform: Any = None,
    crs_transformer: Any = None,
    objectives: Sequence[RouteObjective] | None = None,
    base_speed_kmh: float = 2.7,
    max_slope_deg: float = 15.0,
    warning_slope_deg: float = 10.0,
    roughness_warning_m: float = 0.30,
    return_to_base: bool = True,
    near_hazard: np.ndarray | None = None,
    science_interest: np.ndarray | None = None,
    max_grid_cells: int = 4_000_000,
    grid: Any = None,
) -> PlanOutcome:
    """Plan multi-objective traverse routes across an analysis grid.

    Spatial Reference Modes:
        - If both 'transform' and 'crs_transformer' are provided, the planner runs
          in spatially-referenced mode (geo_referenced=True). Coordinates are
          projected, path_points and route path contain valid GeoPoints,
          elevation_profile is populated, and max_distance_from_base_m is computed
          via great-circle haversine distance.
        - If neither is provided, the planner runs in grid-only mode for synthetic
          grids ("grid coordinates only, geographic outputs are not real").
          In grid-only mode, geo_referenced is False, path_points and route path
          are empty ([]), elevation_profile is empty ([]), and
          max_distance_from_base_m is computed from Euclidean grid distances
          (cell_size_m times the grid offset).
        - If one is provided without the other, a ValueError is raised.
        - If input route points are GeoPoints (lat/lon), both transform and
          crs_transformer are strictly required; omitting them raises ValueError.

    Args:
        elevation: 2D array of elevations in metres.
        slope: 2D array of slopes in degrees.
        roughness: 2D array of roughness in metres.
        hazard_states: 2D array of HazardState integer codes.
        base: Starting coordinate (GeoPoint or (row, col)).
        destination: Primary turnaround coordinate.
        stops: Optional list of intermediate science stops.
        stop_labels: Optional labels for intermediate stops.
        base_label: Label for starting base.
        destination_label: Label for destination.
        cell_size_m: Grid spacing in metres. Callers must pass the true ground
            spacing (e.g. the native pixel is about 1.0117 m, Decision D-013 scales
            east-west ground spacing by cos(latitude)); the engine uses cell_size_m
            directly as the planar metric step distance.
        transform: Optional rasterio Affine transform.
        crs_transformer: Optional MarsCoordinateTransformer.
        objectives: Optional list of RouteObjective profiles to evaluate.
        base_speed_kmh: Nominal flat walking speed in km/h.
        max_slope_deg: Traversal slope limit in degrees.
        warning_slope_deg: Caution slope threshold in degrees.
        roughness_warning_m: Caution roughness threshold in metres.
        return_to_base: Whether to include a return leg from destination to base.
        near_hazard: Optional 2D boolean array of NEAR_HAZARD flags.
        science_interest: Optional 2D array of science interest in [0, 1].
        max_grid_cells: Cap on grid cells for search window expansion.
        grid: Optional AnalysisGrid instance (overrides array parameters if supplied).

    Returns:
        PlanOutcome dataclass.

    Performance Limitation:
        On a 1 m resolution analysis grid, traverses >= 2 km with 25% padding
        (at least 500 m) will derive search bounding boxes exceeding 4,000,000
        cells (ARESNAV_MAX_GRID_CELLS) and return status=NO_FEASIBLE_ROUTE with
        is_grid_too_large=True (GRID_TOO_LARGE). To plan traverses at regional or
        multi-kilometre scale, the analysis grid must be aggregated to a coarser
        resolution (e.g. 5 m or 10 m, as specified in SCIENCE_AND_SAFETY_SPEC.md
        section 4.4), which is an owner design decision for WP-11.
    """
    if grid is not None:
        elevation = grid.elevation
        slope = grid.slope
        roughness = grid.roughness
        hazard_states = grid.hazard_states
        near_hazard = grid.near_hazard
        transform = grid.transform
        cell_size_m = grid.cell_size_m

    # Spatial referencing: both transform and crs_transformer must be supplied together, or neither
    has_transform = transform is not None
    has_crs = crs_transformer is not None
    if has_transform != has_crs:
        raise ValueError(
            "Both 'transform' and 'crs_transformer' must be provided together, or neither."
        )
    geo_referenced = has_transform and has_crs

    rows, cols = elevation.shape

    # Non-negotiable scientific integrity: missing data is never zero and never PASS.
    # Non-finite values in elevation, slope, roughness (and science interest if present)
    # are strictly treated as IMPASSABLE_NODATA. Caller arrays are NEVER modified.
    working_hazards = np.copy(hazard_states)
    non_finite_mask = ~np.isfinite(elevation) | ~np.isfinite(slope) | ~np.isfinite(roughness)
    if science_interest is not None:
        non_finite_mask = non_finite_mask | ~np.isfinite(science_interest)

    working_hazards[non_finite_mask] = HazardState.IMPASSABLE_NODATA

    # 1. Resolve and validate all route points in sequence
    raw_points: list[tuple[str, Union[GeoPoint, tuple[int, int]]]] = [(base_label, base)]
    if stops:
        for idx, st in enumerate(stops):
            lbl = stop_labels[idx] if stop_labels and idx < len(stop_labels) else f"stop {idx + 1}"
            raw_points.append((lbl, st))
    raw_points.append((destination_label, destination))

    resolved_points: list[tuple[str, tuple[int, int], GeoPoint | None]] = []

    for lbl, pt in raw_points:
        try:
            r, c = resolve_point_to_cell(pt, transform=transform, crs_transformer=crs_transformer)
        except ValueError:
            raise
        except Exception as e:
            return PlanOutcome(
                status=PlanStatus.INSUFFICIENT_DATA,
                blocking_reason=f"Failed to resolve coordinate for point '{lbl}': {e}",
                blocking_point=lbl,
                geo_referenced=geo_referenced,
            )

        # Check bounds
        if not (0 <= r < rows and 0 <= c < cols):
            return PlanOutcome(
                status=PlanStatus.INSUFFICIENT_DATA,
                blocking_reason=f"Route point '{lbl}' lies outside grid bounds",
                blocking_point=lbl,
                geo_referenced=geo_referenced,
            )

        # Check hazard state and missing data
        state = working_hazards[r, c]
        if state == HazardState.IMPASSABLE_NODATA or non_finite_mask[r, c]:
            return PlanOutcome(
                status=PlanStatus.INSUFFICIENT_DATA,
                blocking_reason=f"Route point '{lbl}' lies on missing data (IMPASSABLE_NODATA)",
                blocking_point=lbl,
                geo_referenced=geo_referenced,
            )
        if state in (HazardState.IMPASSABLE_SLOPE, HazardState.IMPASSABLE_EXCLUSION):
            state_name = HazardState(state).name
            return PlanOutcome(
                status=PlanStatus.NO_FEASIBLE_ROUTE,
                blocking_reason=f"Route point '{lbl}' lies on an impassable cell ({state_name})",
                blocking_point=lbl,
                geo_referenced=geo_referenced,
            )

        gp = (
            pt
            if isinstance(pt, GeoPoint)
            else cell_to_geopoint(r, c, transform=transform, crs_transformer=crs_transformer)
        )
        resolved_points.append((lbl, (r, c), gp))

    # 2. Derive Search Window with 25% padding (at least 500 m) (section 7.1)
    all_rows = [p[1][0] for p in resolved_points]
    all_cols = [p[1][1] for p in resolved_points]
    r_min, r_max = min(all_rows), max(all_rows)
    c_min, c_max = min(all_cols), max(all_cols)

    box_h_m = (r_max - r_min) * cell_size_m
    box_w_m = (c_max - c_min) * cell_size_m
    pad_r_m = max(0.25 * box_h_m, 500.0)
    pad_c_m = max(0.25 * box_w_m, 500.0)

    pad_r = int(math.ceil(pad_r_m / cell_size_m))
    pad_c = int(math.ceil(pad_c_m / cell_size_m))

    win_r0 = max(0, r_min - pad_r)
    win_r1 = min(rows, r_max + pad_r + 1)
    win_c0 = max(0, c_min - pad_c)
    win_c1 = min(cols, c_max + pad_c + 1)

    win_cells = (win_r1 - win_r0) * (win_c1 - win_c0)
    if win_cells > max_grid_cells:
        return PlanOutcome(
            status=PlanStatus.NO_FEASIBLE_ROUTE,
            blocking_reason=(
                f"Search window size {win_cells} cells exceeds maximum limit of "
                f"{max_grid_cells} cells (GRID_TOO_LARGE)"
            ),
            is_grid_too_large=True,
            geo_referenced=geo_referenced,
        )

    # 3. Handle requested profiles and science-interest omission (section 7.3)
    requested_objs = (
        list(objectives)
        if objectives is not None
        else [
            RouteObjective.LOWEST_RISK,
            RouteObjective.BALANCED,
            RouteObjective.MAX_SCIENCE,
        ]
    )

    omitted_objectives: list[OmittedObjective] = []
    active_objs: list[RouteObjective] = []

    for obj in requested_objs:
        if obj == RouteObjective.MAX_SCIENCE and science_interest is None:
            omitted_objectives.append(
                OmittedObjective(
                    objective=RouteObjective.MAX_SCIENCE,
                    reason="no science-interest layer available",
                )
            )
        else:
            active_objs.append(obj)

    # 4. Sequential leg definitions: base -> stop 1 -> ... -> destination [-> base]
    legs_spec: list[tuple[str, str, tuple[int, int], tuple[int, int]]] = []
    for i in range(len(resolved_points) - 1):
        from_lbl, from_rc, _ = resolved_points[i]
        to_lbl, to_rc, _ = resolved_points[i + 1]
        legs_spec.append((from_lbl, to_lbl, from_rc, to_rc))

    if return_to_base and len(resolved_points) > 1:
        dest_lbl, dest_rc, _ = resolved_points[-1]
        base_lbl, base_rc, _ = resolved_points[0]
        legs_spec.append((dest_lbl, base_lbl, dest_rc, base_rc))

    # 5. Execute routing per active objective profile
    computed_routes: list[PlannedRoute] = []

    for profile in active_objs:
        # Determine profile weights (section 7.3)
        base_weights = PROFILE_WEIGHTS[profile]
        if science_interest is None and profile == RouteObjective.BALANCED:
            weights = ObjectiveWeights(
                w_s=base_weights.w_s,
                w_r=base_weights.w_r,
                w_h=base_weights.w_h,
                w_sci=0.0,
            )
        else:
            weights = base_weights

        # Precompute static cell factors inside search window
        sub_elev = elevation[win_r0:win_r1, win_c0:win_c1]
        sub_slope = slope[win_r0:win_r1, win_c0:win_c1]
        sub_roughness = roughness[win_r0:win_r1, win_c0:win_c1]
        sub_haz = working_hazards[win_r0:win_r1, win_c0:win_c1]
        sub_mask = non_finite_mask[win_r0:win_r1, win_c0:win_c1]

        safe_sub_slope = np.where(sub_mask, 0.0, sub_slope)
        safe_sub_roughness = np.where(sub_mask, 0.0, sub_roughness)
        sub_sci = (
            science_interest[win_r0:win_r1, win_c0:win_c1] if science_interest is not None else None
        )
        safe_sub_sci = np.where(sub_mask, 0.0, sub_sci) if sub_sci is not None else None
        sub_near = near_hazard[win_r0:win_r1, win_c0:win_c1] if near_hazard is not None else None

        sub_factors = precompute_cell_cost_factors(
            slope_deg=safe_sub_slope,
            roughness_m=safe_sub_roughness,
            hazard_states=sub_haz,
            weights=weights,
            near_hazard=sub_near,
            max_slope_deg=max_slope_deg,
            roughness_warning_m=roughness_warning_m,
            science_interest=safe_sub_sci,
        )

        planned_legs: list[PlannedLeg] = []
        profile_failed = False
        failing_leg_name = ""

        for from_lbl, to_lbl, (fr_r, fr_c), (to_r, to_c) in legs_spec:
            # Map coordinates to search window
            local_start = (fr_r - win_r0, fr_c - win_c0)
            local_goal = (to_r - win_r0, to_c - win_c0)

            # Search within window first
            astar_res = run_astar(
                start=local_start,
                goal=local_goal,
                elevation=sub_elev,
                hazard_states=sub_haz,
                cell_cost_factors=sub_factors,
                cell_size_m=cell_size_m,
                base_speed_kmh=base_speed_kmh,
                w_sci=weights.w_sci,
            )

            # If no path found, repeat once on full grid if allowed (section 7.1)
            is_full_grid = win_r0 == 0 and win_r1 == rows and win_c0 == 0 and win_c1 == cols
            if not astar_res.success and not is_full_grid:
                total_cells = rows * cols
                if total_cells > max_grid_cells:
                    return PlanOutcome(
                        status=PlanStatus.NO_FEASIBLE_ROUTE,
                        blocking_reason=(
                            f"Search window fallback to full grid ({total_cells} cells) exceeds "
                            f"limit of {max_grid_cells} cells (GRID_TOO_LARGE)"
                        ),
                        is_grid_too_large=True,
                        geo_referenced=geo_referenced,
                    )

                # Precompute full grid factors
                safe_full_slope = np.where(non_finite_mask, 0.0, slope)
                safe_full_roughness = np.where(non_finite_mask, 0.0, roughness)
                safe_full_sci = (
                    np.where(non_finite_mask, 0.0, science_interest)
                    if science_interest is not None
                    else None
                )

                full_factors = precompute_cell_cost_factors(
                    slope_deg=safe_full_slope,
                    roughness_m=safe_full_roughness,
                    hazard_states=working_hazards,
                    weights=weights,
                    near_hazard=near_hazard,
                    max_slope_deg=max_slope_deg,
                    roughness_warning_m=roughness_warning_m,
                    science_interest=safe_full_sci,
                )

                astar_res = run_astar(
                    start=(fr_r, fr_c),
                    goal=(to_r, to_c),
                    elevation=elevation,
                    hazard_states=working_hazards,
                    cell_cost_factors=full_factors,
                    cell_size_m=cell_size_m,
                    base_speed_kmh=base_speed_kmh,
                    w_sci=weights.w_sci,
                )
                offset_r, offset_c = 0, 0
            else:
                offset_r, offset_c = win_r0, win_c0

            if not astar_res.success:
                profile_failed = True
                failing_leg_name = f"{from_lbl} -> {to_lbl}"
                break

            # Map path cells to global grid coordinates
            global_path_cells = [(r + offset_r, c + offset_c) for r, c in astar_res.path]
            path_points = (
                [
                    cell_to_geopoint(r, c, transform=transform, crs_transformer=crs_transformer)
                    for r, c in global_path_cells
                ]
                if geo_referenced
                else []
            )

            planned_legs.append(
                PlannedLeg(
                    from_label=from_lbl,
                    to_label=to_lbl,
                    path_cells=global_path_cells,
                    path_points=path_points,
                    horizontal_distance_m=astar_res.horizontal_distance_m,
                    surface_distance_m=astar_res.surface_distance_m,
                    ascent_m=astar_res.ascent_m,
                    descent_m=astar_res.descent_m,
                    walk_time_s=astar_res.walk_time_s,
                )
            )

        if profile_failed:
            return PlanOutcome(
                status=PlanStatus.NO_FEASIBLE_ROUTE,
                blocking_reason=f"No feasible route for leg: {failing_leg_name}",
                blocking_leg=failing_leg_name,
                geo_referenced=geo_referenced,
            )

        # Concatenate full path across all legs
        full_path_cells: list[tuple[int, int]] = []
        full_path_points: list[GeoPoint] = []
        for leg_idx, leg in enumerate(planned_legs):
            cells = leg.path_cells if leg_idx == 0 else leg.path_cells[1:]
            full_path_cells.extend(cells)
            if geo_referenced:
                points = leg.path_points if leg_idx == 0 else leg.path_points[1:]
                full_path_points.extend(points)

        # Calculate elevation profile points (populated only if georeferenced)
        elevation_profile: list[ProfilePoint] = []
        if geo_referenced:
            cum_dist = 0.0
            ortho_dist = float(cell_size_m)
            diag_dist = float(cell_size_m * math.sqrt(2.0))

            for idx, (r, c) in enumerate(full_path_cells):
                if idx > 0:
                    prev_r, prev_c = full_path_cells[idx - 1]
                    is_diag = (abs(r - prev_r) == 1) and (abs(c - prev_c) == 1)
                    cum_dist += diag_dist if is_diag else ortho_dist

                elevation_profile.append(
                    ProfilePoint(
                        distance_m=cum_dist,
                        point=full_path_points[idx],
                        elevation_m=float(elevation[r, c]),
                        slope_deg=float(slope[r, c]),
                    )
                )

        # Route statistics (section 7.8)
        base_gp = resolved_points[0][2]
        base_cell = resolved_points[0][1]
        slope_st, rough_st, frac_warn, max_dist, prim_cov = compute_route_statistics(
            full_path_cells=full_path_cells,
            elevation=elevation,
            slope=slope,
            roughness=roughness,
            cell_size_m=cell_size_m,
            warning_slope_deg=warning_slope_deg,
            base_geopoint=base_gp,
            path_geopoints=full_path_points if geo_referenced else None,
            base_cell=base_cell,
        )

        totals = PlannedRouteTotals(
            horizontal_distance_m=sum(leg.horizontal_distance_m for leg in planned_legs),
            surface_distance_m=sum(leg.surface_distance_m for leg in planned_legs),
            ascent_m=sum(leg.ascent_m for leg in planned_legs),
            descent_m=sum(leg.descent_m for leg in planned_legs),
            walk_time_s=sum(leg.walk_time_s for leg in planned_legs),
        )

        route_id = f"rt_{profile.value.lower()}"

        # Duplicate route detection (section 7.7)
        identical_to: str | None = None
        for earlier_rt in computed_routes:
            if earlier_rt.full_path_cells == full_path_cells:
                identical_to = earlier_rt.route_id
                break

        computed_routes.append(
            PlannedRoute(
                route_id=route_id,
                objective=profile,
                identical_to=identical_to,
                legs=planned_legs,
                path=full_path_points,
                full_path_cells=full_path_cells,
                elevation_profile=elevation_profile,
                slope_stats=slope_st,
                roughness_stats=rough_st,
                fraction_above_warning_slope=frac_warn,
                max_distance_from_base_m=max_dist,
                primary_coverage_fraction=prim_cov,
                totals=totals,
            )
        )

    return PlanOutcome(
        status=PlanStatus.OK,
        routes=computed_routes,
        omitted_objectives=omitted_objectives,
        geo_referenced=geo_referenced,
    )
