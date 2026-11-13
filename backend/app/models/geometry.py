"""Geometry models implementing docs/API_CONTRACTS.md §3.1."""

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_longitude(lon: float) -> float:
    """Validate and normalize longitude to [0, 360) east-positive degrees.

    Inputs in [-180, 0) are normalized by adding 360.
    Inputs outside [-180, 360) are rejected.
    """
    if lon < -180.0 or lon >= 360.0:
        raise ValueError(f"Longitude {lon} is outside allowable range [-180, 360)")
    if -180.0 <= lon < 0.0:
        lon += 360.0
    # Handle floating point -0.0
    if lon == 0.0:
        lon = 0.0
    return lon


class GeoPoint(BaseModel):
    """Planetocentric coordinate on Mars."""

    lat: float = Field(
        ...,
        description="Planetocentric latitude in degrees [-90, 90]",
        ge=-90.0,
        le=90.0,
    )
    lon: float = Field(
        ...,
        description="East-positive longitude in degrees [0, 360)",
    )

    @field_validator("lon")
    @classmethod
    def validate_and_normalize_lon(cls, v: float) -> float:
        return normalize_longitude(v)


class GeoBounds(BaseModel):
    """Geographic bounding box on Mars."""

    lat_min: float = Field(
        ...,
        description="Minimum latitude in degrees [-90, 90]",
        ge=-90.0,
        le=90.0,
    )
    lat_max: float = Field(
        ...,
        description="Maximum latitude in degrees [-90, 90]",
        ge=-90.0,
        le=90.0,
    )
    lon_min: float = Field(
        ...,
        description="Minimum longitude in degrees [0, 360)",
    )
    lon_max: float = Field(
        ...,
        description="Maximum longitude in degrees [0, 360)",
    )

    @field_validator("lon_min", "lon_max")
    @classmethod
    def validate_and_normalize_lon(cls, v: float) -> float:
        return normalize_longitude(v)

    @model_validator(mode="after")
    def validate_lat_bounds(self) -> "GeoBounds":
        if self.lat_min >= self.lat_max:
            raise ValueError(
                f"lat_min ({self.lat_min}) must be strictly less than lat_max ({self.lat_max})"
            )
        return self
