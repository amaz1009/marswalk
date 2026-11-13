"""Datasets and layers models implementing docs/API_CONTRACTS.md §3.3."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DataClass, DatasetStatus, DataType, LayerKind
from app.models.geometry import GeoBounds


class TemporalCoverage(BaseModel):
    """Observation period or time bounds of a dataset."""

    start: datetime | None = Field(default=None, description="Start timestamp in UTC")
    end: datetime | None = Field(default=None, description="End timestamp in UTC")
    description: str = Field(..., description="Summary of temporal extent")


class ProcessingStep(BaseModel):
    """Provenance record of a single pipeline transformation step."""

    step: str = Field(..., description="Pipeline stage identifier")
    tool: str = Field(..., description="Library and exact version")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    completed_at: datetime = Field(..., description="Timestamp of completion")


class DatasetRecord(BaseModel):
    """Metadata record for a primary or derived dataset product."""

    dataset_id: str = Field(..., description="Unique UPPERCASE snake_case product ID")
    name: str = Field(..., description="Human-readable title")
    mission: str = Field(..., description="Sponsoring mission")
    instrument: str = Field(..., description="Acquiring instrument")
    source_archive: str = Field(..., description="Publishing archive node or organization")
    source_url: str = Field(..., description="Landing page or download URL")
    product_ids: list[str] = Field(..., description="Source product identifiers")
    citation: str = Field(..., description="Full scholarly or archive citation")
    data_type: DataType = Field(..., description="Primary data kind")
    data_class: DataClass = Field(..., description="Classification category")
    units: str | None = Field(default=None, description="Physical units")
    source_crs: str = Field(..., description="WKT or PROJ string of source")
    source_conventions: str = Field(..., description="Latitude type and longitude direction")
    native_resolution_m: float | None = Field(
        default=None, description="Post spacing or resolution in metres"
    )
    temporal_coverage: TemporalCoverage = Field(..., description="Temporal coverage")
    coverage_bounds: GeoBounds | None = Field(default=None, description="Spatial bounding box")
    region_coverage_fraction: float | None = Field(
        default=None,
        description="Share of region covered (0-1)",
        ge=0.0,
        le=1.0,
    )
    status: DatasetStatus = Field(..., description="Availability status")
    status_reason: str | None = Field(default=None, description="Reason if not AVAILABLE")
    processing_steps: list[ProcessingStep] = Field(
        default_factory=list, description="Processing history"
    )
    processed_path: str | None = Field(default=None, description="Path relative to data directory")
    limitations: list[str] = Field(..., min_length=1, description="Known operational limitations")
    usage_note: str | None = Field(default=None, description="Licensing or usage guidelines")
    retrieved_at: datetime | None = Field(
        default=None, description="Download or verification timestamp"
    )

    @model_validator(mode="after")
    def validate_status_reason(self) -> "DatasetRecord":
        if self.status != DatasetStatus.AVAILABLE and not self.status_reason:
            raise ValueError("status_reason is required when dataset status is not AVAILABLE")
        return self


class LegendCategory(BaseModel):
    """Discrete category mapping for categorical layers."""

    value: float | str | int = Field(..., description="Category code or pixel value")
    label: str = Field(..., description="Descriptive category label")
    color: str = Field(..., description="Hex or CSS color representation")


class Legend(BaseModel):
    """Colormap or categorical rendering specification."""

    colormap: str = Field(..., description="Colormap name or categorical marker")
    vmin: float | None = Field(
        default=None, description="Minimum data value for raster color mapping"
    )
    vmax: float | None = Field(
        default=None, description="Maximum data value for raster color mapping"
    )
    units: str | None = Field(default=None, description="Display units")
    categories: list[LegendCategory] | None = Field(default=None, description="Discrete categories")


class LayerInfo(BaseModel):
    """Client layer manifest entry for map visualization."""

    layer_id: str = Field(..., description="Unique lowercase snake_case layer identifier")
    name: str = Field(..., description="Human-readable layer name")
    kind: LayerKind = Field(..., description="Raster or vector layer")
    data_type: DataType = Field(..., description="Data kind")
    status: DatasetStatus = Field(..., description="Operational status")
    status_reason: str | None = Field(default=None, description="Reason when unavailable")
    dataset_ids: list[str] = Field(..., description="Contributing dataset product IDs")
    data_class: DataClass = Field(..., description="Scientific classification")
    bounds: GeoBounds | None = Field(default=None, description="Spatial extent")
    native_resolution_m: float | None = Field(
        default=None, description="Native resolution in metres"
    )
    legend: Legend | None = Field(default=None, description="Rendering legend")
    image_url: str | None = Field(default=None, description="Relative URL to PNG image overlay")
    features_url: str | None = Field(
        default=None, description="Relative URL to GeoJSON vector features"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Layer caveats and limitations"
    )
