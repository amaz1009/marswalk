"""Raster CRS introspection and coordinate transformer builder.

Implements pure function to construct MarsCoordinateTransformer from raster CRS.
Per Part B1 findings:
    An absent lon_0 in a PROJ string is INDISTINGUISHABLE from lon_0 = 0 in
    crs.to_dict(), WKT and coordinate_operation.params because PROJ populates
    default lon_0 = 0 when omitted. This module introspects the parameters
    and enforces strict validation.
"""

from typing import Any

from pyproj import CRS

from app.utils.coordinates import MarsCoordinateTransformer


def build_transformer_from_crs(crs_input: Any) -> MarsCoordinateTransformer:
    """Build a MarsCoordinateTransformer from a raster CRS.

    Validates that:
    1. Projection is Equidistant Cylindrical / Equirectangular ('eqc').
    2. lat_ts == 0 (latitude of true scale / first standard parallel).
    3. lat_0 == 0 (latitude of natural origin).
    4. Spheroid is spherical: semi-major == semi-minor (a == b).
    5. lon_0 is introspectable from the CRS parameters.

    Limitation:
        As established in AresNav WP-11 Part B1 measurements, PROJ automatically
        supplies lon_0 = 0.0 when a proj string lacks an explicit central meridian.
        Therefore, an omitted lon_0 cannot be distinguished from an explicit lon_0 = 0.
        Callers must provide rasters carrying well-formed spatial references with an
        introspectable central meridian. No fallback to region.center_lon is permitted.

    Args:
        crs_input: Any object convertible via pyproj.crs.CRS.from_user_input
            (rasterio.crs.CRS, pyproj.crs.CRS, PROJ string, or WKT string).

    Returns:
        MarsCoordinateTransformer configured with center_lat=0.0, center_lon=lon_0,
        and the CRS spherical radius.

    Raises:
        ValueError: If CRS is invalid, non-spherical, unsupported projection,
            or if required parameters are missing or non-zero.
    """
    try:
        crs = CRS.from_user_input(crs_input)
    except Exception as exc:
        raise ValueError(f"Invalid or unparseable CRS input: {exc}") from exc

    # Check projection
    crs_dict = crs.to_dict()
    proj = crs_dict.get("proj", "")
    if not proj and crs.coordinate_operation:
        method_name = crs.coordinate_operation.method_name.lower()
        if "equidistant cylindrical" in method_name or "equirectangular" in method_name:
            proj = "eqc"

    if proj != "eqc":
        raise ValueError(
            f"Unsupported projection '{proj}'. Only Equidistant Cylindrical ('eqc') "
            f"is supported for AresNav terrain routing."
        )

    # Validate lat_ts == 0 and lat_0 == 0
    lat_ts = float(crs_dict.get("lat_ts", 0.0))
    lat_0 = float(crs_dict.get("lat_0", 0.0))
    if abs(lat_ts) > 1e-6:
        raise ValueError(f"Unsupported lat_ts={lat_ts}. Must be 0 for standard equirectangular.")
    if abs(lat_0) > 1e-6:
        raise ValueError(f"Unsupported lat_0={lat_0}. Must be 0 for standard equirectangular.")

    # Validate spheroid / sphere (a == b)
    if crs.ellipsoid is None:
        raise ValueError("CRS lacks an introspectable ellipsoid/spheroid definition.")

    a = float(crs.ellipsoid.semi_major_metre)
    b = float(crs.ellipsoid.semi_minor_metre)
    if abs(a - b) > 1e-3:
        raise ValueError(
            f"Non-spherical ellipsoid detected (a={a}, b={b}). MarsCoordinateTransformer "
            f"requires a spherical reference (a == b) per SCIENCE_AND_SAFETY_SPEC.md §2.1."
        )

    # Introspect lon_0
    lon_0 = crs_dict.get("lon_0")
    if lon_0 is None and crs.coordinate_operation:
        for p in crs.coordinate_operation.params:
            p_name = p.name.lower()
            if "longitude of natural origin" in p_name or "central_meridian" in p_name:
                lon_0 = p.value
                break

    if lon_0 is None:
        raise ValueError(
            "Central meridian ('lon_0' / 'Longitude of natural origin') could not be "
            "introspected from raster CRS. Fallback to region.center_lon is prohibited."
        )

    return MarsCoordinateTransformer(
        center_lat=0.0,
        center_lon=float(lon_0),
        radius=float(a),
    )
