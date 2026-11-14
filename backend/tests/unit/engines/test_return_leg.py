"""Unit tests for directional asymmetric return leg walk time (Ruling C-06).

Verifies:
- walk_total = outbound + return, each calculated from per-step directional speed on
  its own direction of travel (return is reversed path with slope signs reversed).
- Assert walk_total differs from 2 * outbound, matching hand-derived literal from
  compute_step_time. Never 2 * outbound.
"""

import math

import numpy as np

from app.engines.eva.speed import compute_step_time
from app.engines.routing.planner import plan_routes
from app.models.enums import RouteObjective


def test_asymmetric_slope_outbound_and_return_walk_times() -> None:
    """Traverse uphill outbound and downhill return verifies walk_total != 2 * outbound.

    Grid: 3 rows x 5 cols.
    Base at (1, 0), elev = 0.0 m.
    Dest at (1, 3), elev = 0.3 m (three 1.0 m steps with dz = +0.1 m each).
    Cell size = 1.0 m. Flat base_speed = 2.7 km/h (0.75 m/s).

    Hand Derivation from compute_step_time(dz, dh, base_speed_kmh=2.7):
      Per-step uphill (dz = +0.1, dh = 1.0):
        grad = +0.1
        exp_arg = -3.5 * (|0.1 + 0.05| - 0.05) = -3.5 * 0.10 = -0.35
        v = 0.75 * exp(-0.35) = 0.75 * 0.7046880897 = 0.528516067 m/s
        s = sqrt(1.0^2 + 0.1^2) = sqrt(1.01) = 1.004987562 m
        t_step_uphill = 1.004987562 / 0.528516067 = 1.9015269815 s

      Per-step downhill (dz = -0.1, dh = 1.0):
        grad = -0.1
        exp_arg = -3.5 * (|-0.1 + 0.05| - 0.05) = -3.5 * 0.0 = 0.0
        v = 0.75 * exp(0.0) = 0.75 m/s
        s = sqrt(1.01) = 1.004987562 m
        t_step_downhill = 1.004987562 / 0.75 = 1.3399834161 s

      3 steps outbound (uphill):
        t_outbound = 3 * 1.9015269815 = 5.7045809445 s
      3 steps return (downhill):
        t_return = 3 * 1.3399834161 = 4.0199502484 s
      Total walk time:
        t_total = t_outbound + t_return = 9.7245311930 s
      Symmetric double outbound:
        2 * t_outbound = 2 * 5.7045809445 = 11.4091618890 s
    """
    t_step_up = compute_step_time(0.1, 1.0, base_speed_kmh=2.7)
    t_step_down = compute_step_time(-0.1, 1.0, base_speed_kmh=2.7)
    assert math.isclose(t_step_up, 1.9015269815108216, rel_tol=1e-7)
    assert math.isclose(t_step_down, 1.339983416149452, rel_tol=1e-7)

    expected_outbound = 3 * t_step_up
    expected_return = 3 * t_step_down
    expected_total = expected_outbound + expected_return
    two_times_outbound = 2.0 * expected_outbound

    # Build terrain grid
    elev = np.zeros((3, 5), dtype=np.float32)
    for c in range(5):
        elev[:, c] = c * 0.1  # linear slope of 0.1 m per metre

    slope = np.full((3, 5), 5.71, dtype=np.float32)  # atan(0.1) approx 5.71 deg
    rough = np.full((3, 5), 0.02, dtype=np.float32)
    haz = np.zeros((3, 5), dtype=np.uint8)

    outcome = plan_routes(
        elevation=elev,
        slope=slope,
        roughness=rough,
        hazard_states=haz,
        base=(1, 0),
        destination=(1, 3),
        cell_size_m=1.0,
        base_speed_kmh=2.7,
        objectives=[RouteObjective.LOWEST_RISK],
        return_to_base=True,
    )

    route = outcome.routes[0]
    assert len(route.legs) == 2
    outbound_leg = route.legs[0]
    return_leg = route.legs[1]

    # Verify legs match hand derivation
    assert math.isclose(outbound_leg.walk_time_s, expected_outbound, rel_tol=1e-5)
    assert math.isclose(return_leg.walk_time_s, expected_return, rel_tol=1e-5)
    assert math.isclose(route.totals.walk_time_s, expected_total, rel_tol=1e-5)

    # Strictly assert walk_total differs from 2 * outbound
    assert not math.isclose(route.totals.walk_time_s, two_times_outbound, rel_tol=1e-3)
    assert route.totals.walk_time_s < two_times_outbound
    diff_s = two_times_outbound - route.totals.walk_time_s
    assert math.isclose(diff_s, 3 * (t_step_up - t_step_down), rel_tol=1e-5)
