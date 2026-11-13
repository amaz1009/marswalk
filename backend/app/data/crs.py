"""CRS validation, format detection, and coordinate convention extraction.

Implements requirements from docs/SCIENCE_AND_SAFETY_SPEC.md section 2.1-2.3 and
docs/SYSTEM_ARCHITECTURE.md section 7.2:
- Parses raster CRS using pyproj.CRS (never fragile substring search)
- Checks observed ellipsoid properties (semi_major_metre, semi_minor_metre)
- Restricts accepted bodies strictly to Mars IAU 2000 sphere (R = 3,396,190 m)
  and Mars IAU 2000 ellipsoid (a = 3,396,190 m, b = 3,376,200 m)
- Classifies latitude type directly from ellipsoid properties and explicit caller declaration:
  sphere = planetocentric by construction;
  ellipsoid = requires explicit declared_latitude_type ('PLANETOCENTRIC' or 'PLANETOGRAPHIC')
  because an ellipsoid CRS definition alone cannot distinguish latitude conventions
- Enforces the latitude rule: explicit formula conversion between planetographic
  and planetocentric latitude for ellipsoid sources; never rely on PROJ ballpark
  transformations
- Rejects any CRS that cannot be verified with certainty as CRSValidationError
"""

from typing import Any

import pyproj
from pyproj.exceptions import CRSError

from app.utils.coordinates import (
    planetocentric_to_planetographic,
    planetographic_to_planetocentric,
)

# Accepted Mars IAU 2000 datum parameters (metres, tolerance 0.5 m)
MARS_SEMI_MAJOR_M = 3396190.0
MARS_SPHERE_SEMI_MINOR_M = 3396190.0
MARS_ELLIPSOID_SEMI_MINOR_M = 3376200.0
TOLERANCE_M = 0.5

VALID_LATITUDE_TYPES = frozenset({"PLANETOCENTRIC", "PLANETOGRAPHIC"})


class CRSValidationError(ValueError):
    """Raised when raster CRS is missing, unreadable, or invalid."""


def inspect_raster_crs(
    crs_input: Any,
    driver_name: str | None = None,
    declared_latitude_type: str | None = None,
) -> dict[str, Any]:
    """Inspect and classify CRS definition using pyproj object model.

    Parameters:
    - crs_input: WKT string, PROJ string, or pyproj-compatible CRS input
    - driver_name: optional rasterio driver name
    - declared_latitude_type: explicit latitude type for ellipsoid CRS
      ('PLANETOCENTRIC' or 'PLANETOGRAPHIC'). If None for an ellipsoid CRS,
      raises CRSValidationError because latitude convention cannot be determined
      from the CRS alone.

    Returns a dictionary detailing:
    - is_valid: bool
    - is_projected: bool
    - is_geographic: bool
    - datum_type: 'SPHERE' or 'ELLIPSOID'
    - latitude_type: 'PLANETOCENTRIC' or 'PLANETOGRAPHIC'
    - source_conventions: documented convention string
    - raw_crs: input string or WKT
    """
    if crs_input is None:
        raise CRSValidationError("No readable CRS found in raster header metadata.")

    if isinstance(crs_input, str) and not crs_input.strip():
        raise CRSValidationError("No readable CRS found in raster header metadata.")

    if declared_latitude_type is not None and declared_latitude_type not in VALID_LATITUDE_TYPES:
        raise CRSValidationError(
            f"Invalid declared_latitude_type '{declared_latitude_type}': "
            f"must be one of {sorted(VALID_LATITUDE_TYPES)}."
        )

    try:
        crs = pyproj.CRS.from_user_input(crs_input)
    except CRSError as exc:
        raise CRSValidationError(f"Invalid or unparseable CRS definition: {exc}") from exc
    except Exception as exc:
        raise CRSValidationError(f"Could not construct CRS object: {exc}") from exc

    ellipsoid = crs.ellipsoid
    if ellipsoid is None:
        raise CRSValidationError("CRS has no defined planetary ellipsoid.")

    semi_major = ellipsoid.semi_major_metre
    semi_minor = ellipsoid.semi_minor_metre

    if semi_major is None or semi_minor is None:
        raise CRSValidationError("CRS ellipsoid has undefined semi-major or semi-minor axes.")

    crs_name = getattr(crs, "name", None) or str(crs_input)

    # Validate that semi-major matches Mars equatorial radius (3396190 m)
    if abs(semi_major - MARS_SEMI_MAJOR_M) > TOLERANCE_M:
        raise CRSValidationError(
            f"CRS '{crs_name}' has semi-major={semi_major} m, semi-minor={semi_minor} m; "
            f"does not match Mars radius {MARS_SEMI_MAJOR_M} m."
        )

    # Classify Sphere vs Ellipsoid
    is_sphere = abs(semi_minor - MARS_SPHERE_SEMI_MINOR_M) <= TOLERANCE_M
    is_ellipsoid = abs(semi_minor - MARS_ELLIPSOID_SEMI_MINOR_M) <= TOLERANCE_M

    if not is_sphere and not is_ellipsoid:
        raise CRSValidationError(
            f"CRS '{crs_name}' has semi-major={semi_major} m, semi-minor={semi_minor} m; "
            f"is neither Mars IAU 2000 sphere ({MARS_SEMI_MAJOR_M} m) nor ellipsoid "
            f"({MARS_SEMI_MAJOR_M} m, {MARS_ELLIPSOID_SEMI_MINOR_M} m)."
        )

    is_projected = crs.is_projected
    is_geographic = crs.is_geographic

    # Check axis units
    axis_units = [axis.unit_name for axis in crs.axis_info]
    if is_projected:
        valid_projected_units = {"metre", "meter"}
        if not any(u in valid_projected_units for u in axis_units):
            raise CRSValidationError(f"Projected CRS must use metre units, got {axis_units}.")

    # Determine latitude type
    if is_sphere:
        datum_type = "SPHERE"
        # On a sphere, planetocentric and planetographic latitudes are identical by construction
        latitude_type = "PLANETOCENTRIC"
        convention_desc = (
            "Mars IAU 2000 sphere (R=3396190 m), planetocentric latitude, East-positive longitude"
        )
    else:
        datum_type = "ELLIPSOID"
        if declared_latitude_type is None:
            raise CRSValidationError(
                "latitude type not declared; cannot be determined from the CRS"
            )
        latitude_type = declared_latitude_type
        if latitude_type == "PLANETOGRAPHIC":
            convention_desc = (
                "Mars IAU 2000 ellipsoid (a=3396190, b=3376200), declared planetographic latitude, "
                "requires explicit formula conversion to planetocentric"
            )
        else:
            convention_desc = (
                "Mars IAU 2000 ellipsoid (a=3396190, b=3376200), declared planetocentric latitude"
            )

    return {
        "is_valid": True,
        "is_projected": is_projected,
        "is_geographic": is_geographic,
        "datum_type": datum_type,
        "latitude_type": latitude_type,
        "source_conventions": convention_desc,
        "raw_crs": crs.to_wkt(),
    }


def convert_source_latitude_if_needed(lat: float, crs_info: dict[str, Any]) -> float:
    """Enforce SCIENCE_AND_SAFETY_SPEC.md section 2.3 latitude rule.

    If the source is ellipsoid-based and planetographic, explicitly convert
    to planetocentric latitude using the spec closed formula in app.utils.coordinates.
    Never rely on PROJ ballpark conversions.
    """
    if (
        crs_info.get("datum_type") == "ELLIPSOID"
        and crs_info.get("latitude_type") == "PLANETOGRAPHIC"
    ):
        return planetographic_to_planetocentric(lat)
    return lat


def convert_internal_to_source_latitude_if_needed(
    lat_centric: float, crs_info: dict[str, Any]
) -> float:
    """Convert internal planetocentric latitude back to source planetographic if needed."""
    if (
        crs_info.get("datum_type") == "ELLIPSOID"
        and crs_info.get("latitude_type") == "PLANETOGRAPHIC"
    ):
        return planetocentric_to_planetographic(lat_centric)
    return lat_centric
