"""Unit tests for human walking speed model and routing engine.

Covers:
- T-EVA-01: Walking speed formula, flat speed, downhill maximum, slope at tan 15 deg.
- T-EVA-02: Step times for orthogonal, diagonal and sloped steps.
- T-ROUTE-01: Flat grid straight route distance and traversal walk time.
- T-ROUTE-02: Route avoids impassable wall and reaches destination.
- T-ROUTE-03: Enclosed start location returns NO_FEASIBLE_ROUTE naming failing leg.
- T-ROUTE-04: Start on NaN elevation cell returns INSUFFICIENT_DATA naming point.
- T-ROUTE-05: Strict corner-cutting prohibition on diagonal moves.
- T-ROUTE-06: Determinism across five identical planning runs.
- T-ROUTE-07: A* cost equals Dijkstra cost on 20 random seeded grids (heuristic admissibility).
- T-ROUTE-08: Ridge fixture: LOWEST_RISK avoids steep slope while pure-time crosses.
- T-ROUTE-09: Identical routes across profiles are flagged with identical_to.
- T-ROUTE-10: MAX_SCIENCE is omitted with explanation when science layer is absent.
- T-ROUTE-11: Search window or fallback exceeding grid cell cap returns GRID_TOO_LARGE.
- T-ROUTE-12: Asymmetric slope fixture: outbound and return leg walk times differ.
"""

import math

import numpy as np
import pytest
from rasterio.transform import Affine

from app.engines.eva.speed import (
    compute_step_time,
    walking_speed,
)
from app.engines.hazards.grid import HazardState
from app.engines.routing.astar import run_astar
from app.engines.routing.cost import (
    PROFILE_WEIGHTS,
    ObjectiveWeights,
    precompute_cell_cost_factors,
)
from app.engines.routing.planner import plan_routes
from app.models.enums import PlanStatus, RouteObjective
from app.models.geometry import GeoPoint
from app.utils.coordinates import MarsCoordinateTransformer

# ---------------------------------------------------------------------------
# T-EVA-01 & T-EVA-02: Human Walking Speed & Step Time
# ---------------------------------------------------------------------------


def test_t_eva_01_speed_function() -> None:
    """T-EVA-01: Speed function: v(0) = v0; maximum at S = -0.05; value at S = tan 15 deg."""
    base_speed = 2.7  # km/h

    # 1. Flat speed: v(0) = 2.70000000 km/h (exact)
    v_flat = walking_speed(0.0, base_speed_kmh=base_speed)
    assert math.isclose(v_flat, 2.7, rel_tol=1e-6)

    # 2. Maximum occurs at S = -0.05 (-2.86 degrees)
    # v(-0.05) = 2.7 * exp(0.175) = 3.21636478 km/h
    v_max_actual = walking_speed(-0.05, base_speed_kmh=base_speed)
    assert math.isclose(v_max_actual, 3.21636478, rel_tol=1e-6)

    # Check strictly lower on either side of S = -0.05
    assert walking_speed(-0.051, base_speed_kmh=base_speed) < v_max_actual
    assert walking_speed(-0.049, base_speed_kmh=base_speed) < v_max_actual

    # 3. Value at S = tan(15 deg) = 0.26794919...
    # Exponent = -3.5 * 0.26794919 = -0.93782217...
    # v(tan 15 deg) = 2.7 * exp(-0.93782217) = 1.05699460 km/h
    s_15 = math.tan(math.radians(15.0))
    v_15_actual = walking_speed(s_15, base_speed_kmh=base_speed)
    assert math.isclose(v_15_actual, 1.05699460, rel_tol=1e-6)

    # 4. Vectorized input support
    grads = np.array([0.0, -0.05, s_15], dtype=np.float64)
    v_vec = walking_speed(grads, base_speed_kmh=base_speed)
    assert isinstance(v_vec, np.ndarray)
    assert np.allclose(v_vec, [2.7, 3.21636478, 1.05699460], rtol=1e-6)


def test_t_eva_02_step_times() -> None:
    """T-EVA-02: Step time for known orthogonal and diagonal steps."""
    base_speed = 2.7  # km/h = 0.75 m/s

    # 1. Orthogonal flat step: dh = 1.0 m, dz = 0.0 m
    # t = 1.0 / 0.75 = 1.33333333 s (4/3 s)
    t_ortho = compute_step_time(delta_z=0.0, delta_d_h=1.0, base_speed_kmh=base_speed)
    assert math.isclose(t_ortho, 1.33333333, rel_tol=1e-6)

    # 2. Diagonal flat step: dh = sqrt(2) m, dz = 0.0 m
    # t = sqrt(2) / 0.75 = 1.88561808 s
    t_diag = compute_step_time(delta_z=0.0, delta_d_h=math.sqrt(2.0), base_speed_kmh=base_speed)
    assert math.isclose(t_diag, 1.88561808, rel_tol=1e-6)

    # 3. Sloped step: dh = 1.0 m, dz = 0.1 m (S = 0.1)
    # ds = sqrt(1.01) = 1.00498756 m
    # v = 0.75 * exp(-0.35) = 0.52850937 m/s
    # t = ds / v = 1.90152698 s
    t_sloped_actual = compute_step_time(delta_z=0.1, delta_d_h=1.0, base_speed_kmh=base_speed)
    assert math.isclose(t_sloped_actual, 1.90152698, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# T-ROUTE-01 to T-ROUTE-12: Routing Engine Core Tests
# ---------------------------------------------------------------------------


def test_t_route_01_flat_grid_straight_route() -> None:
    """T-ROUTE-01: On a flat grid, a straight route has the expected distance and walk time."""
    rows, cols = 10, 10
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(5, 2),
        destination=(5, 8),
        cell_size_m=1.0,
        base_speed_kmh=2.7,
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    assert len(outcome.routes) >= 1

    route = outcome.routes[0]
    expected_path = [(5, 2), (5, 3), (5, 4), (5, 5), (5, 6), (5, 7), (5, 8)]
    assert route.full_path_cells == expected_path

    # 6 steps * 1.0 m = 6.0 m
    assert math.isclose(route.totals.horizontal_distance_m, 6.0, rel_tol=1e-6)
    assert math.isclose(route.totals.surface_distance_m, 6.0, rel_tol=1e-6)
    # 6.0 m / 0.75 m/s = 8.0 s
    assert math.isclose(route.totals.walk_time_s, 8.0, rel_tol=1e-6)


def test_t_route_02_wall_avoidance() -> None:
    """T-ROUTE-02: A route goes around a wall of impassable cells and never crosses one."""
    rows, cols = 12, 12
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Vertical wall at col 5 from row 0 to 8
    hazards[0:9, 5] = HazardState.IMPASSABLE_SLOPE

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(4, 2),
        destination=(4, 8),
        cell_size_m=1.0,
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    route = outcome.routes[0]
    assert len(route.full_path_cells) > 0

    # Ensure no cell on the path is impassable
    for r, c in route.full_path_cells:
        assert hazards[r, c] == HazardState.PASSABLE
        assert not (c == 5 and r < 9)


def test_t_route_03_enclosed_start_no_feasible_route() -> None:
    """T-ROUTE-03: An enclosed start returns NO_FEASIBLE_ROUTE naming the failing leg."""
    rows, cols = 15, 15
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Completely surround start (7, 7) with impassable wall
    for r in range(6, 9):
        for c in range(6, 9):
            if (r, c) != (7, 7):
                hazards[r, c] = HazardState.IMPASSABLE_SLOPE

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(7, 7),
        destination=(0, 0),
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.NO_FEASIBLE_ROUTE
    assert outcome.blocking_leg is not None
    assert "base" in outcome.blocking_leg or "destination" in outcome.blocking_leg
    assert outcome.blocking_reason is not None
    assert "base -> destination" in outcome.blocking_reason


def test_t_route_04_nan_cell_insufficient_data() -> None:
    """T-ROUTE-04: A start on a NaN cell returns INSUFFICIENT_DATA naming the point."""
    rows, cols = 10, 10
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Mark base cell as missing data
    elevation[3, 3] = np.nan
    hazards[3, 3] = HazardState.IMPASSABLE_NODATA

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(3, 3),
        destination=(7, 7),
        base_label="habitat_base",
    )

    assert outcome.status == PlanStatus.INSUFFICIENT_DATA
    assert outcome.blocking_point == "habitat_base"
    assert "habitat_base" in outcome.blocking_reason


def test_t_route_05_no_diagonal_corner_cutting() -> None:
    """T-ROUTE-05: No diagonal move passes between two impassable orthogonal cells."""
    rows, cols = 5, 5
    elevation = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Start at (1, 1), Goal at (2, 2)
    # Block orthogonal neighbour (1, 2)
    hazards[1, 2] = HazardState.IMPASSABLE_SLOPE

    factors = np.ones((rows, cols), dtype=np.float64)
    res = run_astar(
        start=(1, 1),
        goal=(2, 2),
        elevation=elevation,
        hazard_states=hazards,
        cell_cost_factors=factors,
        cell_size_m=1.0,
    )

    assert res.success
    # The direct diagonal step (1, 1) -> (2, 2) must NOT be taken because (1, 2) is blocked
    for i in range(len(res.path) - 1):
        step = (res.path[i], res.path[i + 1])
        assert step != ((1, 1), (2, 2))

    # Path must route via the open orthogonal cell (2, 1)
    assert res.path == [(1, 1), (2, 1), (2, 2)]

    # If both orthogonal neighbours (1, 2) and (2, 1) are impassable, and surrounded:
    hazards[2, 1] = HazardState.IMPASSABLE_SLOPE
    # Block other exits to force check
    hazards[0, :] = HazardState.IMPASSABLE_SLOPE
    hazards[:, 0] = HazardState.IMPASSABLE_SLOPE
    hazards[1, 0] = HazardState.IMPASSABLE_SLOPE
    hazards[2, 0] = HazardState.IMPASSABLE_SLOPE

    res_blocked = run_astar(
        start=(1, 1),
        goal=(2, 2),
        elevation=elevation,
        hazard_states=hazards,
        cell_cost_factors=factors,
        cell_size_m=1.0,
    )
    # Cannot squeeze diagonally through the blocked corner!
    assert not res_blocked.success


def test_t_route_06_determinism_five_runs() -> None:
    """T-ROUTE-06: Five identical runs produce identical paths and costs."""
    rng = np.random.default_rng(12345)
    rows, cols = 30, 30
    elevation = rng.uniform(0.0, 50.0, size=(rows, cols))
    slope = rng.uniform(0.0, 12.0, size=(rows, cols))
    roughness = rng.uniform(0.0, 0.15, size=(rows, cols))
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Some obstacles
    hazards[rng.uniform(0, 1, size=(rows, cols)) < 0.15] = HazardState.IMPASSABLE_SLOPE
    hazards[2, 2] = HazardState.PASSABLE
    hazards[27, 27] = HazardState.PASSABLE

    results = []
    for _ in range(5):
        outcome = plan_routes(
            elevation=elevation,
            slope=slope,
            roughness=roughness,
            hazard_states=hazards,
            base=(2, 2),
            destination=(27, 27),
            cell_size_m=1.0,
            return_to_base=False,
        )
        assert outcome.status == PlanStatus.OK
        results.append(outcome.routes[0])

    # Assert exact bitwise reproducibility across all 5 runs
    base_cells = results[0].full_path_cells
    base_dist = results[0].totals.horizontal_distance_m
    base_time = results[0].totals.walk_time_s

    for r in results[1:]:
        assert r.full_path_cells == base_cells
        assert r.totals.horizontal_distance_m == base_dist
        assert r.totals.walk_time_s == base_time


def test_t_route_07_astar_vs_dijkstra_admissibility_20_seeds() -> None:
    """T-ROUTE-07: A* cost equals Dijkstra cost on 20 random seeded grids."""
    for seed in range(1, 21):
        rng = np.random.default_rng(seed)
        rows, cols = 20, 20
        elevation = rng.uniform(-10.0, 10.0, size=(rows, cols))
        slope = rng.uniform(0.0, 10.0, size=(rows, cols))
        roughness = rng.uniform(0.0, 0.1, size=(rows, cols))
        hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

        # 10% obstacles
        mask = rng.uniform(0.0, 1.0, size=(rows, cols)) < 0.10
        hazards[mask] = HazardState.IMPASSABLE_SLOPE

        start = (2, 2)
        goal = (17, 17)
        hazards[start] = HazardState.PASSABLE
        hazards[goal] = HazardState.PASSABLE

        weights = ObjectiveWeights(w_s=2.0, w_r=1.5, w_h=1.0, w_sci=0.0)
        cell_factors = precompute_cell_cost_factors(
            slope_deg=slope,
            roughness_m=roughness,
            hazard_states=hazards,
            weights=weights,
            max_slope_deg=15.0,
            roughness_warning_m=0.30,
        )

        res_astar = run_astar(
            start=start,
            goal=goal,
            elevation=elevation,
            hazard_states=hazards,
            cell_cost_factors=cell_factors,
            cell_size_m=1.0,
            base_speed_kmh=2.7,
            w_sci=weights.w_sci,
            use_heuristic=True,
        )

        res_dijkstra = run_astar(
            start=start,
            goal=goal,
            elevation=elevation,
            hazard_states=hazards,
            cell_cost_factors=cell_factors,
            cell_size_m=1.0,
            base_speed_kmh=2.7,
            w_sci=weights.w_sci,
            use_heuristic=False,
        )

        assert res_astar.success == res_dijkstra.success
        if res_astar.success:
            # Optimal cost must match within float precision
            assert math.isclose(res_astar.total_cost, res_dijkstra.total_cost, rel_tol=1e-8)
            # A* must not expand more nodes than Dijkstra
            assert res_astar.visited_nodes <= res_dijkstra.visited_nodes


def test_t_route_08_ridge_fixture_lowest_risk_avoids_steep() -> None:
    """T-ROUTE-08: On the ridge fixture, LOWEST_RISK avoids steep slope while pure-time crosses."""
    rows, cols = 15, 15
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Place a steep ridge in the middle: cols 6..8, rows 3..14
    # with slope 14.0 deg (near max 15.0 deg)
    slope[3:15, 6:9] = 14.0

    # Start at (7, 2), Destination at (7, 12)
    # Direct straight-line path passes through the 14 deg ridge.
    # An open flat detour exists via rows 0..2 where slope is 0.0 deg.

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(7, 2),
        destination=(7, 12),
        objectives=[RouteObjective.LOWEST_RISK],
        cell_size_m=1.0,
        max_slope_deg=15.0,
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    route_risk = outcome.routes[0]

    # LOWEST_RISK should take the detour through rows 0..2 to avoid the 14 deg ridge
    max_slope_risk = route_risk.slope_stats.max
    assert max_slope_risk is not None
    assert max_slope_risk < 14.0
    for r, c in route_risk.full_path_cells:
        assert slope[r, c] < 14.0


def test_t_route_09_duplicate_routes_identical_to() -> None:
    """T-ROUTE-09: Identical paths across profiles are flagged with identical_to."""
    rows, cols = 10, 10
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(2, 2),
        destination=(8, 8),
        objectives=[RouteObjective.LOWEST_RISK, RouteObjective.BALANCED],
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    assert len(outcome.routes) == 2

    r1, r2 = outcome.routes[0], outcome.routes[1]
    # On flat terrain both find the straight diagonal path
    assert r1.full_path_cells == r2.full_path_cells
    assert r1.identical_to is None
    assert r2.identical_to == r1.route_id


def test_t_route_10_max_science_omission() -> None:
    """T-ROUTE-10: MAX_SCIENCE is omitted with a reason when no science-interest layer exists."""
    rows, cols = 10, 10
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(1, 1),
        destination=(5, 5),
        science_interest=None,  # No science layer
        objectives=[
            RouteObjective.LOWEST_RISK,
            RouteObjective.BALANCED,
            RouteObjective.MAX_SCIENCE,
        ],
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    assert len(outcome.routes) == 2
    assert [r.objective for r in outcome.routes] == [
        RouteObjective.LOWEST_RISK,
        RouteObjective.BALANCED,
    ]

    assert len(outcome.omitted_objectives) == 1
    omitted = outcome.omitted_objectives[0]
    assert omitted.objective == RouteObjective.MAX_SCIENCE
    assert omitted.reason == "no science-interest layer available"


def test_t_route_11_grid_too_large_cap() -> None:
    """T-ROUTE-11: A search area above the cell cap returns GRID_TOO_LARGE."""
    rows, cols = 100, 100  # 10,000 cells
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Set cell cap to 500 cells (search window will exceed this)
    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(10, 10),
        destination=(80, 80),
        cell_size_m=1.0,
        max_grid_cells=500,
    )

    assert outcome.status == PlanStatus.NO_FEASIBLE_ROUTE
    assert outcome.is_grid_too_large
    assert "GRID_TOO_LARGE" in outcome.blocking_reason


def test_t_route_12_asymmetric_slope_outbound_return_times() -> None:
    """T-ROUTE-12: On the asymmetric-slope fixture, outbound and return walk times differ."""
    rows, cols = 20, 5
    # Linear ramp: row 0 is 0 m, row 10 is 50 m
    # Elevation gradient is +5 m per cell in row direction
    r_coords = np.arange(rows, dtype=np.float64)
    elevation = np.repeat(r_coords[:, np.newaxis] * 5.0, cols, axis=1)
    slope = np.full((rows, cols), 5.0, dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(2, 2),
        destination=(8, 2),
        cell_size_m=10.0,
        base_speed_kmh=2.7,
        objectives=[RouteObjective.BALANCED],
        return_to_base=True,
    )

    assert outcome.status == PlanStatus.OK
    route = outcome.routes[0]
    assert len(route.legs) == 2

    outbound_leg = route.legs[0]
    return_leg = route.legs[1]

    # Outbound leg is uphill across 6 diagonal switchback steps.
    # Diagonal steps are preferred by A* on the linear ramp because dh = 10*sqrt(2) m
    # flattens the gradient from S = 5/10 = 0.50 to S = 5/(10*sqrt(2)) = 0.35355339.
    # Across 6 diagonal steps:
    # dh_total = 6 * 10 * sqrt(2) = 60 * sqrt(2) = 84.85281374 m
    # ds_total = 6 * sqrt((10*sqrt(2))^2 + 5^2) = 6 * sqrt(225) = 90.0 m
    # v_out = 0.75 * exp(-3.5 * (sqrt(2)/4)) = 0.21759509 m/s
    # t_out = 6 * (15.0 / (0.75 * exp(-3.5 * sqrt(2)/4))) = 413.61211314 s
    assert math.isclose(outbound_leg.horizontal_distance_m, 84.85281374, rel_tol=1e-6)
    assert math.isclose(outbound_leg.surface_distance_m, 90.0, rel_tol=1e-6)
    assert math.isclose(outbound_leg.ascent_m, 30.0, rel_tol=1e-6)
    assert math.isclose(outbound_leg.descent_m, 0.0, abs_tol=1e-6)
    assert math.isclose(outbound_leg.walk_time_s, 413.61211314, rel_tol=1e-6)

    # Return leg is downhill across 6 diagonal switchback steps.
    # dh_total = 84.85281374 m, ds_total = 90.0 m
    # S = -5 / (10*sqrt(2)) = -0.35355339
    # Exponent = -3.5 * (|S + 0.05| - 0.05) = -3.5 * (0.35355339 - 0.10) = -0.88743687
    # v_ret = 0.75 * exp(-0.88743687) = 0.30878199 m/s
    # t_ret = 6 * (15.0 / (0.75 * exp(-0.88743687))) = 291.46752989 s
    assert math.isclose(return_leg.horizontal_distance_m, 84.85281374, rel_tol=1e-6)
    assert math.isclose(return_leg.surface_distance_m, 90.0, rel_tol=1e-6)
    assert math.isclose(return_leg.ascent_m, 0.0, abs_tol=1e-6)
    assert math.isclose(return_leg.descent_m, 30.0, rel_tol=1e-6)
    assert math.isclose(return_leg.walk_time_s, 291.46752989, rel_tol=1e-6)

    # Outbound uphill takes strictly longer than return downhill
    assert outbound_leg.walk_time_s > return_leg.walk_time_s

    # Route totals (outbound 413.61211314 s + return 291.46752989 s = 705.07964303 s)
    assert math.isclose(route.totals.walk_time_s, 705.07964303, rel_tol=1e-6)

    # Human walking speed uphill is slower than downhill (at moderate slopes)
    # Therefore outbound leg traversal time must be strictly longer than return leg
    assert outbound_leg.walk_time_s > return_leg.walk_time_s


def test_slope_penalty_scaling_with_max_slope() -> None:
    """The slope penalty term scales quadratically with max_slope_deg.

    Hand Derivation:
        Cell properties:
            slope = 10.0 degrees
            roughness = 0.0 m (rho = 0.0)
            hazard = PASSABLE (0)
            near_hazard = False (eta = 0.0)
            science_interest = None (iota = 0.0)
        BALANCED profile weights:
            w_s = 1.0, w_r = 1.0, w_h = 1.0, w_sci = 0.25 (unused since iota = 0)
        Formula:
            penalty = 1.0 + w_s * (slope / max_slope_deg)^2 + w_r * rho + w_h * eta
            factor = penalty * (1.0 - w_sci * iota)
                   = 1.0 + 1.0 * (10.0 / max_slope_deg)^2

        Case 1: max_slope_deg = 15.0
            (10.0 / 15.0)^2 = (2/3)^2 = 4/9 = 0.44444444...
            factor_15 = 1.0 + 4/9 = 13/9 = 1.44444444...

        Case 2: max_slope_deg = 20.0
            (10.0 / 20.0)^2 = (1/2)^2 = 1/4 = 0.25
            factor_20 = 1.0 + 0.25 = 1.25000000...
    """
    slope = np.array([[10.0]], dtype=np.float64)
    roughness = np.array([[0.0]], dtype=np.float64)
    hazards = np.array([[HazardState.PASSABLE]], dtype=np.uint8)
    weights = PROFILE_WEIGHTS[RouteObjective.BALANCED]

    factors_15 = precompute_cell_cost_factors(
        slope_deg=slope,
        roughness_m=roughness,
        hazard_states=hazards,
        weights=weights,
        max_slope_deg=15.0,
        roughness_warning_m=0.30,
    )
    assert math.isclose(float(factors_15[0, 0]), 13.0 / 9.0, rel_tol=1e-9)

    factors_20 = precompute_cell_cost_factors(
        slope_deg=slope,
        roughness_m=roughness,
        hazard_states=hazards,
        weights=weights,
        max_slope_deg=20.0,
        roughness_warning_m=0.30,
    )
    assert math.isclose(float(factors_20[0, 0]), 1.25, rel_tol=1e-9)


def test_nan_roughness_on_passable_cell_routed_around() -> None:
    """Passable cell with NaN roughness is treated as IMPASSABLE_NODATA and routed around.

    Caller arrays must remain completely unmodified.
    """
    rows, cols = 7, 7
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.full((rows, cols), 0.05, dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Place NaN roughness directly on the straight-line path between (3, 1) and (3, 5)
    # Crucially, hazards array marks it PASSABLE!
    roughness[3, 3] = np.nan
    assert hazards[3, 3] == HazardState.PASSABLE

    # Snapshot caller arrays
    elev_orig = elevation.copy()
    slope_orig = slope.copy()
    rough_orig = roughness.copy()
    haz_orig = hazards.copy()

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(3, 1),
        destination=(3, 5),
        cell_size_m=1.0,
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    route = outcome.routes[0]
    path_cells = route.full_path_cells

    # The path must successfully reach destination
    assert path_cells[0] == (3, 1)
    assert path_cells[-1] == (3, 5)

    # The NaN roughness cell (3, 3) must NOT be stepped on
    assert (3, 3) not in path_cells

    # Caller arrays must be bitwise identical (no mutation)
    assert np.array_equal(elevation, elev_orig, equal_nan=True)
    assert np.array_equal(slope, slope_orig, equal_nan=True)
    assert np.array_equal(roughness, rough_orig, equal_nan=True)
    assert np.array_equal(hazards, haz_orig)


def test_nan_roughness_on_route_point_returns_insufficient_data() -> None:
    """Route point on a cell with NaN roughness returns INSUFFICIENT_DATA naming the point.

    Caller arrays must remain completely unmodified.
    """
    rows, cols = 5, 5
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Destination cell has NaN roughness while hazard states says PASSABLE
    roughness[4, 4] = np.nan
    assert hazards[4, 4] == HazardState.PASSABLE

    # Snapshot caller arrays
    elev_orig = elevation.copy()
    slope_orig = slope.copy()
    rough_orig = roughness.copy()
    haz_orig = hazards.copy()

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(1, 1),
        destination=(4, 4),
        destination_label="sample_target_alpha",
    )

    assert outcome.status == PlanStatus.INSUFFICIENT_DATA
    assert outcome.blocking_point == "sample_target_alpha"
    assert "sample_target_alpha" in outcome.blocking_reason
    assert "IMPASSABLE_NODATA" in outcome.blocking_reason

    # Caller arrays must remain untouched
    assert np.array_equal(elevation, elev_orig, equal_nan=True)
    assert np.array_equal(slope, slope_orig, equal_nan=True)
    assert np.array_equal(roughness, rough_orig, equal_nan=True)
    assert np.array_equal(hazards, haz_orig)


def test_nan_slope_and_elevation_guard() -> None:
    """Passable cells with NaN slope or NaN elevation are treated as IMPASSABLE_NODATA.

    Route points on such cells return INSUFFICIENT_DATA naming the point.
    """
    rows, cols = 7, 7
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # Place NaN slope at (3, 3)
    slope[3, 3] = np.nan

    outcome = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(3, 1),
        destination=(3, 5),
        cell_size_m=1.0,
        return_to_base=False,
    )

    assert outcome.status == PlanStatus.OK
    route = outcome.routes[0]
    assert (3, 3) not in route.full_path_cells

    # Place NaN slope on base point
    outcome_base_nan = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(3, 3),
        destination=(3, 5),
        base_label="hab_start",
    )
    assert outcome_base_nan.status == PlanStatus.INSUFFICIENT_DATA
    assert outcome_base_nan.blocking_point == "hab_start"


def test_spatial_reference_mismatch_raises_value_error() -> None:
    """Providing transform without crs_transformer or vice-versa raises ValueError."""
    rows, cols = 5, 5
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    sample_transform = Affine.translation(100.0, -200.0)
    sample_transformer = MarsCoordinateTransformer(center_lat=0.0, center_lon=137.3)

    # 1. Transform provided without crs_transformer
    with pytest.raises(ValueError, match="Both 'transform' and 'crs_transformer' must be provided"):
        plan_routes(
            elevation=elevation,
            slope=slope,
            roughness=roughness,
            hazard_states=hazards,
            base=(1, 1),
            destination=(3, 3),
            transform=sample_transform,
            crs_transformer=None,
        )

    # 2. crs_transformer provided without transform
    with pytest.raises(ValueError, match="Both 'transform' and 'crs_transformer' must be provided"):
        plan_routes(
            elevation=elevation,
            slope=slope,
            roughness=roughness,
            hazard_states=hazards,
            base=(1, 1),
            destination=(3, 3),
            transform=None,
            crs_transformer=sample_transformer,
        )


def test_geopoint_input_without_spatial_ref_raises_value_error() -> None:
    """Passing GeoPoint inputs without both transform and crs_transformer raises ValueError."""
    rows, cols = 5, 5
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    base_gp = GeoPoint(lat=-4.78, lon=137.30)
    dest_gp = GeoPoint(lat=-4.79, lon=137.31)

    with pytest.raises(ValueError, match="Cannot resolve GeoPoint"):
        plan_routes(
            elevation=elevation,
            slope=slope,
            roughness=roughness,
            hazard_states=hazards,
            base=base_gp,
            destination=dest_gp,
            transform=None,
            crs_transformer=None,
        )


def test_grid_only_and_georeferenced_modes() -> None:
    """Grid-only mode produces geo_referenced=False with empty geo points; full mode sets True."""
    rows, cols = 8, 8
    elevation = np.zeros((rows, cols), dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    roughness = np.zeros((rows, cols), dtype=np.float64)
    hazards = np.full((rows, cols), HazardState.PASSABLE, dtype=np.uint8)

    # 1. Grid-only mode (synthetic grid without transform / crs_transformer)
    outcome_grid = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(1, 1),
        destination=(5, 5),
        cell_size_m=2.0,
        return_to_base=False,
    )
    assert outcome_grid.status == PlanStatus.OK
    assert outcome_grid.geo_referenced is False

    route_g = outcome_grid.routes[0]
    # In grid-only mode, geographic coordinates are not invented
    assert len(route_g.path) == 0
    assert len(route_g.legs[0].path_points) == 0
    assert len(route_g.elevation_profile) == 0
    # max_distance_from_base_m is computed from Euclidean grid distance * cell_size_m
    # Start at (1, 1), End at (5, 5): offset = hypot(4, 4) * 2.0 = 4 * sqrt(2) * 2.0
    expected_max_dist = math.hypot(4.0, 4.0) * 2.0
    assert math.isclose(route_g.max_distance_from_base_m, expected_max_dist, rel_tol=1e-6)

    # 2. Spatially referenced mode (both transform and crs_transformer provided)
    transform = Affine.translation(0.0, -280000.0) @ Affine.scale(1.0, -1.0)
    crs_transformer = MarsCoordinateTransformer(center_lat=0.0, center_lon=137.3)

    outcome_geo = plan_routes(
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        hazard_states=hazards,
        base=(1, 1),
        destination=(5, 5),
        cell_size_m=1.0,
        transform=transform,
        crs_transformer=crs_transformer,
        return_to_base=False,
    )
    assert outcome_geo.status == PlanStatus.OK
    assert outcome_geo.geo_referenced is True

    route_geo = outcome_geo.routes[0]
    assert len(route_geo.path) == len(route_geo.full_path_cells)
    assert len(route_geo.legs[0].path_points) == len(route_geo.legs[0].path_cells)
    assert len(route_geo.elevation_profile) == len(route_geo.full_path_cells)
    # Coordinates in path are real GeoPoints
    assert isinstance(route_geo.path[0], GeoPoint)
    assert route_geo.max_distance_from_base_m > 0.0
