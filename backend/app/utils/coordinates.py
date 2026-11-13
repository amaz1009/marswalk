"""Coordinate definitions, normalisation, and conversions for Mars.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.1–§2.3 and §2.5.
All constants are from IAU 2000 Mars definitions.
Uses Mars datums only; no terrestrial coordinate systems.
"""

import math

# IAU 2000 Mars constants (docs/SCIENCE_AND_SAFETY_SPEC.md §2.1)
MARS_SPHERE_RADIUS_M: float = 3_396_190.0
MARS_EQUATORIAL_RADIUS_M: float = 3_396_190.0
MARS_POLAR_RADIUS_M: float = 3_376_200.0

# Ellipsoid axis ratio squared (b^2 / a^2)
_B2_OVER_A2: float = (MARS_POLAR_RADIUS_M / MARS_EQUATORIAL_RADIUS_M) ** 2
_A2_OVER_B2: float = 1.0 / _B2_OVER_A2

# Inverse flattening 1/f = a / (a - b)
MARS_INVERSE_FLATTENING: float = MARS_EQUATORIAL_RADIUS_M / (
    MARS_EQUATORIAL_RADIUS_M - MARS_POLAR_RADIUS_M
)

# Mars 2000 Sphere WKT definition (docs/SCIENCE_AND_SAFETY_SPEC.md §2.1)
MARS_SPHERE_WKT: str = """GEOGCRS["Mars (2000) - Sphere",
    DATUM["Mars (2000) - Sphere",
        ELLIPSOID["Mars (2000) - Sphere", 3396190, 0,
            LENGTHUNIT["metre", 1.0]]
    ],
    PRIMEM["Reference Meridian", 0.0,
        ANGLEUNIT["degree", 0.0174532925199433]
    ],
    CS[ellipsoidal, 2],
        AXIS["Latitude (lat)", north, ORDER[1]],
        AXIS["Longitude (lon)", east, ORDER[2]],
        ANGLEUNIT["degree", 0.0174532925199433]
]"""

# Mars 2000 Ellipsoid WKT definition (docs/SCIENCE_AND_SAFETY_SPEC.md §2.1)
MARS_ELLIPSOID_WKT: str = f"""GEOGCRS["Mars (2000) - Ellipsoid",
    DATUM["Mars (2000) - Ellipsoid",
        ELLIPSOID["Mars (2000) - Ellipsoid", 3396190, {MARS_INVERSE_FLATTENING:.13f},
            LENGTHUNIT["metre", 1.0]]
    ],
    PRIMEM["Reference Meridian", 0.0,
        ANGLEUNIT["degree", 0.0174532925199433]
    ],
    CS[ellipsoidal, 2],
        AXIS["Latitude (lat)", north, ORDER[1]],
        AXIS["Longitude (lon)", east, ORDER[2]],
        ANGLEUNIT["degree", 0.0174532925199433]
]"""


def validate_latitude(lat: float) -> None:
    """Validate planetocentric or planetographic latitude in degrees.

    Must be finite and within [-90.0, 90.0].
    """
    if math.isnan(lat) or math.isinf(lat):
        raise ValueError(f"Latitude must be a finite number, got {lat}")
    if lat < -90.0 or lat > 90.0:
        raise ValueError(f"Latitude {lat} is outside allowable range [-90, 90]")


def validate_longitude(lon: float) -> None:
    """Validate longitude against source bounds [-180.0, 360.0) per §2.2.

    Must be finite and within [-180.0, 360.0).
    """
    if math.isnan(lon) or math.isinf(lon):
        raise ValueError(f"Longitude must be a finite number, got {lon}")
    if lon < -180.0 or lon >= 360.0:
        raise ValueError(f"Longitude {lon} is outside allowable range [-180, 360)")


def validate_coordinates(lat: float, lon: float) -> None:
    """Validate both latitude and longitude."""
    validate_latitude(lat)
    validate_longitude(lon)


def normalize_longitude(lon: float) -> float:
    """Normalize any longitude angle to east-positive [0, 360) degrees.

    Handles mathematical wrapping via modulo 360:
    360 -> 0, -90 -> 270, 450 -> 90, -180 -> 180, -0.0 -> 0.0.
    """
    if math.isnan(lon) or math.isinf(lon):
        raise ValueError(f"Longitude must be a finite number, got {lon}")
    normalized = lon % 360.0
    if normalized == 0.0:
        normalized = 0.0
    return normalized


def west_to_east_longitude(lon_west: float) -> float:
    """Convert west-positive longitude to east-positive longitude in [0, 360).

    Formula (docs/SCIENCE_AND_SAFETY_SPEC.md §2.2):
    lon_east = (360 - lon_west) mod 360
    """
    if math.isnan(lon_west) or math.isinf(lon_west):
        raise ValueError(f"Longitude must be a finite number, got {lon_west}")
    lon_east = (360.0 - lon_west) % 360.0
    if lon_east == 0.0:
        lon_east = 0.0
    return lon_east


def east_to_west_longitude(lon_east: float) -> float:
    """Convert east-positive longitude to west-positive longitude in [0, 360).

    Inverts west_to_east_longitude: (360 - lon_east) mod 360.
    """
    if math.isnan(lon_east) or math.isinf(lon_east):
        raise ValueError(f"Longitude must be a finite number, got {lon_east}")
    lon_west = (360.0 - lon_east) % 360.0
    if lon_west == 0.0:
        lon_west = 0.0
    return lon_west


def planetographic_to_planetocentric(lat_deg: float) -> float:
    """Convert planetographic latitude to planetocentric latitude on IAU 2000 Mars ellipsoid.

    Formula (docs/SCIENCE_AND_SAFETY_SPEC.md §2.3):
    tan(lat_centric) = (b^2 / a^2) * tan(lat_graphic)
    Equator (0°) and poles (±90°) remain identical.
    """
    validate_latitude(lat_deg)
    if lat_deg == 0.0 or abs(lat_deg) == 90.0:
        return lat_deg
    rad_graphic = math.radians(lat_deg)
    rad_centric = math.atan(_B2_OVER_A2 * math.tan(rad_graphic))
    return math.degrees(rad_centric)


def planetocentric_to_planetographic(lat_deg: float) -> float:
    """Convert planetocentric latitude to planetographic latitude on IAU 2000 Mars ellipsoid.

    Formula (docs/SCIENCE_AND_SAFETY_SPEC.md §2.3):
    tan(lat_graphic) = (a^2 / b^2) * tan(lat_centric)
    Equator (0°) and poles (±90°) remain identical.
    """
    validate_latitude(lat_deg)
    if lat_deg == 0.0 or abs(lat_deg) == 90.0:
        return lat_deg
    rad_centric = math.radians(lat_deg)
    rad_graphic = math.atan(_A2_OVER_B2 * math.tan(rad_centric))
    return math.degrees(rad_graphic)


def build_mars_equirectangular_wkt(
    center_lat: float = 0.0,
    center_lon: float = 0.0,
    false_easting: float = 0.0,
    false_northing: float = 0.0,
) -> str:
    """Build WKT string for Mars Equirectangular projected analysis CRS.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.5.
    """
    return f"""PROJCRS["Mars (2000) / Equirectangular",
    BASEGEOGCRS["Mars (2000) - Sphere",
        DATUM["Mars (2000) - Sphere",
            ELLIPSOID["Mars (2000) - Sphere", 3396190, 0,
                LENGTHUNIT["metre", 1.0]]
        ],
        PRIMEM["Reference Meridian", 0.0,
            ANGLEUNIT["degree", 0.0174532925199433]
        ]
    ],
    CONVERSION["Equirectangular",
        METHOD["Equidistant Cylindrical"],
        PARAMETER["Latitude of 1st standard parallel", {center_lat},
            ANGLEUNIT["degree", 0.0174532925199433]],
        PARAMETER["Longitude of natural origin", {center_lon},
            ANGLEUNIT["degree", 0.0174532925199433]],
        PARAMETER["False easting", {false_easting},
            LENGTHUNIT["metre", 1.0]],
        PARAMETER["False northing", {false_northing},
            LENGTHUNIT["metre", 1.0]]
    ],
    CS[Cartesian, 2],
        AXIS["Easting (x)", east, ORDER[1], LENGTHUNIT["metre", 1.0]],
        AXIS["Northing (y)", north, ORDER[2], LENGTHUNIT["metre", 1.0]]
]"""


class MarsCoordinateTransformer:
    """Transformation helper between Mars internal geographic CRS and projected analysis CRS.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md §2.5 with explicit latitude handling (§2.3).
    Follows pyproj 'always_xy=True' convention: coordinates are passed and returned as
    (x, y) or (lon, lat) where the horizontal/easting/longitude axis is first.
    """

    def __init__(
        self,
        center_lat: float = 0.0,
        center_lon: float = 0.0,
        false_easting: float = 0.0,
        false_northing: float = 0.0,
        radius: float = MARS_SPHERE_RADIUS_M,
    ) -> None:
        validate_latitude(center_lat)
        validate_longitude(center_lon)
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.false_easting = false_easting
        self.false_northing = false_northing
        self.radius = radius

    @property
    def wkt(self) -> str:
        """WKT specification of this projected analysis CRS."""
        return build_mars_equirectangular_wkt(
            center_lat=self.center_lat,
            center_lon=self.center_lon,
            false_easting=self.false_easting,
            false_northing=self.false_northing,
        )

    def transform(
        self, lon: float, lat: float, is_planetographic: bool = False
    ) -> tuple[float, float]:
        """Transform geographic coordinates (lon, lat) to projected (x, y) metres.

        If is_planetographic is True, explicitly converts planetographic latitude to
        planetocentric latitude before projection (avoiding the PROJ ballpark trap).

        Returns:
            tuple[float, float]: (x, y) in metres (always_xy=True ordering).
        """
        validate_latitude(lat)
        validate_longitude(lon)

        # Explicit planetographic handling per §2.3
        if is_planetographic:
            lat = planetographic_to_planetocentric(lat)

        phi = math.radians(lat)
        phi_0 = math.radians(self.center_lat)

        # Longitude difference wrapped to (-180, 180]
        dlon_deg = (lon - self.center_lon + 180.0) % 360.0 - 180.0
        if dlon_deg == -180.0:
            dlon_deg = 180.0
        dlon_rad = math.radians(dlon_deg)

        x = self.radius * dlon_rad * math.cos(phi_0) + self.false_easting
        y = self.radius * (phi - phi_0) + self.false_northing
        return x, y

    def inverse_transform(
        self, x: float, y: float, to_planetographic: bool = False
    ) -> tuple[float, float]:
        """Inverse transform projected (x, y) metres to geographic (lon, lat) in degrees.

        If to_planetographic is True, converts resulting planetocentric latitude to
        planetographic latitude.

        Returns:
            tuple[float, float]: (lon, lat) in degrees (always_xy=True ordering).
        """
        if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
            raise ValueError(f"Projected coordinates must be finite, got x={x}, y={y}")

        phi_0 = math.radians(self.center_lat)
        cos_phi_0 = math.cos(phi_0)
        if cos_phi_0 == 0.0:
            raise ValueError(f"Standard parallel {self.center_lat}° has zero cosine; cannot invert")

        phi = phi_0 + (y - self.false_northing) / self.radius
        dlon_rad = (x - self.false_easting) / (self.radius * cos_phi_0)

        lat = math.degrees(phi)
        lon = normalize_longitude(self.center_lon + math.degrees(dlon_rad))

        validate_latitude(lat)

        if to_planetographic:
            lat = planetocentric_to_planetographic(lat)

        return lon, lat

    def round_trip(
        self, lon: float, lat: float, is_planetographic: bool = False
    ) -> tuple[float, float]:
        """Round-trip coordinates (lon, lat) -> (x, y) -> (lon, lat)."""
        x, y = self.transform(lon, lat, is_planetographic=is_planetographic)
        return self.inverse_transform(x, y, to_planetographic=is_planetographic)
