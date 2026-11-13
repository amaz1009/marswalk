"""Region models implementing docs/API_CONTRACTS.md §3.4."""

from pydantic import BaseModel, Field

from app.models.enums import DataClass
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoBounds, GeoPoint


class ScienceTarget(BaseModel):
    """Identified scientific target or sampling location."""

    target_id: str = Field(..., description="Unique target identifier")
    name: str = Field(..., description="Human-readable target name")
    point: GeoPoint = Field(..., description="Target coordinate")
    rationale: str = Field(..., description="Scientific motivation and justification")
    data_class: DataClass = Field(
        ...,
        description="Scientific data classification",
    )
    evidence: list[EvidenceRef] = Field(
        ..., min_length=1, description="Supporting evidence references"
    )
    citation: str | None = Field(default=None, description="Scholarly publication citation")


class RegionSummary(BaseModel):
    """High-level summary of an exploration region."""

    region_id: str = Field(..., description="Unique region identifier")
    name: str = Field(..., description="Display title")
    description: str = Field(..., description="Regional setting description")
    science_objective: str = Field(..., description="Primary exploration objective")
    bounds: GeoBounds = Field(..., description="Bounding box")


class AnalysisSettings(BaseModel):
    """Geospatial processing and grid parameters for a region."""

    primary_dtm_dataset_id: str = Field(..., description="Base elevation model product ID")
    analysis_crs: str = Field(..., description="Local projected coordinate reference system")
    cell_size_m: float = Field(..., description="Grid cell resolution in metres", gt=0)
    max_grid_cells: int = Field(..., description="Upper bound on analysis grid size", gt=0)


class RegionDataStatus(BaseModel):
    """Count of available and unavailable datasets configured for a region."""

    datasets_available: int = Field(..., description="Number of accessible datasets", ge=0)
    datasets_unavailable: int = Field(
        ..., description="Number of missing or offline datasets", ge=0
    )


class RegionDetail(RegionSummary):
    """Detailed specification and configuration of a region."""

    analysis: AnalysisSettings = Field(..., description="Geospatial parameters")
    default_base: GeoPoint | None = Field(
        default=None, description="Suggested habitat/base location"
    )
    default_base_basis: str | None = Field(
        default=None, description="Rationale for default base location"
    )
    science_targets: list[ScienceTarget] = Field(..., description="Designated targets")
    layer_ids: list[str] = Field(..., description="Available layer IDs")
    data_status: RegionDataStatus = Field(..., description="Availability counts")
