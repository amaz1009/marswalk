"""Unit tests for A* and planner deadline / timeout support (Ruling C-04 / Option A).

Verifies:
- deadline=None produces identical results to baseline on a fixed synthetic grid.
- Past deadline (deadline in the past) returns failure immediately without expanding grid.
- Partial completion: first profile finishes, subsequent profile times out using a
  controllable monkeypatched clock (not sleeps).
"""

import time

import numpy as np
import pytest

from app.engines.routing.astar import run_astar
from app.engines.routing.planner import plan_routes
from app.models.enums import PlanStatus, RouteObjective


def create_simple_grid() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Create a 20x20 flat grid fixture."""
    elev = np.zeros((20, 20), dtype=np.float32)
    slope = np.zeros((20, 20), dtype=np.float32)
    rough = np.zeros((20, 20), dtype=np.float32)
    haz = np.zeros((20, 20), dtype=np.uint8)
    return elev, slope, rough, haz


def test_deadline_none_identical_to_baseline() -> None:
    """deadline=None produces identical path, cost, and visited nodes to omitting deadline."""
    elev, slope, rough, haz = create_simple_grid()
    factors = np.ones((20, 20), dtype=np.float64)

    # Baseline call without deadline
    res_base = run_astar(
        start=(0, 0),
        goal=(10, 10),
        elevation=elev,
        hazard_states=haz,
        cell_cost_factors=factors,
        cell_size_m=5.0,
    )

    # Call with deadline=None explicitly
    res_none = run_astar(
        start=(0, 0),
        goal=(10, 10),
        elevation=elev,
        hazard_states=haz,
        cell_cost_factors=factors,
        cell_size_m=5.0,
        deadline=None,
    )

    assert res_none.success is True
    assert res_none.path == res_base.path
    assert res_none.total_cost == res_base.total_cost
    assert res_none.walk_time_s == res_base.walk_time_s
    assert res_none.visited_nodes == res_base.visited_nodes

    # Test planner level with deadline=None
    plan_base = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(0, 0),
        destination=(10, 10),
        cell_size_m=5.0,
        objectives=[RouteObjective.LOWEST_RISK],
        return_to_base=False,
    )
    plan_none = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(0, 0),
        destination=(10, 10),
        cell_size_m=5.0,
        objectives=[RouteObjective.LOWEST_RISK],
        return_to_base=False,
        deadline=None,
    )
    assert plan_none.status == plan_base.status
    assert len(plan_none.routes) == len(plan_base.routes)
    assert plan_none.routes[0].totals.walk_time_s == plan_base.routes[0].totals.walk_time_s


def test_past_deadline_returns_timeout_without_expanding_grid() -> None:
    """A deadline already in the past halts immediately with visited_nodes == 0."""
    elev, slope, rough, haz = create_simple_grid()
    factors = np.ones((20, 20), dtype=np.float64)

    # Deadline 10.0 seconds in the past
    past_deadline = time.perf_counter() - 10.0
    res = run_astar(
        start=(0, 0),
        goal=(10, 10),
        elevation=elev,
        hazard_states=haz,
        cell_cost_factors=factors,
        cell_size_m=5.0,
        deadline=past_deadline,
    )

    assert res.success is False
    assert res.visited_nodes == 0
    assert res.path == []

    # Planner level with past deadline
    plan_out = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(0, 0),
        destination=(10, 10),
        cell_size_m=5.0,
        objectives=[RouteObjective.LOWEST_RISK, RouteObjective.BALANCED],
        return_to_base=False,
        deadline=past_deadline,
    )

    assert plan_out.status == PlanStatus.NO_FEASIBLE_ROUTE
    assert len(plan_out.routes) == 0
    assert "Computation limit:" in plan_out.blocking_reason
    assert "not a terrain finding" in plan_out.blocking_reason
    assert len(plan_out.omitted_objectives) == 2
    for omitted in plan_out.omitted_objectives:
        assert omitted.reason.startswith("Computation limit:")


def test_partial_completion_with_controllable_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate timeout occurring after first profile completes using a controllable clock."""
    elev, slope, rough, haz = create_simple_grid()

    # Controllable virtual clock
    simulated_time = 100.0

    def mock_perf_counter() -> float:
        return simulated_time

    monkeypatch.setattr(time, "perf_counter", mock_perf_counter)

    # Deadline set to 150.0
    deadline = 150.0

    # Hook into plan_routes execution:
    # First profile (LOWEST_RISK) runs while simulated_time = 100.0 (< 150.0) -> completes
    # Monkeypatch precompute_cell_cost_factors so that when called for BALANCED,
    # it advances time to 160.0 (> 150.0)
    orig_precompute = plan_routes.__globals__["precompute_cell_cost_factors"]
    call_count = 0

    def time_advancing_precompute(*args, **kwargs):
        nonlocal simulated_time, call_count
        call_count += 1
        if call_count >= 2:
            # Advance clock past deadline on second profile
            simulated_time = 160.0
        return orig_precompute(*args, **kwargs)

    monkeypatch.setattr(
        "app.engines.routing.planner.precompute_cell_cost_factors",
        time_advancing_precompute,
    )

    plan_out = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(0, 0),
        destination=(10, 10),
        cell_size_m=5.0,
        objectives=[RouteObjective.LOWEST_RISK, RouteObjective.BALANCED],
        return_to_base=False,
        deadline=deadline,
    )

    # First profile finished, so plan_status is OK!
    assert plan_out.status == PlanStatus.OK
    assert len(plan_out.routes) == 1
    assert plan_out.routes[0].objective == RouteObjective.LOWEST_RISK

    # Second profile (BALANCED) is omitted under computation limit
    assert len(plan_out.omitted_objectives) == 1
    omitted = plan_out.omitted_objectives[0]
    assert omitted.objective == RouteObjective.BALANCED
    assert omitted.reason.startswith("Computation limit:")
    assert "not a terrain finding" in omitted.reason


def test_timeout_with_no_science_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout after first profile with science_interest=None preserves both omission reasons."""
    elev, slope, rough, haz = create_simple_grid()

    simulated_time = 100.0

    def mock_perf_counter() -> float:
        return simulated_time

    monkeypatch.setattr(time, "perf_counter", mock_perf_counter)
    deadline = 150.0

    orig_precompute = plan_routes.__globals__["precompute_cell_cost_factors"]
    call_count = 0

    def time_advancing_precompute(*args, **kwargs):
        nonlocal simulated_time, call_count
        call_count += 1
        if call_count >= 2:
            simulated_time = 160.0
        return orig_precompute(*args, **kwargs)

    monkeypatch.setattr(
        "app.engines.routing.planner.precompute_cell_cost_factors",
        time_advancing_precompute,
    )

    plan_out = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(0, 0),
        destination=(10, 10),
        cell_size_m=5.0,
        objectives=[
            RouteObjective.LOWEST_RISK,
            RouteObjective.BALANCED,
            RouteObjective.MAX_SCIENCE,
        ],
        science_interest=None,
        return_to_base=False,
        deadline=deadline,
    )

    assert plan_out.status == PlanStatus.OK
    assert len(plan_out.routes) == 1
    assert plan_out.routes[0].objective == RouteObjective.LOWEST_RISK

    # Exactly 2 omitted objectives: BALANCED (timeout) and MAX_SCIENCE (no layer)
    assert len(plan_out.omitted_objectives) == 2

    # BALANCED exactly once with "Computation limit:"
    balanced_omissions = [
        o for o in plan_out.omitted_objectives if o.objective == RouteObjective.BALANCED
    ]
    assert len(balanced_omissions) == 1
    assert balanced_omissions[0].reason.startswith("Computation limit:")
    assert "not a terrain finding" in balanced_omissions[0].reason

    # MAX_SCIENCE exactly once with "no science-interest layer available"
    science_omissions = [
        o for o in plan_out.omitted_objectives if o.objective == RouteObjective.MAX_SCIENCE
    ]
    assert len(science_omissions) == 1
    assert science_omissions[0].reason == "no science-interest layer available"
