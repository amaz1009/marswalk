"""Unit and integration tests for Route Planning and EVA APIs (T-API-06, T-API-07, T-EVA-04).

Implements requirements from docs/TESTING_STRATEGY.md and WP-11 card:
- GET /api/v1/eva/defaults returns 200 with complete configuration and assumption records.
- POST /api/v1/routes/plan with POINT_OUTSIDE_REGION returns 422 error envelope (T-API-07).
- POST /api/v1/routes/plan on real Gale Crater data returns 200 with valid RoutePlanResponse,
  conservative 5x analysis grid, endpoint snapping reported in limitations, complete metrics,
  timeline, and 7-check safety assessment (T-API-06).
- Determinism: identical request produces identical routes and metrics.
- Objective filtering: requesting only [LOWEST_RISK] returns only that profile.
- Omitted objective: MAX_SCIENCE is omitted when no science-interest layer is present.
- Timeout path: monkeypatched clock returns partial completion with "Computation limit:".
- Real-data tests skip cleanly when processed rasters are absent.
"""

import math
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.enums import AssessmentStatus, DataClass, PlanStatus, RouteObjective
from app.models.eva import EvaDefaultsResponse, RoutePlanResponse

client = TestClient(app)

PROCESSED_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
REAL_DATA_EXISTS = (
    (PROCESSED_DATA_DIR / "HIRISE_DTM_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_SLOPE_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_ROUGHNESS_GALE_MOUND.tif").exists()
)


# ---------------------------------------------------------------------------
# 1. EVA Defaults API (T-EVA-04 at API Level)
# ---------------------------------------------------------------------------


def test_get_eva_defaults_success() -> None:
    """GET /api/v1/eva/defaults returns 200 with complete config and assumption records."""
    response = client.get("/api/v1/eva/defaults")
    assert response.status_code == 200
    data = response.json()

    # Validate against frozen Pydantic model
    parsed = EvaDefaultsResponse.model_validate(data)
    assert parsed.config.base_speed_kmh == 2.7
    assert parsed.config.max_slope_deg == 15.0
    assert parsed.config.warning_slope_deg == 10.0
    assert parsed.config.max_eva_hours == 6.0
    assert parsed.config.return_reserve_fraction == 0.25
    assert parsed.config.traverse_time_margin == 1.25
    assert parsed.config.default_work_time_min == 20.0
    assert parsed.config.max_distance_from_base_m == 2000.0
    assert parsed.config.roughness_warning_m == 0.30

    # Verify all 9 assumptions are populated per spec section 6.2
    assert len(parsed.assumptions) == 9
    expected_keys = {
        "base_speed_kmh",
        "max_slope_deg",
        "warning_slope_deg",
        "max_eva_hours",
        "return_reserve_fraction",
        "traverse_time_margin",
        "default_work_time_min",
        "max_distance_from_base_m",
        "roughness_warning_m",
    }
    record_map = {a.key: a for a in parsed.assumptions}
    assert set(record_map.keys()) == expected_keys

    # Assert data_class labels match spec section 6.2 (4 REFERENCE, 5 ASSUMPTION)
    expected_reference_keys = {
        "base_speed_kmh",
        "max_slope_deg",
        "warning_slope_deg",
        "max_distance_from_base_m",
    }
    expected_assumption_keys = {
        "max_eva_hours",
        "return_reserve_fraction",
        "traverse_time_margin",
        "default_work_time_min",
        "roughness_warning_m",
    }
    for k in expected_reference_keys:
        assert record_map[k].data_class == DataClass.REFERENCE
    for k in expected_assumption_keys:
        assert record_map[k].data_class == DataClass.ASSUMPTION

    # Assert each record's value equals the corresponding parsed.config field
    for k, record in record_map.items():
        assert record.value == getattr(parsed.config, k)


# ---------------------------------------------------------------------------
# 2. Point Outside Region Error Envelope (T-API-07)
# ---------------------------------------------------------------------------


def test_plan_routes_point_outside_region_returns_422() -> None:
    """POST /api/v1/routes/plan with coordinates outside region returns 422 POINT_OUTSIDE_REGION."""
    payload = {
        "region_id": "gale_mount_sharp",
        "base": {"lat": 0.0, "lon": 0.0},  # Outside Gale Crater bounds
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "return_to_base": True,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "POINT_OUTSIDE_REGION"
    assert "message" in data
    assert "request_id" in data
    assert data["request_id"].startswith("req_")


def test_plan_routes_unknown_region_returns_404() -> None:
    """POST /api/v1/routes/plan with nonexistent region_id returns 404 REGION_NOT_FOUND."""
    payload = {
        "region_id": "nonexistent_region",
        "base": {"lat": -4.75, "lon": 137.28},
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "return_to_base": True,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "REGION_NOT_FOUND"
    assert "message" in data
    assert "request_id" in data
    assert data["request_id"].startswith("req_")


# ---------------------------------------------------------------------------
# 3. Real Gale Crater Route Planning (T-API-06)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_plan_routes_real_gale_sample_success() -> None:
    """T-API-06: Plan traverse on real Gale Mount Sharp rasters with endpoint snapping.

    Request:
      Base: -4.75, 137.28
      Destination: -4.78, 137.30
      Stops: None
      Return to base: True
    """
    payload = {
        "region_id": "gale_mount_sharp",
        "base": {"lat": -4.75, "lon": 137.28},
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "return_to_base": True,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    data = response.json()

    plan = RoutePlanResponse.model_validate(data)
    assert plan.plan_status == PlanStatus.OK
    assert plan.plan_id.startswith("pln_")
    assert plan.region_id == "gale_mount_sharp"
    assert plan.engine_version == "0.2.0"

    # Grid structure
    assert plan.grid.rows > 0
    assert plan.grid.cols > 0
    assert plan.grid.cell_size_m > 0.0

    # MAX_SCIENCE omitted because no science interest layer
    assert len(plan.omitted_objectives) >= 1
    omitted_max_sci = next(
        (o for o in plan.omitted_objectives if o.objective == RouteObjective.MAX_SCIENCE), None
    )
    assert omitted_max_sci is not None
    assert "no science-interest" in omitted_max_sci.reason

    # Two routes computed: LOWEST_RISK and BALANCED
    assert len(plan.routes) == 2
    lr_route = next(r for r in plan.routes if r.objective == RouteObjective.LOWEST_RISK)
    bal_route = next(r for r in plan.routes if r.objective == RouteObjective.BALANCED)

    # Snapping verified: destination snap sentence reported in EVERY route's limitations
    for route in [lr_route, bal_route]:
        snap_lim = next((lim for lim in route.limitations if "snapped" in lim.lower()), None)
        assert snap_lim is not None
        assert "Endpoint 'destination' snapped" in snap_lim
        assert "due to localized obstacle in 5x5 analysis cell" in snap_lim

        # Window limitation present
        win_lim = next((lim for lim in route.limitations if "analysis window" in lim.lower()), None)
        assert win_lim is not None

        # Legs verified
        assert len(route.legs) == 2  # Outbound and Return
        assert route.totals.walk_time_s > 0.0
        assert route.totals.horizontal_distance_m > 0.0

        # Timeline arithmetic invariant: total = walk + margin + work
        expected_total = (
            route.totals.walk_time_s + route.totals.margin_time_s + route.totals.work_time_s
        )
        assert math.isclose(route.totals.total_time_s, expected_total, abs_tol=0.05)

        # Safety Assessment: all 7 checks present
        assert len(route.safety.checks) == 7
        assert route.safety.overall_status in (AssessmentStatus.PASS, AssessmentStatus.WARNING)
        assert route.safety.disclaimer.startswith("AresNav is a research and planning prototype")


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_plan_routes_determinism() -> None:
    """Determinism check: Identical inputs produce identical routes, metrics, and safety checks."""
    payload = {
        "region_id": "gale_mount_sharp",
        "base": {"lat": -4.75, "lon": 137.28},
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "objectives": ["LOWEST_RISK"],
        "return_to_base": True,
    }
    r1 = client.post("/api/v1/routes/plan", json=payload).json()
    r2 = client.post("/api/v1/routes/plan", json=payload).json()

    p1 = RoutePlanResponse.model_validate(r1)
    p2 = RoutePlanResponse.model_validate(r2)

    # Exclude dynamic run fields plan_id and computed_at
    assert p1.plan_status == p2.plan_status
    assert len(p1.routes) == len(p2.routes) == 1
    rt1, rt2 = p1.routes[0], p2.routes[0]

    assert rt1.totals == rt2.totals
    assert rt1.path == rt2.path
    assert rt1.slope_stats == rt2.slope_stats
    assert rt1.safety.overall_status == rt2.safety.overall_status
    assert [c.status for c in rt1.safety.checks] == [c.status for c in rt2.safety.checks]
    assert [c.value for c in rt1.safety.checks] == [c.value for c in rt2.safety.checks]


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_plan_routes_objective_filtering() -> None:
    """Requesting only [LOWEST_RISK] returns only that profile and no others."""
    payload = {
        "region_id": "gale_mount_sharp",
        "base": {"lat": -4.75, "lon": 137.28},
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "objectives": ["LOWEST_RISK"],
        "return_to_base": True,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    plan = RoutePlanResponse.model_validate(response.json())
    assert len(plan.routes) == 1
    assert plan.routes[0].objective == RouteObjective.LOWEST_RISK
    # BALANCED was not requested, so not in omitted
    assert not any(o.objective == RouteObjective.BALANCED for o in plan.omitted_objectives)


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_plan_routes_timeout_partial_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout during second profile returns first profile with second in omitted_objectives."""
    # Control virtual clock
    current_virtual_time = 100.0

    def mock_time():
        return current_virtual_time

    monkeypatch.setattr(time, "perf_counter", mock_time)

    # Mock timeout setting to 20.0 seconds
    settings = get_settings()
    monkeypatch.setattr(settings, "ARESNAV_ROUTE_TIMEOUT_S", 20.0)

    # Advance clock past deadline on second profile call
    import app.services.route_service as rs_mod

    orig_plan_routes = rs_mod.plan_routes

    def advance_clock_plan_routes(*args, **kwargs):
        # Let's run with deadline set by route_service (120.0)
        # Advance time to 125.0 during execution so timeout triggers
        res = orig_plan_routes(*args, **kwargs)
        return res

    payload = {
        "region_id": "gale_mount_sharp",
        "base": {"lat": -4.75, "lon": 137.28},
        "destination": {"lat": -4.78, "lon": 137.30},
        "stops": [],
        "objectives": ["LOWEST_RISK", "BALANCED"],
        "return_to_base": True,
    }

    # Advance clock during the second profile inside planner
    import app.engines.routing.planner as pl_mod

    orig_precompute = pl_mod.precompute_cell_cost_factors
    call_idx = 0

    def mock_precompute(*args, **kwargs):
        nonlocal current_virtual_time, call_idx
        call_idx += 1
        if call_idx >= 2:
            current_virtual_time = 125.0  # Expire deadline (100.0 + 20.0 = 120.0)
        return orig_precompute(*args, **kwargs)

    monkeypatch.setattr(pl_mod, "precompute_cell_cost_factors", mock_precompute)

    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    plan = RoutePlanResponse.model_validate(response.json())

    # Graceful partial completion: plan_status OK, 1 route (LOWEST_RISK), BALANCED omitted
    assert plan.plan_status == PlanStatus.OK
    assert len(plan.routes) == 1
    assert plan.routes[0].objective == RouteObjective.LOWEST_RISK
    omitted = next(
        (o for o in plan.omitted_objectives if o.objective == RouteObjective.BALANCED), None
    )
    assert omitted is not None
    assert omitted.reason.startswith("Computation limit:")
    assert "not a terrain finding" in omitted.reason
