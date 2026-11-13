"""Unit tests for Mars coordinate normalisation, conversions, and projections.

Implements T-COORD-01, T-COORD-02, T-COORD-03, T-COORD-04, T-COORD-07, T-COORD-08.
"""

import math

import pyproj
import pytest

from app.utils.coordinates import (
    MARS_ELLIPSOID_WKT,
    MARS_EQUATORIAL_RADIUS_M,
    MARS_POLAR_RADIUS_M,
    MARS_SPHERE_RADIUS_M,
    MarsCoordinateTransformer,
    east_to_west_longitude,
    normalize_longitude,
    planetocentric_to_planetographic,
    planetographic_to_planetocentric,
    validate_coordinates,
    validate_latitude,
    validate_longitude,
    west_to_east_longitude,
)


def test_t_coord_01_longitude_normalization() -> None:
    """T-COORD-01: Longitude normalisation: -180 -> 180, -0.0 -> 0, 359.999 stays, 137.4 stays.

    Also verifies user requirements: 360 -> 0, -90 -> 270, 450 -> 90, and all outputs in [0, 360).
    """
    assert normalize_longitude(-180.0) == 180.0
    assert normalize_longitude(-0.0) == 0.0
    assert normalize_longitude(0.0) == 0.0
    assert normalize_longitude(359.999) == 359.999
    assert normalize_longitude(137.4) == 137.4

    # Additional prompt checks
    assert normalize_longitude(360.0) == 0.0
    assert normalize_longitude(-90.0) == 270.0
    assert normalize_longitude(450.0) == 90.0

    # Ensure range [0, 360) across a sweep of positive and negative angles
    for lon in [-720.0, -540.0, -360.0, -270.0, -1.0, 0.5, 180.0, 359.9, 720.0, 1080.0]:
        res = normalize_longitude(lon)
        assert 0.0 <= res < 360.0


def test_t_coord_02_coordinate_validation() -> None:
    """T-COORD-02: Rejects latitude outside [-90, 90] and longitude outside [-180, 360).

    Also verifies rejection of NaN and infinity.
    """
    # Valid latitudes
    validate_latitude(-90.0)
    validate_latitude(0.0)
    validate_latitude(90.0)
    validate_latitude(-4.5)

    # Invalid latitudes outside [-90, 90]
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_latitude(-90.0001)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_latitude(90.0001)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_latitude(-180.0)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_latitude(100.0)

    # Invalid latitude non-finite
    with pytest.raises(ValueError, match="finite number"):
        validate_latitude(float("nan"))
    with pytest.raises(ValueError, match="finite number"):
        validate_latitude(float("inf"))
    with pytest.raises(ValueError, match="finite number"):
        validate_latitude(float("-inf"))

    # Valid longitudes in [-180, 360)
    validate_longitude(-180.0)
    validate_longitude(0.0)
    validate_longitude(137.4)
    validate_longitude(359.999)

    # Invalid longitudes outside [-180, 360)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_longitude(-180.001)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_longitude(360.0)
    with pytest.raises(ValueError, match="outside allowable range"):
        validate_longitude(450.0)

    # Invalid longitude non-finite
    with pytest.raises(ValueError, match="finite number"):
        validate_longitude(float("nan"))
    with pytest.raises(ValueError, match="finite number"):
        validate_longitude(float("inf"))

    # validate_coordinates helper
    validate_coordinates(-4.5, 137.4)
    with pytest.raises(ValueError):
        validate_coordinates(-95.0, 137.4)
    with pytest.raises(ValueError):
        validate_coordinates(-4.5, 365.0)


def test_t_coord_03_planetographic_planetocentric_conversion() -> None:
    """T-COORD-03: Planetographic <-> planetocentric round trip within 1e-9°.

    Equator and poles unchanged; value at 45° matches formula.
    """
    # Equator unchanged
    assert planetographic_to_planetocentric(0.0) == 0.0
    assert planetocentric_to_planetographic(0.0) == 0.0

    # Poles unchanged
    assert planetographic_to_planetocentric(90.0) == 90.0
    assert planetographic_to_planetocentric(-90.0) == -90.0
    assert planetocentric_to_planetographic(90.0) == 90.0
    assert planetocentric_to_planetographic(-90.0) == -90.0

    # Value at 45° matches exact formula: tan(lat_c) = (b^2 / a^2) * tan(45°)
    b2_over_a2 = (MARS_POLAR_RADIUS_M / MARS_EQUATORIAL_RADIUS_M) ** 2
    expected_centric_45 = math.degrees(math.atan(b2_over_a2 * math.tan(math.radians(45.0))))
    calc_centric = planetographic_to_planetocentric(45.0)
    assert math.isclose(calc_centric, expected_centric_45, rel_tol=1e-12, abs_tol=1e-12)

    # At 45°, planetocentric is approximately 44.661768°
    assert abs(calc_centric - 44.661768) < 1e-5

    # Round trip across latitudes [-89° to +89°] within 1e-9°
    for lat in [-85.0, -60.0, -45.0, -30.0, -4.5, 10.0, 30.0, 45.0, 60.0, 85.0]:
        centric = planetographic_to_planetocentric(lat)
        graphic_back = planetocentric_to_planetographic(centric)
        assert math.isclose(lat, graphic_back, rel_tol=1e-9, abs_tol=1e-9)

    # Rejection of invalid inputs
    with pytest.raises(ValueError):
        planetographic_to_planetocentric(95.0)
    with pytest.raises(ValueError):
        planetocentric_to_planetographic(float("nan"))


def test_t_coord_04_west_east_conversion() -> None:
    """T-COORD-04: West-positive to east-positive conversion round-trips."""
    # (360 - lon_west) % 360
    assert west_to_east_longitude(0.0) == 0.0
    assert west_to_east_longitude(360.0) == 0.0
    assert west_to_east_longitude(90.0) == 270.0
    assert west_to_east_longitude(270.0) == 90.0
    assert west_to_east_longitude(180.0) == 180.0

    # East-to-west
    assert east_to_west_longitude(270.0) == 90.0
    assert east_to_west_longitude(90.0) == 270.0

    # Round-trip across all quadrants
    for lon in [0.0, 45.5, 137.4, 180.0, 222.2, 359.9]:
        assert math.isclose(west_to_east_longitude(east_to_west_longitude(lon)), lon, abs_tol=1e-12)

    # Rejection of invalid inputs
    with pytest.raises(ValueError):
        west_to_east_longitude(float("nan"))
    with pytest.raises(ValueError):
        east_to_west_longitude(float("inf"))


def test_t_coord_07_transformer_round_trip() -> None:
    """T-COORD-07: Internal -> projected -> internal round trip within half a cell.

    Tested through pyproj.Transformer on Mars Equirectangular CRS (< 0.5 m for 1 m DTM).
    """
    transformer = MarsCoordinateTransformer(
        center_lat=-4.5,
        center_lon=137.4,
        false_easting=0.0,
        false_northing=0.0,
    )

    test_points = [
        (-4.5, 137.4),  # Origin
        (-4.6, 137.5),  # Nearby traverse point
        (-5.0, 137.0),  # SW Gale Crater
        (-4.0, 138.0),  # NE Gale Crater
        (0.0, 137.4),  # Equator crossing
    ]

    cell_size_m = 1.0  # 1m HiRISE DTM cell
    half_cell_m = cell_size_m / 2.0

    for lat, lon in test_points:
        x, y = transformer.transform(lon, lat)
        lon_back, lat_back = transformer.inverse_transform(x, y)

        # Angular difference to surface metres on Mars sphere
        dlat_rad = math.radians(lat_back - lat)
        dlon_rad = math.radians(lon_back - lon) * math.cos(math.radians(lat))
        err_m = MARS_SPHERE_RADIUS_M * math.sqrt(dlat_rad**2 + dlon_rad**2)

        assert err_m < half_cell_m, f"Point ({lat}, {lon}) error {err_m} m exceeds {half_cell_m} m"


def test_t_coord_08_proj_ballpark_trap() -> None:
    """T-COORD-08: Ellipsoid-based planetographic input converted explicitly before projection.

    Docs/SCIENCE_AND_SAFETY_SPEC.md §2.3 states:
    'Mandatory rule: do not rely on PROJ to perform this conversion. Between two Mars
    CRSs with different datums and no defined transformation, PROJ may apply a
    "ballpark" transformation that leaves latitude numbers unchanged.'

    How this test would fail if PROJ fell back to a ballpark or Earth-based operation:
    1. The internal-to-analysis MarsCoordinateTransformer operates on Mars 2000 Sphere,
       so its underlying pyproj.Transformer has no datum change and has_ballpark_transformation
       MUST be False. If PROJ fell back to a ballpark operation or Earth datum, this assertion
       fails.
    2. A direct PROJ transformer from MARS_ELLIPSOID_WKT to the analysis CRS has no datum
       shift definition in PROJ; querying pyproj.Transformer.from_crs(MARS_ELLIPSOID_WKT, ...)
       proves that PROJ reports has_ballpark_transformation == True. This demonstrates that
       PROJ cannot perform the conversion on its own without falling into the ballpark trap.
    3. When is_planetographic=True is passed, MarsCoordinateTransformer explicitly converts
       planetographic 45° to planetocentric ~44.661768° before projection. A ballpark transformation
       would leave latitude as 45°, producing an error of R * radians(45 - 44.661768) ≈ 20,049 m.
       The test verifies the explicit conversion avoids this ~20 km error.
    """
    transformer = MarsCoordinateTransformer(
        center_lat=0.0,
        center_lon=0.0,
    )

    # 1. Verify our transformer has no ballpark transformation (exact map projection on Mars sphere)
    assert not transformer.has_ballpark_transformation

    # 2. Verify PROJ's ballpark trap: transforming directly from Mars Ellipsoid to analysis CRS
    # falls back to a ballpark transformation because PROJ lacks a Mars datum shift.
    direct_ellipsoid_transformer = pyproj.Transformer.from_crs(
        MARS_ELLIPSOID_WKT,
        transformer.wkt,
        always_xy=True,
    )
    assert direct_ellipsoid_transformer.has_ballpark_transformation, (
        "Expected PROJ to report a ballpark transformation between Mars Ellipsoid and Sphere"
    )

    # 3. Verify explicit conversion prevents the ~20 km ballpark error
    planetographic_lat = 45.0
    lon = 0.0

    x_correct, y_correct = transformer.transform(lon, planetographic_lat, is_planetographic=True)
    x_ballpark, y_ballpark = transformer.transform(lon, planetographic_lat, is_planetographic=False)

    # The difference between ballpark (unconverted 45°) and explicit planetocentric conversion
    b2_over_a2 = (MARS_POLAR_RADIUS_M / MARS_EQUATORIAL_RADIUS_M) ** 2
    expected_centric_45 = math.degrees(math.atan(b2_over_a2 * math.tan(math.radians(45.0))))
    expected_delta_m = MARS_SPHERE_RADIUS_M * math.radians(planetographic_lat - expected_centric_45)

    y_error_m = abs(y_ballpark - y_correct)
    assert math.isclose(y_error_m, expected_delta_m, rel_tol=1e-5), (
        f"Ballpark delta {y_error_m} m does not match expected {expected_delta_m} m"
    )
    assert y_error_m > 10_000.0, f"Error {y_error_m} m is unexpectedly small (< 10 km)"

    # Inverse transformation with to_planetographic=True restores original planetographic latitude
    lon_rt, lat_rt = transformer.inverse_transform(x_correct, y_correct, to_planetographic=True)
    assert math.isclose(lon_rt, lon, abs_tol=1e-9)
    assert math.isclose(lat_rt, planetographic_lat, abs_tol=1e-9)
