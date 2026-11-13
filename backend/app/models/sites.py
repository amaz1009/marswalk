"""Site evaluation models implementing docs/API_CONTRACTS.md §4.17."""

from pydantic import BaseModel, Field, model_validator

from app.models.eva import EvaConfigOverride
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoPoint


class SiteCandidate(BaseModel):
    """Candidate landing or base site coordinate and evaluation radius."""

    site_id: str = Field(..., description="Unique site candidate identifier")
    point: GeoPoint = Field(..., description="Center coordinate of candidate site")
    radius_m: float = Field(..., description="Evaluation radius in metres", gt=0.0)


class SiteWeights(BaseModel):
    """Multi-criteria evaluation weighting factors (must sum to 1.0 ± 0.001)."""

    terrain: float = Field(..., description="Weight for slope and roughness", ge=0.0, le=1.0)
    human_safety: float = Field(..., description="Weight for human traverse safety", ge=0.0, le=1.0)
    science: float = Field(
        ..., description="Weight for proximity to science targets", ge=0.0, le=1.0
    )
    resources: float = Field(
        ..., description="Weight for proximity to potential in-situ resources", ge=0.0, le=1.0
    )
    accessibility: float = Field(
        ..., description="Weight for landing/traverse accessibility", ge=0.0, le=1.0
    )

    @model_validator(mode="after")
    def validate_sum(self) -> "SiteWeights":
        total = (
            self.terrain + self.human_safety + self.science + self.resources + self.accessibility
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"SiteWeights must sum to 1.0 ± 0.001 (got {total:.4f})")
        return self


class CriterionScores(BaseModel):
    """Scores for individual site evaluation criteria (0-100 or null if unevaluable)."""

    terrain: float | None = Field(
        default=None, description="Terrain score (0-100)", ge=0.0, le=100.0
    )
    human_safety: float | None = Field(
        default=None, description="Safety score (0-100)", ge=0.0, le=100.0
    )
    science: float | None = Field(
        default=None, description="Science score (0-100)", ge=0.0, le=100.0
    )
    resources: float | None = Field(
        default=None, description="Resources score (0-100)", ge=0.0, le=100.0
    )
    accessibility: float | None = Field(
        default=None, description="Accessibility score (0-100)", ge=0.0, le=100.0
    )


class SiteEvaluation(BaseModel):
    """Evaluation outcome and ranking for an individual site candidate."""

    site_id: str = Field(..., description="Candidate site identifier")
    point: GeoPoint = Field(..., description="Site coordinate")
    excluded: bool = Field(..., description="True if any hard safety constraint is violated")
    hard_constraint_violations: list[str] = Field(..., description="Violated hard constraints")
    criterion_scores: CriterionScores = Field(
        ..., description="Breakdown of individual criteria scores"
    )
    weighted_score: float | None = Field(
        default=None, description="Overall weighted composite score (0-100)"
    )
    rank: int | None = Field(default=None, description="Overall rank order (1 is highest)", ge=1)
    evidence: list[EvidenceRef] = Field(..., description="Supporting evidence references")
    uncertainties: list[str] = Field(..., description="Missing or unevaluable criteria notes")
    limitations: list[str] = Field(..., description="Evaluation caveats")


class SiteEvaluationRequest(BaseModel):
    """Input payload for multi-criteria site ranking."""

    region_id: str = Field(..., description="Region identifier")
    candidates: list[SiteCandidate] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of candidate locations (1-20)",
    )
    weights: SiteWeights | None = Field(
        default=None, description="Custom criteria weights; defaults to balanced"
    )
    eva_config: EvaConfigOverride | None = Field(
        default=None, description="Traverse configuration for reachability analysis"
    )
