"""EVA, routing, and safety models implementing docs/API_CONTRACTS.md §3.6 and §4.11-§4.14."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AssessmentStatus,
    PlanStatus,
    RouteObjective,
    SafetyCheckId,
    TimelineKind,
)
from app.models.evidence import AssumptionRecord, EvidenceRef
from app.models.geometry import GeoBounds, GeoPoint
from app.models.terrain import ContextIndicator, ProfilePoint


class EvaConfig(BaseModel):
    """Operational parameters and physiological constraints for an EVA traverse."""

    base_speed_kmh: float | None = Field(
        default=None,
        description="Nominal walking speed on flat terrain (km/h)",
        gt=0.0,
        le=6.0,
    )
    max_slope_deg: float | None = Field(
        default=None,
        description="Hard traversal slope limit in degrees",
        gt=0.0,
        le=30.0,
    )
    warning_slope_deg: float | None = Field(
        default=None,
        description="Caution slope threshold in degrees",
    )
    max_eva_hours: float | None = Field(
        default=None,
        description="Maximum permissible total EVA duration in hours",
        gt=0.0,
        le=10.0,
    )
    return_reserve_fraction: float | None = Field(
        default=None,
        description="Fraction of EVA time reserved for contingency return",
        ge=0.0,
        le=0.9,
    )
    traverse_time_margin: float | None = Field(
        default=None,
        description="Multiplicative safety margin applied to walking time",
        ge=1.0,
        le=3.0,
    )
    default_work_time_min: float | None = Field(
        default=None,
        description="Default scientific work duration per stop in minutes",
        ge=0.0,
    )
    max_distance_from_base_m: float | None = Field(
        default=None,
        description="Maximum allowable straight-line radius from habitat in metres",
        gt=0.0,
    )
    roughness_warning_m: float | None = Field(
        default=None,
        description="Residual surface roughness warning limit in metres",
        gt=0.0,
    )

    @model_validator(mode="after")
    def validate_slope_relationship(self) -> "EvaConfig":
        if self.warning_slope_deg is not None and self.max_slope_deg is not None:
            if self.warning_slope_deg >= self.max_slope_deg:
                raise ValueError(
                    f"warning_slope_deg ({self.warning_slope_deg}) must be strictly less than "
                    f"max_slope_deg ({self.max_slope_deg})"
                )
        return self


class Stop(BaseModel):
    """Intermediate waypoint or scientific stop on an EVA traverse."""

    stop_id: str = Field(..., description="Unique waypoint identifier")
    name: str = Field(..., description="Waypoint name")
    point: GeoPoint = Field(..., description="Coordinate location")
    work_time_min: float | None = Field(
        default=None,
        description="Work time override in minutes",
        ge=0.0,
    )
    target_id: str | None = Field(default=None, description="Associated ScienceTarget identifier")


class SafetyCheck(BaseModel):
    """Outcome of an individual constraint or safety rule evaluation."""

    check_id: SafetyCheckId = Field(..., description="Unique safety check identifier")
    critical: bool = Field(..., description="Whether failure of this check blocks the mission")
    status: AssessmentStatus = Field(..., description="Evaluation outcome status")
    value: float | None = Field(default=None, description="Observed or calculated parameter value")
    threshold: float | None = Field(default=None, description="Safety limit compared against")
    units: str | None = Field(default=None, description="Physical units")
    message: str = Field(..., description="Human-readable explanation of result")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="Supporting evidence")


class SafetyAssessment(BaseModel):
    """Aggregated safety evaluation across all critical and non-critical checks."""

    overall_status: AssessmentStatus = Field(..., description="Aggregated safety outcome")
    checks: list[SafetyCheck] = Field(
        ..., min_length=7, max_length=7, description="All 7 safety checks"
    )
    context: list[ContextIndicator] = Field(
        default_factory=list, description="Environmental context indicators"
    )
    disclaimer: str = Field(..., description="Mandatory safety disclaimer text")


class RouteLeg(BaseModel):
    """Traverse segment between two consecutive stops or bases."""

    from_label: str = Field(..., description="Origin label")
    to_label: str = Field(..., description="Destination label")
    path: list[GeoPoint] = Field(..., description="Ordered polyline vertices")
    horizontal_distance_m: float = Field(..., description="Planar distance in metres", ge=0.0)
    surface_distance_m: float = Field(..., description="Surface 3D distance in metres", ge=0.0)
    ascent_m: float = Field(..., description="Cumulative elevation gain in metres", ge=0.0)
    descent_m: float = Field(..., description="Cumulative elevation loss in metres", ge=0.0)
    walk_time_s: float = Field(..., description="Estimated nominal walking time in seconds", ge=0.0)


class TimelineEntry(BaseModel):
    """Time-budget allocation block within an EVA mission timeline."""

    kind: TimelineKind = Field(..., description="Activity category")
    label: str = Field(..., description="Description or leg/stop label")
    start_s: float = Field(..., description="Start offset from EVA initiation in seconds", ge=0.0)
    duration_s: float = Field(..., description="Duration of activity in seconds", ge=0.0)


class RouteTotals(BaseModel):
    """Integrated distance and time metrics for an entire route."""

    horizontal_distance_m: float = Field(..., description="Total planar distance in metres", ge=0.0)
    surface_distance_m: float = Field(..., description="Total surface distance in metres", ge=0.0)
    walk_time_s: float = Field(
        ..., description="Total walking time in seconds before margin", ge=0.0
    )
    margin_time_s: float = Field(..., description="Allocated safety margin time in seconds", ge=0.0)
    work_time_s: float = Field(..., description="Total scientific work duration in seconds", ge=0.0)
    total_time_s: float = Field(
        ..., description="Combined walk, margin, and work time in seconds", ge=0.0
    )
    time_available_s: float = Field(
        ..., description="Total permissible duration in seconds", gt=0.0
    )
    reserve_required_s: float = Field(
        ..., description="Required contingency reserve in seconds", ge=0.0
    )
    reserve_remaining_s: float = Field(..., description="Remaining unused reserve in seconds")


class StatSummary(BaseModel):
    """Statistical summary of terrain parameters along a traverse."""

    max: float | None = Field(default=None, description="Maximum observed value")
    mean: float | None = Field(default=None, description="Mean observed value")
    p95: float | None = Field(default=None, description="95th percentile value")
    units: str = Field(..., description="Physical units")


class Route(BaseModel):
    """Complete computed traverse path and evaluation profile."""

    route_id: str = Field(..., description="Unique route plan identifier")
    objective: RouteObjective = Field(..., description="Routing optimization profile")
    identical_to: str | None = Field(
        default=None, description="Identifier of duplicate route profile"
    )
    legs: list[RouteLeg] = Field(..., description="Ordered outbound and return segments")
    path: list[GeoPoint] = Field(..., description="Full concatenated polyline")
    elevation_profile: list[ProfilePoint] = Field(
        ..., description="Sampled elevation cross-section"
    )
    slope_stats: StatSummary = Field(..., description="Slope statistics in degrees")
    roughness_stats: StatSummary = Field(..., description="Roughness statistics in metres")
    fraction_above_warning_slope: float = Field(
        ...,
        description="Fraction of route exceeding warning slope (0-1)",
        ge=0.0,
        le=1.0,
    )
    max_distance_from_base_m: float = Field(
        ..., description="Farthest distance from base in metres", ge=0.0
    )
    timeline: list[TimelineEntry] = Field(..., description="Chronological schedule")
    totals: RouteTotals = Field(..., description="Total time and distance budget")
    safety: SafetyAssessment = Field(..., description="Safety check assessment")
    primary_coverage_fraction: float = Field(
        ...,
        description="Share of traverse covered by high-res DTM (0-1)",
        ge=0.0,
        le=1.0,
    )
    evidence: list[EvidenceRef] = Field(default_factory=list, description="Supporting evidence")
    limitations: list[str] = Field(default_factory=list, description="Route caveats")


class GridInfo(BaseModel):
    """Dimensions and spatial reference of the route planning raster grid."""

    analysis_crs: str = Field(..., description="Coordinate reference system")
    cell_size_m: float = Field(..., description="Grid cell resolution in metres", gt=0.0)
    rows: int = Field(..., description="Number of raster rows", gt=0)
    cols: int = Field(..., description="Number of raster columns", gt=0)


class EvaDefaultsResponse(BaseModel):
    """Default EVA operational configuration and parameter assumptions."""

    config: EvaConfig = Field(..., description="Effective default configuration")
    assumptions: list[AssumptionRecord] = Field(..., description="Supporting assumption records")


class OmittedObjective(BaseModel):
    """Record explaining why an optimization objective could not be generated."""

    objective: RouteObjective = Field(..., description="Omitted objective profile")
    reason: str = Field(..., description="Explanation for omission")


class RoutePlanRequest(BaseModel):
    """Input payload for multi-objective traverse optimization."""

    region_id: str = Field(..., description="Target exploration region")
    base: GeoPoint = Field(..., description="Traverse base or habitat start location")
    destination: GeoPoint = Field(..., description="Primary turnaround or destination point")
    stops: list[Stop] = Field(
        default_factory=list, max_length=8, description="Ordered intermediate science stops (0-8)"
    )
    objectives: list[RouteObjective] | None = Field(
        default=None, description="Requested profiles; defaults to all three"
    )
    eva_config: EvaConfig | None = Field(
        default=None, description="Traverse configuration overrides"
    )
    return_to_base: bool = Field(
        default=True, description="Whether route must return to base location"
    )


class RoutePlanResponse(BaseModel):
    """Optimization response containing generated routes across requested profiles."""

    plan_id: str = Field(..., description="Unique plan identifier with pln_ prefix")
    region_id: str = Field(..., description="Region identifier")
    plan_status: PlanStatus = Field(..., description="Overall planning outcome")
    blocking_reason: str | None = Field(
        default=None, description="Explanation when no feasible route is found"
    )
    routes: list[Route] = Field(default_factory=list, description="Computed feasible routes")
    omitted_objectives: list[OmittedObjective] = Field(
        default_factory=list, description="Omitted profiles"
    )
    eva_config: EvaConfig = Field(..., description="Effective configuration used")
    assumptions: list[AssumptionRecord] = Field(
        default_factory=list, description="Assumptions applied"
    )
    grid: GridInfo = Field(..., description="Analysis grid metrics")
    computed_at: datetime = Field(..., description="Computation timestamp in UTC")
    engine_version: str = Field(..., description="Routing engine version")


class EnvelopeRequest(BaseModel):
    """Request payload to compute the reachable walk-back safety envelope."""

    region_id: str = Field(..., description="Region identifier")
    base: GeoPoint = Field(..., description="Habitat base coordinate")
    eva_config: EvaConfig | None = Field(
        default=None, description="Optional configuration overrides"
    )


class EnvelopeResponse(BaseModel):
    """Reachability boundary and raster map of permissible traverse territory."""

    envelope_id: str = Field(..., description="Unique envelope identifier with env_ prefix")
    bounds: GeoBounds = Field(..., description="Geographic extent of envelope")
    image_png_base64: str = Field(..., description="Base64-encoded PNG coverage mask")
    reachable_area_km2: float = Field(
        ..., description="Total reachable surface area in square km", ge=0.0
    )
    max_reach_m: float = Field(
        ..., description="Maximum radial distance reachable from base in metres", ge=0.0
    )
    eva_config: EvaConfig = Field(..., description="Effective parameters used")
    assumptions: list[AssumptionRecord] = Field(
        default_factory=list, description="Parameter assumptions"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Envelope computation limitations"
    )
    computed_at: datetime = Field(..., description="Computation timestamp in UTC")
