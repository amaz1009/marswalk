"""Unit tests for endpoint passability validation and conservative snapping (Ruling C-03).

Verifies:
- Endpoint in an analysis block whose corner pixel is steep gets snapped to nearest passable cell.
- Natively blocked endpoint (native slope > 15 deg or NaN) is NOT snapped.
- No passable cell within 3 analysis cells returns failure with exact tolerance message.
- Endpoint already on a passable analysis cell is not snapped (distance 0.0 m).
"""

import math

import numpy as np
from rasterio.transform import Affine

from app.engines.routing.snapping import resolve_and_snap_endpoint
from app.models.geometry import GeoPoint
from app.utils.coordinates import MarsCoordinateTransformer


def create_snapping_fixture() -> tuple[Affine, MarsCoordinateTransformer]:
    """Create coordinate transformer and affine transform for testing."""
    transformer = MarsCoordinateTransformer(center_lon=137.3, center_lat=0.0)
    # 1 m native resolution
    transform = Affine(1.0, 0.0, -100.0, 0.0, -1.0, -100.0)
    return transform, transformer


def test_endpoint_in_block_with_steep_corner_gets_snapped() -> None:
    """Endpoint is natively passable (slope 4 deg) but 5x5 block is blocked by corner steepness."""
    tf, crs_tf = create_snapping_fixture()

    # Analysis grid 10x10 (50x50 native pixels)
    analysis_hazard = np.zeros((10, 10), dtype=np.uint8)
    native_hazard = np.zeros((50, 50), dtype=np.uint8)

    # Destination requested at analysis cell (5, 5) -> native window (27, 27)
    # Mark analysis cell (5, 5) as blocked (code 2)
    analysis_hazard[5, 5] = 2
    # But native cell (27, 27) is passable (hazard 0)
    native_hazard[27, 27] = 0
    # Steep corner in native block: (25, 25)
    native_hazard[25, 25] = 2

    # Map native cell (27, 27) to GeoPoint
    x_m, y_m = tf @ (27.5, 27.5)
    lon, lat = crs_tf.inverse_transform(x_m, y_m)
    req_pt = GeoPoint(lat=lat, lon=lon)

    snap_res = resolve_and_snap_endpoint(
        label="destination",
        point=req_pt,
        full_transform=tf,
        win_r0=0,
        win_c0=0,
        block_factor=5,
        analysis_hazard=analysis_hazard,
        native_hazard=native_hazard,
        cell_size_m=5.0,
        crs_transformer=crs_tf,
    )

    assert snap_res.is_snapped is True
    assert snap_res.is_natively_blocked is False
    assert snap_res.is_within_tolerance is True
    # Closest orthogonal neighbour in ring 1 is (4, 5) with distance 1 cell = 5.0 m
    assert snap_res.used_analysis_cell == (4, 5)
    assert math.isclose(snap_res.snap_distance_m, 5.0, abs_tol=1e-3)
    assert "Endpoint 'destination' snapped 5.0 m" in snap_res.snap_message
    assert "due to localized obstacle in 5x5 analysis cell" in snap_res.snap_message


def test_natively_blocked_endpoint_is_not_snapped() -> None:
    """Endpoint lying on a natively blocked cell (code 2) is NOT snapped per Ruling C-03."""
    tf, crs_tf = create_snapping_fixture()

    analysis_hazard = np.zeros((10, 10), dtype=np.uint8)
    native_hazard = np.zeros((50, 50), dtype=np.uint8)

    # Native cell is impassable
    native_hazard[25, 25] = 2
    analysis_hazard[5, 5] = 2

    x_m, y_m = tf @ (25.5, 25.5)
    lon, lat = crs_tf.inverse_transform(x_m, y_m)
    req_pt = GeoPoint(lat=lat, lon=lon)

    snap_res = resolve_and_snap_endpoint(
        label="destination",
        point=req_pt,
        full_transform=tf,
        win_r0=0,
        win_c0=0,
        block_factor=5,
        analysis_hazard=analysis_hazard,
        native_hazard=native_hazard,
        cell_size_m=5.0,
        crs_transformer=crs_tf,
    )

    assert snap_res.is_snapped is False
    assert snap_res.is_natively_blocked is True
    assert snap_res.is_within_tolerance is False
    assert "lies on a natively impassable cell" in snap_res.failure_reason
    assert "Snapping is prohibited for natively blocked endpoints" in snap_res.failure_reason


def test_no_passable_cell_within_three_rings_returns_failure() -> None:
    """Surrounded by impassable cells out to 3 rings returns failure with window message."""
    tf, crs_tf = create_snapping_fixture()

    # Block analysis grid in a 7x7 zone around (5, 5)
    analysis_hazard = np.zeros((11, 11), dtype=np.uint8)
    analysis_hazard[2:9, 2:9] = 2  # rings 1, 2, 3 all blocked
    native_hazard = np.zeros((55, 55), dtype=np.uint8)
    # Native cell itself is passable
    native_hazard[27, 27] = 0

    x_m, y_m = tf @ (27.5, 27.5)
    lon, lat = crs_tf.inverse_transform(x_m, y_m)
    req_pt = GeoPoint(lat=lat, lon=lon)

    snap_res = resolve_and_snap_endpoint(
        label="destination",
        point=req_pt,
        full_transform=tf,
        win_r0=0,
        win_c0=0,
        block_factor=5,
        analysis_hazard=analysis_hazard,
        native_hazard=native_hazard,
        cell_size_m=5.0,
        crs_transformer=crs_tf,
    )

    assert snap_res.is_snapped is False
    assert snap_res.is_within_tolerance is False
    assert (
        "No passable analysis cell within 3 cells of endpoint 'destination'"
        in snap_res.failure_reason
    )
    assert "within the analysis window" in snap_res.failure_reason


def test_passable_endpoint_not_snapped() -> None:
    """Endpoint already on a passable analysis cell has is_snapped=False and distance 0.0."""
    tf, crs_tf = create_snapping_fixture()

    analysis_hazard = np.zeros((10, 10), dtype=np.uint8)
    native_hazard = np.zeros((50, 50), dtype=np.uint8)

    x_m, y_m = tf @ (12.5, 12.5)
    lon, lat = crs_tf.inverse_transform(x_m, y_m)
    req_pt = GeoPoint(lat=lat, lon=lon)

    snap_res = resolve_and_snap_endpoint(
        label="base",
        point=req_pt,
        full_transform=tf,
        win_r0=0,
        win_c0=0,
        block_factor=5,
        analysis_hazard=analysis_hazard,
        native_hazard=native_hazard,
        cell_size_m=5.0,
        crs_transformer=crs_tf,
    )

    assert snap_res.is_snapped is False
    assert snap_res.is_within_tolerance is True
    assert snap_res.snap_distance_m == 0.0
    assert snap_res.snap_message is None
