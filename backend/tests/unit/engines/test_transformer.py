"""Unit tests for raster CRS introspection and coordinate transformer builder.

Verifies:
- Standard Martian equirectangular CRS builds valid MarsCoordinateTransformer.
- Invalid projections (UTM, Mercator) raise ValueError.
- Non-zero lat_ts or lat_0 raise ValueError.
- Non-spherical ellipsoids raise ValueError.
- B1 finding: PROJ defaulting missing lon_0 to 0 is tested and recorded.
- Lat/lon round trip within one pixel.
"""

import math

import pytest
from pyproj import CRS
from rasterio.transform import Affine

from app.engines.routing.transformer import build_transformer_from_crs
from app.utils.coordinates import MarsCoordinateTransformer


def test_valid_mars_equirectangular_crs() -> None:
    """Standard Gale Crater Equirectangular Mars CRS constructs valid transformer."""
    wkt = (
        'PROJCS["EQUIRECTANGULAR MARS",'
        'GEOGCS["GCS_MARS",'
        'DATUM["D_MARS",SPHEROID["MARS_localRadius",3396190,0]],'
        'PRIMEM["Reference_Meridian",0],'
        'UNIT["degree",0.0174532925199433]],'
        'PROJECTION["Equirectangular"],'
        'PARAMETER["latitude_of_origin",0],'
        'PARAMETER["central_meridian",137.3],'
        'PARAMETER["standard_parallel_1",0],'
        'PARAMETER["false_easting",0],'
        'PARAMETER["false_northing",0],'
        'UNIT["metre",1]]'
    )
    transformer = build_transformer_from_crs(wkt)
    assert isinstance(transformer, MarsCoordinateTransformer)
    assert math.isclose(transformer.center_lon, 137.3, abs_tol=1e-6)
    assert math.isclose(transformer.center_lat, 0.0, abs_tol=1e-6)
    assert math.isclose(transformer.radius, 3396190.0, abs_tol=1e-3)


def test_non_eqc_projection_raises_value_error() -> None:
    """Non-equirectangular projection raises ValueError."""
    utm_crs = "+proj=utm +zone=32 +datum=WGS84 +units=m"
    with pytest.raises(ValueError, match="Unsupported projection"):
        build_transformer_from_crs(utm_crs)


def test_non_zero_lat_ts_or_lat_0_raises_value_error() -> None:
    """Non-zero standard parallel or latitude of origin raises ValueError."""
    crs_bad_ts = "+proj=eqc +lat_ts=15 +lat_0=0 +lon_0=137.3 +R=3396190 +units=m"
    with pytest.raises(ValueError, match="Unsupported lat_ts"):
        build_transformer_from_crs(crs_bad_ts)

    crs_bad_0 = "+proj=eqc +lat_ts=0 +lat_0=10 +lon_0=137.3 +R=3396190 +units=m"
    with pytest.raises(ValueError, match="Unsupported lat_0"):
        build_transformer_from_crs(crs_bad_0)


def test_non_spherical_ellipsoid_raises_value_error() -> None:
    """Ellipsoid with a != b raises ValueError per §2.1 spherical requirement."""
    crs_ellipsoid = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=137.3 +a=3396190 +b=3376200 +units=m"
    with pytest.raises(ValueError, match="Non-spherical ellipsoid detected"):
        build_transformer_from_crs(crs_ellipsoid)


def test_b1_observation_missing_lon_0_indistinguishable_from_zero() -> None:
    """Record observed B1 finding: PROJ defaults absent lon_0 to 0.0 across introspected views."""
    synth_no_lon0 = "+proj=eqc +lat_ts=0 +lat_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m"
    crs = CRS.from_user_input(synth_no_lon0)

    # 1. crs.to_dict() has lon_0 = 0
    assert crs.to_dict().get("lon_0") == 0

    # 2. coordinate_operation parameter shows 0.0
    found_param = False
    if crs.coordinate_operation:
        for p in crs.coordinate_operation.params:
            if "origin" in p.name.lower() or "meridian" in p.name.lower():
                assert math.isclose(p.value, 0.0, abs_tol=1e-6)
                found_param = True
    assert found_param

    # Transformer builds with center_lon 0.0
    transformer = build_transformer_from_crs(synth_no_lon0)
    assert transformer.center_lon == 0.0


def test_round_trip_lat_lon_to_pixel_to_lat_lon() -> None:
    """Round-trip lat/lon -> projected m -> pixel -> projected m -> lat/lon matches within 1 mm."""
    transformer = MarsCoordinateTransformer(center_lon=137.3, center_lat=0.0)
    # HiRISE transform at Gale
    transform = Affine(
        1.0117467945795, 0.0, -3620.0300310056555, 0.0, -1.0117467945795, -279807.6836691456
    )

    orig_lat, orig_lon = -4.75, 137.28
    x_m, y_m = transformer.transform(orig_lon, orig_lat)

    inv_tf = ~transform
    col_float, row_float = inv_tf @ (x_m, y_m)

    # Convert back to projected coordinates from exact pixel float
    x_rec, y_rec = transform @ (col_float, row_float)
    assert math.isclose(x_m, x_rec, abs_tol=1e-4)
    assert math.isclose(y_m, y_rec, abs_tol=1e-4)

    lon_rec, lat_rec = transformer.inverse_transform(x_rec, y_rec)
    assert math.isclose(orig_lat, lat_rec, abs_tol=1e-7)
    assert math.isclose(orig_lon, lon_rec, abs_tol=1e-7)
