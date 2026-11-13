"""Unit tests for Mars geodesy, Haversine distance, bearing, and interpolation.

Implements T-COORD-05, T-COORD-06, and great-circle interpolation checks.
"""

import math

import pytest

from app.utils.geodesy import (
    MARS_SPHERE_RADIUS_M,
    haversine_distance,
    initial_bearing,
    interpolate_great_circle,
    wrap_longitude_difference,
)


def test_t_coord_05_haversine_distance() -> None:
    """T-COORD-05: Haversine: zero distance, quarter meridian = πR/2, antipodal = πR.

    Tolerance 1e-6 relative.
    Also verifies: one degree of longitude along equator = R * π / 180; distance is symmetric.
    """
    r = MARS_SPHERE_RADIUS_M

    # Point to itself is 0.0
    assert haversine_distance(0.0, 0.0, 0.0, 0.0) == 0.0
    assert haversine_distance(-4.5, 137.4, -4.5, 137.4) == 0.0

    # Symmetric distance
    p1 = (-4.5, 137.4)
    p2 = (-4.6, 137.5)
    d12 = haversine_distance(p1[0], p1[1], p2[0], p2[1])
    d21 = haversine_distance(p2[0], p2[1], p1[0], p1[1])
    assert math.isclose(d12, d21, rel_tol=1e-12)

    # One degree of longitude along equator = R * pi / 180
    expected_one_deg = r * math.pi / 180.0
    calc_one_deg = haversine_distance(0.0, 0.0, 0.0, 1.0)
    assert math.isclose(calc_one_deg, expected_one_deg, rel_tol=1e-6)

    # Quarter meridian (pole to equator): πR / 2
    expected_quarter = math.pi * r / 2.0
    calc_quarter = haversine_distance(0.0, 0.0, 90.0, 0.0)
    assert math.isclose(calc_quarter, expected_quarter, rel_tol=1e-6)

    # Antipodal points: πR
    expected_antipodal = math.pi * r
    calc_antipodal_meridian = haversine_distance(90.0, 0.0, -90.0, 0.0)
    assert math.isclose(calc_antipodal_meridian, expected_antipodal, rel_tol=1e-6)

    calc_antipodal_equator = haversine_distance(0.0, 0.0, 0.0, 180.0)
    assert math.isclose(calc_antipodal_equator, expected_antipodal, rel_tol=1e-6)

    # Invalid coordinates rejected
    with pytest.raises(ValueError):
        haversine_distance(95.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        haversine_distance(0.0, float("nan"), 0.0, 0.0)


def test_t_coord_06_initial_bearing() -> None:
    """T-COORD-06: Initial bearing for due north, east, south and west.

    Due north is 0, due east along the equator is 90.
    """
    # Due north from equator: 0.0°
    assert math.isclose(initial_bearing(0.0, 0.0, 10.0, 0.0), 0.0, abs_tol=1e-9)

    # Due east along equator: 90.0°
    assert math.isclose(initial_bearing(0.0, 0.0, 0.0, 10.0), 90.0, abs_tol=1e-9)

    # Due south along meridian: 180.0°
    assert math.isclose(initial_bearing(10.0, 0.0, 0.0, 0.0), 180.0, abs_tol=1e-9)

    # Due west along equator: 270.0°
    assert math.isclose(initial_bearing(0.0, 10.0, 0.0, 0.0), 270.0, abs_tol=1e-9)

    # Point to itself returns 0.0 convention
    assert initial_bearing(-4.5, 137.4, -4.5, 137.4) == 0.0

    # Invalid coordinates rejected
    with pytest.raises(ValueError):
        initial_bearing(0.0, 0.0, -95.0, 0.0)


def test_great_circle_interpolation() -> None:
    """Great-circle interpolation: midpoint between (0, 0) and (0, 90) is lon 45.

    Endpoints returned exactly at fraction 0.0 and 1.0.
    """
    # Endpoints returned exactly
    p_start = interpolate_great_circle(lat1=-4.5, lon1=137.4, lat2=-4.8, lon2=137.8, fraction=0.0)
    assert p_start == (-4.5, 137.4)

    p_end = interpolate_great_circle(lat1=-4.5, lon1=137.4, lat2=-4.8, lon2=137.8, fraction=1.0)
    assert p_end == (-4.8, 137.8)

    # Midpoint between (0, 0) and (0, 90) along equator is (0, 45)
    lat_mid, lon_mid = interpolate_great_circle(
        lat1=0.0, lon1=0.0, lat2=0.0, lon2=90.0, fraction=0.5
    )
    assert math.isclose(lat_mid, 0.0, abs_tol=1e-9)
    assert math.isclose(lon_mid, 45.0, abs_tol=1e-9)

    # Midpoint along meridian from (0, 0) to (60, 0) is (30, 0)
    lat_mid_meridian, lon_mid_meridian = interpolate_great_circle(
        lat1=0.0, lon1=0.0, lat2=60.0, lon2=0.0, fraction=0.5
    )
    assert math.isclose(lat_mid_meridian, 30.0, abs_tol=1e-9)
    assert math.isclose(lon_mid_meridian, 0.0, abs_tol=1e-9)

    # Invalid fractions rejected
    with pytest.raises(ValueError, match="Interpolation fraction"):
        interpolate_great_circle(0.0, 0.0, 10.0, 10.0, -0.01)
    with pytest.raises(ValueError, match="Interpolation fraction"):
        interpolate_great_circle(0.0, 0.0, 10.0, 10.0, 1.01)
    with pytest.raises(ValueError, match="Interpolation fraction"):
        interpolate_great_circle(0.0, 0.0, 10.0, 10.0, float("nan"))


def test_wrap_longitude_difference() -> None:
    """wrap_longitude_difference wraps angles into (-180, 180]."""
    assert wrap_longitude_difference(0.0) == 0.0
    assert wrap_longitude_difference(180.0) == 180.0
    assert wrap_longitude_difference(-180.0) == 180.0
    assert wrap_longitude_difference(270.0) == -90.0
    assert wrap_longitude_difference(-270.0) == 90.0
    assert wrap_longitude_difference(360.0) == 0.0

    with pytest.raises(ValueError):
        wrap_longitude_difference(float("nan"))
