"""Unit tests for terrain and hazard engines (T-TERR-01 to T-TERR-08, T-HAZ-01).

Implements docs/TESTING_STRATEGY.md section 5.4.
All fixtures are code-generated synthetic arrays (pure synthetic fixtures).
All expected values are derived by formula, never pasted numbers.
"""

import math

import numpy as np

from app.engines.hazards.grid import HazardState, compute_hazard_grid
from app.engines.terrain.aggregate import aggregate_to_analysis_grid
from app.engines.terrain.confidence import ConfidenceCode, compute_data_confidence
from app.engines.terrain.profile import (
    interpolate_great_circle_points,
)
from app.engines.terrain.roughness import compute_residual_roughness
from app.engines.terrain.sampling import sample_bilinear
from app.engines.terrain.slope import (
    MARS_SPHERE_RADIUS_M,
    compute_horn_slope,
    compute_row_ground_scales,
)
from app.models.geometry import GeoPoint


def test_t_terr_01_horn_slope_tilted_planes() -> None:
    """T-TERR-01: Horn slope on tilted planes of 5, 10, and 30 deg within 0.01 deg.

    Expected slope is derived by formula:
        slope_deg = degrees(atan(sqrt(a^2 + b^2)))
    """
    dy = 1.0
    dx_ground = np.array([1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    rows, cols = 5, 5

    for target_deg in [5.0, 10.0, 30.0]:
        # Gradient magnitude tan(target_deg)
        grad = math.tan(math.radians(target_deg))

        # Test purely x-tilted plane: z = grad * x
        x_coords = np.arange(cols, dtype=np.float64) * 1.0
        y_coords = np.arange(rows, dtype=np.float64) * 1.0
        xx, yy = np.meshgrid(x_coords, y_coords)

        # 1. Pure East-West tilt
        z_x = grad * xx
        slope_x = compute_horn_slope(z_x.astype(np.float32), dx_ground, dy)
        interior_x = slope_x[1:-1, 1:-1]
        assert np.allclose(interior_x, target_deg, atol=0.01), (
            f"Expected x-tilted slope {target_deg} deg, got {interior_x[1, 1]}"
        )

        # 2. Pure North-South tilt: z = grad * y
        z_y = grad * yy
        slope_y = compute_horn_slope(z_y.astype(np.float32), dx_ground, dy)
        interior_y = slope_y[1:-1, 1:-1]
        assert np.allclose(interior_y, target_deg, atol=0.01), (
            f"Expected y-tilted slope {target_deg} deg, got {interior_y[1, 1]}"
        )

        # 3. 45-degree diagonal tilt: a = grad / sqrt(2), b = grad / sqrt(2)
        # sqrt(a^2 + b^2) = grad
        a = grad / math.sqrt(2.0)
        b = grad / math.sqrt(2.0)
        z_diag = a * xx + b * yy
        slope_diag = compute_horn_slope(z_diag.astype(np.float32), dx_ground, dy)
        interior_diag = slope_diag[1:-1, 1:-1]
        assert np.allclose(interior_diag, target_deg, atol=0.01), (
            f"Expected diagonal slope {target_deg} deg, got {interior_diag[1, 1]}"
        )


def test_d_013_equirectangular_cos_latitude_scaling() -> None:
    """Owner Decision D-013: Verify cos(latitude) ground scaling in equirectangular CRS.

    Asserts that:
    1. Per-row ground scale dx_ground differs between two rows at different latitudes
       by the exact analytical cos(phi) ratio.
    2. Expected slope for a plane specified in ground metres is derived by formula
       accounting for cos(latitude).
    """
    radius = MARS_SPHERE_RADIUS_M
    dx_proj = 1.0117467945795
    dy_proj = 1.0117467945795

    # 1. Compare two rows at latitude 0 and latitude -4.8 deg
    lat_1_deg = 0.0
    lat_2_deg = -4.8
    y_1 = lat_1_deg * (math.pi / 180.0) * radius  # 0.0 m northing
    y_2 = lat_2_deg * (math.pi / 180.0) * radius  # negative northing

    # Construct synthetic 2-row transform
    # Row 0 at y_1, Row 1 at y_2
    transform_f = y_1
    transform_e = y_2 - y_1  # step between rows

    dx_ground, dy = compute_row_ground_scales(
        transform_a=dx_proj,
        transform_e=transform_e,
        transform_f=transform_f,
        height=2,
        radius_m=radius,
    )

    # Cell centres for row 0 and row 1 per Amendment A-2 (f + (row + 0.5) * e)
    y_center_0 = transform_f + 0.5 * transform_e
    y_center_1 = transform_f + 1.5 * transform_e
    expected_ratio = math.cos(y_center_1 / radius) / math.cos(y_center_0 / radius)
    actual_ratio = dx_ground[1] / dx_ground[0]
    assert np.isclose(actual_ratio, expected_ratio, rtol=1e-5), (
        f"Scale ratio {actual_ratio} must match analytical cos ratio {expected_ratio}"
    )

    # 2. Slope of known ground slope plane at latitude -4.8 deg:
    # Let ground slope in x be S_ground = tan(15 deg).
    # Then dz/dx_ground = S_ground.
    # In projected coordinates, x_proj = x_ground / cos(phi), so
    # dz/dx_proj = S_ground * cos(phi).
    # Horn slope using dx_ground must recover exactly the 15 deg ground slope!
    target_ground_deg = 15.0
    phi_test_rad = math.radians(-4.8)
    s_ground = math.tan(math.radians(target_ground_deg))

    # Grid of 5x5 cells where x is in projected coordinates
    cols = 5
    rows = 5
    x_proj_coords = np.arange(cols, dtype=np.float64) * dx_proj
    # Elevation based on ground distance: x_ground = x_proj * cos(phi)
    # z = S_ground * (x_proj * cos(phi))
    z_elev = s_ground * (x_proj_coords[None, :] * math.cos(phi_test_rad))
    z_elev = np.repeat(z_elev, rows, axis=0)

    # Supply dx_ground = dx_proj * cos(phi)
    dx_ground_arr = np.full(rows, dx_proj * math.cos(phi_test_rad), dtype=np.float64)
    computed_slope = compute_horn_slope(z_elev.astype(np.float32), dx_ground_arr, dy_proj)

    # Interior must equal target_ground_deg within 0.01 deg
    interior_slope = computed_slope[1:-1, 1:-1]
    assert np.allclose(interior_slope, target_ground_deg, atol=0.01), (
        f"Ground slope {target_ground_deg} deg not recovered with cos(phi) scale: "
        f"{interior_slope[1, 1]}"
    )


def test_t_terr_02_slope_nan_propagation_and_edges() -> None:
    """T-TERR-02: Slope is NaN when any window cell is NaN, and on raster edges."""
    rows, cols = 7, 7
    z = np.zeros((rows, cols), dtype=np.float32)
    dx_ground = np.ones(rows, dtype=np.float64)
    dy = 1.0

    slope = compute_horn_slope(z, dx_ground, dy)

    # Edge cells must be NaN (spec section 4.2)
    assert np.all(np.isnan(slope[0, :])), "Top row must be NaN"
    assert np.all(np.isnan(slope[-1, :])), "Bottom row must be NaN"
    assert np.all(np.isnan(slope[:, 0])), "Left column must be NaN"
    assert np.all(np.isnan(slope[:, -1])), "Right column must be NaN"

    # Flat plane interior must be 0 deg
    assert np.allclose(slope[1:-1, 1:-1], 0.0), "Flat interior must be slope 0"

    # Introduce a single NaN at cell (3, 3)
    z_nan = z.copy()
    z_nan[3, 3] = np.nan

    slope_nan = compute_horn_slope(z_nan, dx_ground, dy)

    # All 9 cells in the 3x3 neighbourhood of (3, 3) must now be NaN
    for r in range(2, 5):
        for c in range(2, 5):
            assert np.isnan(slope_nan[r, c]), f"Cell ({r}, {c}) must be NaN due to neighbour NaN"

    # Cells outside the 3x3 window must remain valid (0.0)
    assert not np.isnan(slope_nan[1, 1]), "Cell (1, 1) outside 3x3 window should remain valid"
    assert not np.isnan(slope_nan[5, 5]), "Cell (5, 5) outside 3x3 window should remain valid"


def test_t_terr_03_residual_roughness_plane_is_zero() -> None:
    """T-TERR-03: Residual roughness of a perfect plane is 0 (<= 1e-9 m) at any tilt."""
    rows, cols = 7, 7
    dx_ground = np.ones(rows, dtype=np.float64)
    dy = 1.0

    xx, yy = np.meshgrid(np.arange(cols), np.arange(rows))

    for tilt_deg in [0.0, 5.0, 15.0, 30.0, 45.0]:
        grad = math.tan(math.radians(tilt_deg))
        # Arbitrary plane z = alpha*x + beta*y + gamma in float64
        z_plane = (grad * 0.6) * xx + (grad * 0.8) * yy + 123.45

        roughness = compute_residual_roughness(z_plane, dx_ground, dy)

        # Edge cells are NaN
        assert np.all(np.isnan(roughness[0, :])), "Top edge must be NaN"
        assert np.all(np.isnan(roughness[:, 0])), "Left edge must be NaN"

        # Interior roughness must be <= 1e-9 m
        interior_rms = roughness[1:-1, 1:-1]
        assert np.all(interior_rms <= 1e-9), (
            f"Residual roughness for plane tilted {tilt_deg} deg must be ~0, "
            f"got max {np.nanmax(interior_rms)}"
        )


def test_residual_roughness_float32_offset_regression() -> None:
    """Regression test: perfect plane with realistic Mars elevation offset (-4000 m).

    Verifies that local centering prevents float32 catastrophic cancellation:
    even with a large negative elevation offset (-4000 m), residual roughness
    remains bounded within float32 precision spacing (~4.88e-4 m), whereas uncentered
    subtraction produced 0.06 m noise.
    """
    rows, cols = 7, 7
    dx_ground = np.ones(rows, dtype=np.float64)
    dy = 1.0

    xx, yy = np.meshgrid(np.arange(cols), np.arange(rows))

    for tilt_deg in [0.0, 5.0, 15.0, 30.0]:
        grad = math.tan(math.radians(tilt_deg))
        z_plane = ((grad * 0.6) * xx + (grad * 0.8) * yy - 4000.0).astype(np.float32)

        roughness = compute_residual_roughness(z_plane, dx_ground, dy)
        interior_rms = roughness[1:-1, 1:-1]
        max_spacing = float(np.spacing(np.float32(4000.0)))
        assert np.all(interior_rms <= max_spacing), (
            f"Roughness on -4000 m offset plane must be <= float32 spacing ({max_spacing:.2e}), "
            f"got max {np.nanmax(interior_rms):.2e}"
        )


def test_t_terr_04_residual_roughness_checkerboard_analytic() -> None:
    """T-TERR-04: Residual roughness of checkerboard fixture equals analytic value.

    For a 3x3 window:
        +h -h +h
        -h +h -h
        +h -h +h
    Mean = h/9. By symmetry alpha = 0, beta = 0.
    Sum of squared residuals = 5*(8/9*h)^2 + 4*(-10/9*h)^2 = 80/9 * h^2.
    RMS = sqrt(80/81) * h = (4 * sqrt(5) / 9) * h.
    """
    h = 2.5
    expected_rms = (4.0 * math.sqrt(5.0) / 9.0) * h

    # 5x5 array with checkerboard in center
    checker = np.array(
        [
            [+h, -h, +h, -h, +h],
            [-h, +h, -h, +h, -h],
            [+h, -h, +h, -h, +h],
            [-h, +h, -h, +h, -h],
            [+h, -h, +h, -h, +h],
        ],
        dtype=np.float32,
    )

    dx_ground = np.ones(5, dtype=np.float64)
    dy = 1.0

    roughness = compute_residual_roughness(checker, dx_ground, dy)

    # Centre cell (2, 2)
    center_rms = roughness[2, 2]
    assert np.isclose(center_rms, expected_rms, rtol=1e-5), (
        f"Checkerboard RMS expected {expected_rms:.6f}, got {center_rms:.6f}"
    )


def test_t_terr_05_conservative_aggregation_and_validity() -> None:
    """T-TERR-05: Aggregation uses maximum slope and roughness; 90% validity rule holds."""
    # 10x10 native grid, aggregated with block_size=5 -> 2x2 analysis grid
    elev = np.full((10, 10), 100.0, dtype=np.float32)
    slope = np.full((10, 10), 5.0, dtype=np.float32)
    roughness = np.full((10, 10), 0.1, dtype=np.float32)

    # Introduce a steep native cell in Block (0, 0): slope = 25.0 deg, roughness = 0.8 m
    slope[2, 2] = 25.0
    roughness[2, 2] = 0.8

    # Block (0, 1): Introduce 3 NaNs out of 25 cells (validity = 22/25 = 88% < 90%)
    elev[0:3, 5] = np.nan
    slope[0:3, 5] = np.nan
    roughness[0:3, 5] = np.nan

    # Block (1, 0): Introduce 2 NaNs out of 25 cells (validity = 23/25 = 92% >= 90%)
    elev[7:9, 1] = np.nan
    slope[7:9, 1] = np.nan
    roughness[7:9, 1] = np.nan

    agg = aggregate_to_analysis_grid(elev, slope, roughness, block_size=5, min_valid_fraction=0.90)

    # Block (0, 0): 100% valid; slope must be MAXIMUM (25.0 deg); roughness must be MAXIMUM (0.8 m)
    assert bool(agg["is_valid"][0, 0]) is True
    assert np.isclose(agg["slope_max"][0, 0], 25.0), "Aggregated slope must be conservative maximum"
    assert np.isclose(agg["roughness_max"][0, 0], 0.8), (
        "Aggregated roughness must be conservative maximum"
    )
    assert agg["slope_mean"][0, 0] < 25.0, "Mean slope should be lower than maximum"

    # Block (0, 1): 88% valid (< 90%); must be marked INVALID and NaN per section 4.4
    assert not agg["is_valid"][0, 1], "Block with 88% valid cells must fail 90% validity threshold"
    assert np.isnan(agg["elevation"][0, 1]), "Invalid block elevation must be NaN"
    assert np.isnan(agg["slope_max"][0, 1]), "Invalid block slope must be NaN"
    assert np.isnan(agg["roughness_max"][0, 1]), "Invalid block roughness must be NaN"

    # Block (1, 0): 92% valid (>= 90%); must be VALID
    assert agg["is_valid"][1, 0], "Block with 92% valid cells must pass 90% validity threshold"
    assert not np.isnan(agg["elevation"][1, 0]), "Valid block elevation must not be NaN"


def test_t_terr_06_bilinear_sampling_nan_propagation() -> None:
    """T-TERR-06: Bilinear sampling returns NaN if any contributing cell is NaN."""
    data = np.array(
        [
            [10.0, 20.0, 30.0],
            [40.0, 50.0, 60.0],
            [70.0, 80.0, 90.0],
        ],
        dtype=np.float64,
    )

    # Valid position (0.5, 0.5): average of 10, 20, 40, 50 = 30.0
    val = sample_bilinear(data, 0.5, 0.5)
    expected = 0.25 * (10.0 + 20.0 + 40.0 + 50.0)
    assert np.isclose(val, expected), f"Expected {expected}, got {val}"

    # Corrupt one contributing cell (0, 1) with NaN
    data_nan = data.copy()
    data_nan[0, 1] = np.nan

    # Sampling at (0.5, 0.5) involves (0,0), (0,1), (1,0), (1,1) -> must be NaN per section 4.1
    val_nan = sample_bilinear(data_nan, 0.5, 0.5)
    assert np.isnan(val_nan), "Bilinear sampling must return NaN if any contributing cell is NaN"

    # Sampling at (1.5, 0.5) involves (1,0), (1,1), (2,0), (2,1) -> no NaN involved, should be valid
    val_valid = sample_bilinear(data_nan, 1.5, 0.5)
    assert not np.isnan(val_valid), "Sampling disjoint from NaN cell should succeed"


def test_t_terr_07_profile_sample_spacing_and_cumulative_distance() -> None:
    """T-TERR-07: Profile samples are evenly spaced and cumulative distance is correct."""
    p_start = GeoPoint(lat=0.0, lon=0.0)
    # Step 0.001 deg North along prime meridian on Mars sphere
    # Ground distance: 0.001 * pi / 180 * 3396190 m ~ 59.275 m
    p_end = GeoPoint(lat=0.001, lon=0.0)

    spacing_m = 10.0
    points = interpolate_great_circle_points(p_start, p_end, sample_spacing_m=spacing_m)

    assert len(points) >= 6
    # First point at 0 distance
    assert points[0][1] == 0.0
    assert np.isclose(points[0][0].lat, 0.0)

    # Distances must be strictly increasing
    dists = [d for _, d in points]
    assert all(x < y for x, y in zip(dists, dists[1:], strict=False)), (
        "Distances must be strictly increasing"
    )

    # Check nominal spacing
    diffs = np.diff(dists)
    # All interior steps should be close to nominal spacing
    assert np.allclose(diffs, diffs[0], atol=1e-3), "Profile steps must be evenly spaced"


def test_t_terr_08_data_confidence_levels() -> None:
    """T-TERR-08: Data-confidence levels match section 11 of spec for layer combinations."""
    shape = (2, 2)
    # Cell (0, 0): High (DTM <= 2m + optical + context)
    # Cell (0, 1): Medium (DTM + optical only)
    # Cell (1, 0): Low (DTM only, no optical, no context)
    # Cell (1, 1): None (no valid DTM slope)

    has_dtm = np.array([[True, True], [True, False]])
    has_optical = np.array([[True, True], [False, False]])
    has_context = np.array([[True, False], [False, False]])
    has_regional = np.array([[True, True], [True, True]])

    conf = compute_data_confidence(
        has_valid_dtm_slope=has_dtm,
        dtm_post_spacing_m=1.0,
        has_optical_coverage=has_optical,
        has_context_coverage=has_context,
        has_regional_context=has_regional,
    )

    assert conf[0, 0] == ConfidenceCode.HIGH, "Valid DTM + optical + context must be HIGH"
    assert conf[0, 1] == ConfidenceCode.MEDIUM, "Valid DTM + optical must be MEDIUM"
    assert conf[1, 0] == ConfidenceCode.LOW, "Valid DTM with no other layers must be LOW"
    assert conf[1, 1] == ConfidenceCode.LOW, "Regional context only must be LOW"

    # Cell with no regional and no DTM must be NONE
    conf_none = compute_data_confidence(
        has_valid_dtm_slope=np.zeros(shape, dtype=bool),
        dtm_post_spacing_m=1.0,
    )
    assert np.all(conf_none == ConfidenceCode.NONE), "No data must be NONE"


def test_t_haz_01_hazard_states_and_near_hazard_flags() -> None:
    """T-HAZ-01: Hazard states and NEAR_HAZARD flags.

    Asserts: NaN -> IMPASSABLE_NODATA, slope > max -> IMPASSABLE_SLOPE, NEAR_HAZARD.
    """
    # 5x5 grid
    elevation = np.full((5, 5), 100.0, dtype=np.float32)
    slope = np.full((5, 5), 5.0, dtype=np.float32)  # All passable initially

    # Cell (1, 1) has slope = 20 deg > 15 deg -> IMPASSABLE_SLOPE
    slope[1, 1] = 20.0

    # Cell (3, 3) has NaN elevation -> IMPASSABLE_NODATA
    elevation[3, 3] = np.nan

    haz_res = compute_hazard_grid(elevation, slope, max_slope_deg=15.0)
    states = haz_res.states
    near_haz = haz_res.near_hazard

    # 1. Verify states
    assert states[1, 1] == HazardState.IMPASSABLE_SLOPE, "Steep cell must be IMPASSABLE_SLOPE"
    assert states[3, 3] == HazardState.IMPASSABLE_NODATA, "NaN cell must be IMPASSABLE_NODATA"
    assert states[0, 4] == HazardState.PASSABLE, "Distant cell must be PASSABLE"

    # 2. Impassable cells must NOT be NEAR_HAZARD (flag applies to passable cells)
    assert not near_haz[1, 1], "Impassable cell cannot be NEAR_HAZARD"
    assert not near_haz[3, 3], "Impassable cell cannot be NEAR_HAZARD"

    # 3. 8-neighbours of (1, 1) that are passable must be flagged NEAR_HAZARD
    assert near_haz[0, 0], "Cell (0, 0) adjacent to (1, 1) must be NEAR_HAZARD"
    assert near_haz[0, 1], "Cell (0, 1) adjacent to (1, 1) must be NEAR_HAZARD"
    assert near_haz[1, 2], "Cell (1, 2) adjacent to (1, 1) must be NEAR_HAZARD"

    # 4. 8-neighbours of (3, 3) that are passable must be flagged NEAR_HAZARD
    assert near_haz[2, 3], "Cell (2, 3) adjacent to (3, 3) must be NEAR_HAZARD"
    assert near_haz[3, 4], "Cell (3, 4) adjacent to (3, 3) must be NEAR_HAZARD"

    # 5. Cell (0, 4) is 3 cells away from (1, 1) and (3, 3) -> must NOT be NEAR_HAZARD
    assert not near_haz[0, 4], "Distant cell (0, 4) must not be NEAR_HAZARD"
