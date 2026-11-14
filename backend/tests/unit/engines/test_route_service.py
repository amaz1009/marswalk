"""Unit tests for RouteService and EvaService (T-API-06, T-API-07, T-EVA-04).

Executes route service logic directly in-process without ASGI/loopback network dependencies:
- EvaService.get_defaults returns complete configuration and 9 assumption records.
- POINT_OUTSIDE_REGION raises 422 AppException with exact details.
- REGION_NOT_FOUND raises 404 AppException.
- Real Gale Crater traverse returns valid RoutePlanResponse, conservative 5x grid,
  destination snapping reported in route limitations, complete metrics, timeline,
  and 7-check safety assessment with disclaimer.
- Determinism check: identical requests yield identical routes and metrics.
- Objective filtering: requesting only [LOWEST_RISK] returns only that profile.
- MAX_SCIENCE omitted with spec 7.3 reason when science interest layer absent.
- Timeout path: monkeypatched clock returns partial completion with 'Computation limit:'.
"""

import math
import time
from pathlib import Path

import pytest

from app.config import get_settings
from app.core.errors import AppException
from app.models.enums import AssessmentStatus, PlanStatus, RouteObjective
from app.models.eva import GeoPoint, RoutePlanRequest
from app.services.eva_service import get_eva_service
from app.services.route_service import get_route_service

PROCESSED_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
REAL_DATA_EXISTS = (
    (PROCESSED_DATA_DIR / "HIRISE_DTM_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_SLOPE_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_ROUGHNESS_GALE_MOUND.tif").exists()
)


# ---------------------------------------------------------------------------
# 1. EVA Defaults
# ---------------------------------------------------------------------------


def test_eva_service_get_defaults() -> None:
    """EvaService.get_defaults returns complete configuration and 9 assumption records."""
    service = get_eva_service()
    res = service.get_defaults()
    assert res.config.base_speed_kmh == 2.7
    assert res.config.max_slope_deg == 15.0
    assert res.config.warning_slope_deg == 10.0
    assert res.config.max_eva_hours == 6.0
    assert res.config.return_reserve_fraction == 0.25
    assert res.config.roughness_warning_m == 0.30

    # 9 assumptions from spec 6.2
    assert len(res.assumptions) == 9
    keys = {a.key for a in res.assumptions}
    assert "base_speed_kmh" in keys
    assert "roughness_warning_m" in keys


# ---------------------------------------------------------------------------
# 2. Validation / Region Error Handling
# ---------------------------------------------------------------------------


def test_route_service_point_outside_region() -> None:
    """Coordinates outside region bounds raise AppException 422 POINT_OUTSIDE_REGION."""
    service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=0.0, lon=0.0),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        return_to_base=True,
    )
    with pytest.raises(AppException) as exc_info:
        service.plan_traverse(req)

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code == "POINT_OUTSIDE_REGION"
    assert "gale_mount_sharp" in exc_info.value.message


def test_route_service_unknown_region() -> None:
    """Nonexistent region raises AppException 404 REGION_NOT_FOUND."""
    service = get_route_service()
    req = RoutePlanRequest(
        region_id="unknown_region_id",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        return_to_base=True,
    )
    with pytest.raises(AppException) as exc_info:
        service.plan_traverse(req)

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "REGION_NOT_FOUND"


# ---------------------------------------------------------------------------
# 3. Real Gale Crater Route Planning (T-API-06)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_route_service_real_gale_sample() -> None:
    """Plan traverse on real Gale Mount Sharp rasters with endpoint snapping and 7 safety checks."""
    service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        return_to_base=True,
    )
    plan = service.plan_traverse(req)

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
def test_route_service_determinism() -> None:
    """Determinism check: Identical inputs produce identical routes, metrics, and safety checks."""
    service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        objectives=[RouteObjective.LOWEST_RISK],
        return_to_base=True,
    )
    p1 = service.plan_traverse(req)
    p2 = service.plan_traverse(req)

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
def test_route_service_objective_filtering() -> None:
    """Requesting only [LOWEST_RISK] returns only that profile and no others."""
    service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        objectives=[RouteObjective.LOWEST_RISK],
        return_to_base=True,
    )
    plan = service.plan_traverse(req)
    assert len(plan.routes) == 1
    assert plan.routes[0].objective == RouteObjective.LOWEST_RISK
    assert not any(o.objective == RouteObjective.BALANCED for o in plan.omitted_objectives)


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_route_service_timeout_partial_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout during second profile returns first profile with second in omitted_objectives."""
    current_virtual_time = 100.0

    def mock_time():
        return current_virtual_time

    monkeypatch.setattr(time, "perf_counter", mock_time)

    settings = get_settings()
    monkeypatch.setattr(settings, "ARESNAV_ROUTE_TIMEOUT_S", 20.0)

    import app.engines.routing.planner as pl_mod

    orig_precompute = pl_mod.precompute_cell_cost_factors
    call_idx = 0

    def mock_precompute(*args, **kwargs):
        nonlocal current_virtual_time, call_idx
        call_idx += 1
        if call_idx >= 2:
            current_virtual_time = 125.0
        return orig_precompute(*args, **kwargs)

    monkeypatch.setattr(pl_mod, "precompute_cell_cost_factors", mock_precompute)

    service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        objectives=[RouteObjective.LOWEST_RISK, RouteObjective.BALANCED],
        return_to_base=True,
    )
    plan = service.plan_traverse(req)

    assert plan.plan_status == PlanStatus.OK
    assert len(plan.routes) == 1
    assert plan.routes[0].objective == RouteObjective.LOWEST_RISK
    omitted = next(
        (o for o in plan.omitted_objectives if o.objective == RouteObjective.BALANCED), None
    )
    assert omitted is not None
    assert omitted.reason.startswith("Computation limit:")
    assert "not a terrain finding" in omitted.reason
