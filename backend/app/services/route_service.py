"""Route planning service implementing deterministic traverse optimization.

Implements AresNav API_CONTRACTS.md §4.12 POST /api/v1/routes/plan:
- Validates region existence and point containment (422 POINT_OUTSIDE_REGION).
- Windowed terrain read with conservative 5x analysis grid aggregation.
- Ruling C-03 endpoint passability validation and snapping.
- Directional multi-profile routing with ARESNAV_ROUTE_TIMEOUT_S enforcement.
- Timeline compilation and 7-check safety assessment per route.
- Returns RoutePlanResponse with complete provenance and metrics.
"""

import math
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from app.config import get_settings
from app.core.errors import AppException
from app.engines.eva.defaults import (
    get_default_assumption_records,
    get_default_eva_config,
    resolve_eva_config,
)
from app.engines.eva.timeline import compute_eva_timeline
from app.engines.hazards.grid import HazardState
from app.engines.routing.grid import extract_analysis_grid
from app.engines.routing.planner import plan_routes
from app.engines.routing.snapping import resolve_and_snap_endpoint
from app.engines.routing.transformer import build_transformer_from_crs
from app.engines.safety.aggregate import build_safety_assessment
from app.engines.safety.checks import (
    evaluate_distance_from_base,
    evaluate_eva_duration,
    evaluate_hazard_intersection,
    evaluate_return_reserve,
    evaluate_roughness,
    evaluate_slope_max,
    evaluate_terrain_data_coverage,
)
from app.engines.safety.context import build_context_indicators
from app.models.enums import PlanStatus, RouteObjective
from app.models.eva import (
    GridInfo,
    Route,
    RouteLeg,
    RoutePlanRequest,
    RoutePlanResponse,
    RouteTotals,
)
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoBounds, GeoPoint
from app.services.region_service import get_region_raw
from app.utils.coordinates import normalize_longitude
from app.utils.geodesy import haversine_distance

ENGINE_VERSION: str = "0.2.0"
ROUTING_DATASET_IDS: tuple[str, ...] = ("HIRISE_DTM_GALE_MOUND",)
OBJECTIVE_PRIORITY_ORDER: list[RouteObjective] = [
    RouteObjective.LOWEST_RISK,
    RouteObjective.BALANCED,
    RouteObjective.MAX_SCIENCE,
]


class RouteService:
    """Service orchestrating end-to-end multi-objective traverse planning."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir

    def plan_traverse(self, request: RoutePlanRequest) -> RoutePlanResponse:
        """Execute deterministic traverse planning for requested route points."""
        start_time = time.perf_counter()
        settings = get_settings()
        timeout_s = float(settings.ARESNAV_ROUTE_TIMEOUT_S)
        deadline = start_time + timeout_s

        base_dir = self.data_dir or settings.resolved_data_dir

        # 1. Validate Region and Point Containment
        raw_region = get_region_raw(request.region_id, data_dir=base_dir)
        bounds = GeoBounds(**raw_region["bounds"])

        all_points_to_check: list[tuple[GeoPoint, str]] = [
            (request.base, "base"),
            (request.destination, "destination"),
        ]
        for idx, stop in enumerate(request.stops):
            all_points_to_check.append((stop.point, f"stop_{idx}_{stop.name}"))

        for pt, lbl in all_points_to_check:
            norm_lon = normalize_longitude(pt.lon)
            if not (
                bounds.lat_min <= pt.lat <= bounds.lat_max
                and bounds.lon_min <= norm_lon <= bounds.lon_max
            ):
                raise AppException(
                    error_code="POINT_OUTSIDE_REGION",
                    message=(
                        f"Point '{lbl}' ({pt.lat:.6f}, {norm_lon:.6f}) lies outside "
                        f"region '{request.region_id}' bounds"
                    ),
                    status_code=422,
                    details={"region_id": request.region_id, "lat": pt.lat, "lon": norm_lon},
                )

        # 2. Resolve Effective EVA Configuration
        effective_cfg = (
            resolve_eva_config(request.eva_config)
            if request.eva_config is not None
            else get_default_eva_config()
        )
        assumptions = get_default_assumption_records()

        # 3. Locate Required Processed Rasters
        processed_dir = base_dir / "processed"
        dtm_path = processed_dir / "HIRISE_DTM_GALE_MOUND.tif"
        slope_path = processed_dir / "HIRISE_SLOPE_GALE_MOUND.tif"
        rough_path = processed_dir / "HIRISE_ROUGHNESS_GALE_MOUND.tif"

        if not (dtm_path.exists() and slope_path.exists() and rough_path.exists()):
            return RoutePlanResponse(
                plan_id=f"pln_{uuid.uuid4().hex[:12]}",
                region_id=request.region_id,
                plan_status=PlanStatus.INSUFFICIENT_DATA,
                blocking_reason=(
                    "Required processed terrain rasters are unavailable for this region"
                ),
                routes=[],
                omitted_objectives=[],
                eva_config=effective_cfg,
                assumptions=assumptions,
                grid=GridInfo(analysis_crs="UNKNOWN", cell_size_m=5.0, rows=1, cols=1),
                computed_at=datetime.now(timezone.utc),
                engine_version=ENGINE_VERSION,
            )

        with (
            rasterio.open(dtm_path) as dtm_src,
            rasterio.open(slope_path) as slope_src,
            rasterio.open(rough_path) as rough_src,
        ):
            # 4. Build Spatial Reference Transformer
            crs_transformer = build_transformer_from_crs(dtm_src.crs)
            full_transform = dtm_src.transform
            full_h, full_w = dtm_src.shape

            # Project input points to full raster pixel coordinates
            def pt_to_full_pixel(p: GeoPoint) -> tuple[int, int]:
                x_p, y_p = crs_transformer.transform(p.lon, p.lat)
                inv_tf = ~full_transform
                c_f, r_f = inv_tf @ (x_p, y_p)
                return int(math.floor(r_f)), int(math.floor(c_f))

            all_input_geopoints = [request.base, request.destination] + [
                s.point for s in request.stops
            ]
            all_full_pixels = [pt_to_full_pixel(gp) for gp in all_input_geopoints]

            # 5. Extract Search Window and Aggregate to 5x Analysis Grid
            grid_res = extract_analysis_grid(
                dtm_reader=dtm_src,
                slope_reader=slope_src,
                roughness_reader=rough_src,
                points=all_full_pixels,
                max_slope_deg=effective_cfg.max_slope_deg,
                max_grid_cells=settings.ARESNAV_MAX_GRID_CELLS,
            )

            grid_info = GridInfo(
                analysis_crs=str(dtm_src.crs),
                cell_size_m=round(grid_res.cell_size_m, 4),
                rows=grid_res.h_out,
                cols=grid_res.w_out,
            )

            # Cap guard: check if analysis grid exceeded limit
            if grid_res.is_grid_too_large:
                return RoutePlanResponse(
                    plan_id=f"pln_{uuid.uuid4().hex[:12]}",
                    region_id=request.region_id,
                    plan_status=PlanStatus.NO_FEASIBLE_ROUTE,
                    blocking_reason=(
                        f"Analysis grid ({grid_res.total_cells} cells) exceeds limit of "
                        f"{settings.ARESNAV_MAX_GRID_CELLS} cells (GRID_TOO_LARGE)"
                    ),
                    routes=[],
                    omitted_objectives=[],
                    eva_config=effective_cfg,
                    assumptions=assumptions,
                    grid=grid_info,
                    computed_at=datetime.now(timezone.utc),
                    engine_version=ENGINE_VERSION,
                )

            # 6. Validate and Snap Endpoints (Ruling C-03)
            base_snap = resolve_and_snap_endpoint(
                label="base",
                point=request.base,
                full_transform=full_transform,
                win_r0=grid_res.win_r0,
                win_c0=grid_res.win_c0,
                block_factor=5,
                analysis_hazard=grid_res.hazard_states,
                native_hazard=grid_res.native_hazard_states,
                cell_size_m=grid_res.cell_size_m,
                crs_transformer=crs_transformer,
            )
            dest_snap = resolve_and_snap_endpoint(
                label="destination",
                point=request.destination,
                full_transform=full_transform,
                win_r0=grid_res.win_r0,
                win_c0=grid_res.win_c0,
                block_factor=5,
                analysis_hazard=grid_res.hazard_states,
                native_hazard=grid_res.native_hazard_states,
                cell_size_m=grid_res.cell_size_m,
                crs_transformer=crs_transformer,
            )

            stop_snaps = []
            for s_idx, stop in enumerate(request.stops):
                s_snap = resolve_and_snap_endpoint(
                    label=stop.name or f"stop_{s_idx}",
                    point=stop.point,
                    full_transform=full_transform,
                    win_r0=grid_res.win_r0,
                    win_c0=grid_res.win_c0,
                    block_factor=5,
                    analysis_hazard=grid_res.hazard_states,
                    native_hazard=grid_res.native_hazard_states,
                    cell_size_m=grid_res.cell_size_m,
                    crs_transformer=crs_transformer,
                )
                stop_snaps.append(s_snap)

            all_snaps = [base_snap, dest_snap] + stop_snaps
            for snap in all_snaps:
                if not snap.is_within_tolerance:
                    return RoutePlanResponse(
                        plan_id=f"pln_{uuid.uuid4().hex[:12]}",
                        region_id=request.region_id,
                        plan_status=PlanStatus.NO_FEASIBLE_ROUTE,
                        blocking_reason=snap.failure_reason,
                        routes=[],
                        omitted_objectives=[],
                        eva_config=effective_cfg,
                        assumptions=assumptions,
                        grid=grid_info,
                        computed_at=datetime.now(timezone.utc),
                        engine_version=ENGINE_VERSION,
                    )

            # Collect snap notices for route limitations
            snap_notices = [s.snap_message for s in all_snaps if s.is_snapped and s.snap_message]

            # 7. Order Objectives (Fixed Priority: LOWEST_RISK, BALANCED, MAX_SCIENCE)
            if request.objectives is not None:
                requested_objs = [
                    obj for obj in OBJECTIVE_PRIORITY_ORDER if obj in request.objectives
                ]
            else:
                requested_objs = list(OBJECTIVE_PRIORITY_ORDER)

            # 8. Execute Routing Engine
            stops_cells = [s.used_analysis_cell for s in stop_snaps]
            stop_labels = [s.label for s in stop_snaps]

            plan_outcome = plan_routes(
                elevation=grid_res.elevation,
                slope=grid_res.slope_max,
                roughness=grid_res.roughness_max,
                hazard_states=grid_res.hazard_states,
                base=base_snap.used_analysis_cell,
                destination=dest_snap.used_analysis_cell,
                stops=stops_cells if stops_cells else None,
                stop_labels=stop_labels if stop_labels else None,
                cell_size_m=grid_res.cell_size_m,
                transform=grid_res.analysis_transform,
                crs_transformer=crs_transformer,
                objectives=requested_objs,
                base_speed_kmh=effective_cfg.base_speed_kmh,
                max_slope_deg=effective_cfg.max_slope_deg,
                warning_slope_deg=effective_cfg.warning_slope_deg,
                roughness_warning_m=effective_cfg.roughness_warning_m,
                return_to_base=request.return_to_base,
                deadline=deadline,
            )

            # Check if planning failed
            if plan_outcome.status != PlanStatus.OK and not plan_outcome.routes:
                return RoutePlanResponse(
                    plan_id=f"pln_{uuid.uuid4().hex[:12]}",
                    region_id=request.region_id,
                    plan_status=plan_outcome.status,
                    blocking_reason=plan_outcome.blocking_reason,
                    routes=[],
                    omitted_objectives=plan_outcome.omitted_objectives,
                    eva_config=effective_cfg,
                    assumptions=assumptions,
                    grid=grid_info,
                    computed_at=datetime.now(timezone.utc),
                    engine_version=ENGINE_VERSION,
                )

            # 9. Build Routes with Timeline and Safety Assessment
            computed_routes: list[Route] = []
            context_indicators = build_context_indicators()

            for planned_r in plan_outcome.routes:
                # Build RouteLegs
                route_legs = [
                    RouteLeg(
                        from_label=leg.from_label,
                        to_label=leg.to_label,
                        path=leg.path_points,
                        horizontal_distance_m=leg.horizontal_distance_m,
                        surface_distance_m=leg.surface_distance_m,
                        ascent_m=leg.ascent_m,
                        descent_m=leg.descent_m,
                        walk_time_s=leg.walk_time_s,
                    )
                    for leg in planned_r.legs
                ]

                # Compute EVA Timeline
                timeline_entries, timeline_totals = compute_eva_timeline(
                    legs=route_legs,
                    stops=request.stops,
                    config=effective_cfg,
                    destination_work_time_min=0.0,
                )

                # Extract Path Values for Safety Evaluation
                path_slopes = [
                    float(grid_res.slope_max[rc, cc]) for (rc, cc) in planned_r.full_path_cells
                ]
                path_hazards = [
                    int(grid_res.hazard_states[rc, cc]) for (rc, cc) in planned_r.full_path_cells
                ]
                hazard_cells_crossed = sum(1 for h in path_hazards if h != HazardState.PASSABLE)
                path_roughness = [
                    float(grid_res.roughness_max[rc, cc]) for (rc, cc) in planned_r.full_path_cells
                ]
                path_elevations = [
                    float(grid_res.elevation[rc, cc]) for (rc, cc) in planned_r.full_path_cells
                ]
                valid_count = sum(1 for e in path_elevations if np.isfinite(e))
                coverage_fraction = (
                    float(valid_count / len(path_elevations)) if path_elevations else 0.0
                )

                # Distance from REQUESTED base coordinate
                max_dist_from_req_base = (
                    max(
                        haversine_distance(
                            request.base.lat,
                            request.base.lon,
                            pt.lat,
                            pt.lon,
                        )
                        for pt in planned_r.path
                    )
                    if planned_r.path
                    else 0.0
                )

                # Evaluate Seven Safety Checks
                c1 = evaluate_slope_max(
                    path_slopes=path_slopes,
                    config=effective_cfg,
                    analysis_cell_size_m=grid_res.cell_size_m,
                )
                c2 = evaluate_hazard_intersection(impassable_cells_count=hazard_cells_crossed)
                c3 = evaluate_terrain_data_coverage(
                    primary_coverage_fraction=coverage_fraction,
                    primary_dtm_post_spacing_m=float(full_transform.a),
                )
                c4 = evaluate_eva_duration(
                    total_time_s=timeline_totals.total_time_s,
                    config=effective_cfg,
                    return_to_base=request.return_to_base,
                )
                c5 = evaluate_return_reserve(
                    total_time_s=timeline_totals.total_time_s,
                    config=effective_cfg,
                    return_to_base=request.return_to_base,
                )
                c6 = evaluate_roughness(
                    path_roughness=path_roughness,
                    config=effective_cfg,
                )
                c7 = evaluate_distance_from_base(
                    max_distance_from_base_m=max_dist_from_req_base,
                    config=effective_cfg,
                )

                safety_checks = [c1, c2, c3, c4, c5, c6, c7]
                safety_assessment = build_safety_assessment(
                    checks=safety_checks,
                    context=context_indicators,
                )

                # Compose Route Limitations
                route_limitations = list(snap_notices)
                route_limitations.append(
                    f"Slope statistics evaluated using conservative block-max slope on "
                    f"{grid_res.cell_size_m:.2f} m analysis grid."
                )
                route_limitations.append(
                    "The search window can cut off detour paths around terrain obstacles; "
                    "NO_FEASIBLE_ROUTE indicates no passable route exists within the analysis "
                    "window, not that no global route exists across the wider region."
                )

                route_evidence = [
                    EvidenceRef(
                        source_type="dataset",
                        source_id="HIRISE_DTM_GALE_MOUND",
                        detail=(
                            "Primary terrain elevation and derived slope/roughness models "
                            f"(native post spacing {full_transform.a:.2f} m, "
                            f"5x analysis grid {grid_res.cell_size_m:.2f} m)"
                        ),
                    ),
                    EvidenceRef(
                        source_type="reference",
                        source_id="science_spec.section_7",
                        detail=(
                            "Deterministic A* pathfinding with 8-connectivity and "
                            "corner-cutting prohibition"
                        ),
                    ),
                ]

                totals = RouteTotals(
                    horizontal_distance_m=round(planned_r.totals.horizontal_distance_m, 2),
                    surface_distance_m=round(planned_r.totals.surface_distance_m, 2),
                    walk_time_s=round(timeline_totals.walk_time_s, 2),
                    margin_time_s=round(timeline_totals.margin_time_s, 2),
                    work_time_s=round(timeline_totals.work_time_s, 2),
                    total_time_s=round(timeline_totals.total_time_s, 2),
                    time_available_s=round(timeline_totals.time_available_s, 2),
                    reserve_required_s=round(timeline_totals.reserve_required_s, 2),
                    reserve_remaining_s=round(timeline_totals.reserve_remaining_s, 2),
                )

                computed_routes.append(
                    Route(
                        route_id=f"rte_{planned_r.objective.name.lower()}_{uuid.uuid4().hex[:8]}",
                        objective=planned_r.objective,
                        identical_to=planned_r.identical_to,
                        legs=route_legs,
                        path=planned_r.path,
                        elevation_profile=planned_r.elevation_profile,
                        slope_stats=planned_r.slope_stats,
                        roughness_stats=planned_r.roughness_stats,
                        fraction_above_warning_slope=planned_r.fraction_above_warning_slope,
                        max_distance_from_base_m=round(max_dist_from_req_base, 2),
                        timeline=timeline_entries,
                        totals=totals,
                        safety=safety_assessment,
                        primary_coverage_fraction=round(coverage_fraction, 4),
                        evidence=route_evidence,
                        limitations=route_limitations,
                    )
                )

            return RoutePlanResponse(
                plan_id=f"pln_{uuid.uuid4().hex[:12]}",
                region_id=request.region_id,
                plan_status=plan_outcome.status,
                blocking_reason=plan_outcome.blocking_reason,
                routes=computed_routes,
                omitted_objectives=plan_outcome.omitted_objectives,
                eva_config=effective_cfg,
                assumptions=assumptions,
                grid=grid_info,
                computed_at=datetime.now(timezone.utc),
                engine_version=ENGINE_VERSION,
            )


_route_service = RouteService()


def get_route_service() -> RouteService:
    """Dependency provider returning singleton RouteService."""
    return _route_service
