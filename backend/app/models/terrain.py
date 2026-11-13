"""Terrain models implementing docs/API_CONTRACTS.md §3.5 and §4.9-§4.10."""

from pydantic import BaseModel, Field

from app.models.enums import (
    ConfidenceLevel,
    ContextIndicatorId,
    ContextStatus,
    DataClass,
    ValueStatus,
)
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoPoint


class LayerValue(BaseModel):
    """Inspected value for a specific layer at a geographic point."""

    layer_id: str = Field(..., description="Target layer identifier")
    value: float | str | None = Field(default=None, description="Sampled layer value")
    units: str | None = Field(default=None, description="Physical units")
    status: ValueStatus = Field(..., description="Sampling outcome status")
    data_class: DataClass = Field(..., description="Scientific classification")
    dataset_ids: list[str] = Field(default_factory=list, description="Source dataset IDs")
    native_resolution_m: float | None = Field(default=None, description="Native spatial resolution")


class ContextIndicator(BaseModel):
    """Environmental context indicator (e.g. ambient radiation or thermal conditions)."""

    indicator_id: ContextIndicatorId = Field(..., description="Indicator type")
    status: ContextStatus = Field(..., description="Data availability status")
    summary: str = Field(..., description="Plain language assessment")
    value: float | None = Field(default=None, description="Quantitative measurement if available")
    units: str | None = Field(default=None, description="Physical units")
    period: str | None = Field(
        default=None, description="Observation timeframe or diurnal sol phase"
    )
    data_class: DataClass = Field(..., description="Scientific classification")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="Supporting evidence")
    limitations: list[str] = Field(..., min_length=1, description="Caveats and limitations")


class PointInspection(BaseModel):
    """Complete multi-layer query response at a single coordinate."""

    region_id: str = Field(..., description="Region identifier")
    point: GeoPoint = Field(..., description="Sampled point coordinate")
    values: list[LayerValue] = Field(default_factory=list, description="Layer values")
    data_confidence: ConfidenceLevel = Field(..., description="Overall confidence level")
    context: list[ContextIndicator] = Field(default_factory=list, description="Context indicators")
    limitations: list[str] = Field(default_factory=list, description="Inspection caveats")


class ProfilePoint(BaseModel):
    """Sample point along an elevation and slope cross-section."""

    distance_m: float = Field(
        ..., description="Cumulative horizontal distance from profile start", ge=0.0
    )
    point: GeoPoint = Field(..., description="Point location")
    elevation_m: float | None = Field(default=None, description="Elevation in metres")
    slope_deg: float | None = Field(default=None, description="Local slope in degrees")


class ProfileRequest(BaseModel):
    """Request payload for terrain cross-section profiling."""

    region_id: str = Field(..., description="Region identifier")
    points: list[GeoPoint] = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Vertices defining the polyline path (2-200 points)",
    )
    sample_spacing_m: float | None = Field(
        default=None,
        description="Sample spacing along polyline; defaults to analysis cell size",
        gt=0.0,
    )


class ProfileResponse(BaseModel):
    """Cross-section profile response containing sampled points."""

    samples: list[ProfilePoint] = Field(..., description="Sampled profile points")
    total_horizontal_distance_m: float = Field(
        ..., description="Total polyline horizontal length in metres", ge=0.0
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Contributing elevation datasets"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Resolution and interpolation limitations"
    )
