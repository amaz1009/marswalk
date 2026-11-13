"""Shared models and enumerations implementing docs/API_CONTRACTS.md."""

from app.models.agents import (
    AgentAnalysisRequest,
    AgentAnalysisResponse,
    AgentResult,
    AgentSynthesis,
    Finding,
)
from app.models.datasets import (
    DatasetRecord,
    LayerInfo,
    Legend,
    LegendCategory,
    ProcessingStep,
    TemporalCoverage,
)
from app.models.enums import (
    AgentRunStatus,
    AssessmentStatus,
    ConfidenceLevel,
    ContextIndicatorId,
    ContextStatus,
    DataClass,
    DatasetStatus,
    DataType,
    LayerKind,
    LlmMode,
    PlanStatus,
    RouteObjective,
    SafetyCheckId,
    TimelineKind,
    ValueStatus,
)
from app.models.eva import (
    EnvelopeRequest,
    EnvelopeResponse,
    EvaConfig,
    EvaConfigOverride,
    EvaDefaultsResponse,
    GridInfo,
    OmittedObjective,
    Route,
    RouteLeg,
    RoutePlanRequest,
    RoutePlanResponse,
    RouteTotals,
    SafetyAssessment,
    SafetyCheck,
    StatSummary,
    Stop,
    TimelineEntry,
)
from app.models.evidence import AssumptionRecord, EvidenceRef
from app.models.geometry import GeoBounds, GeoPoint, normalize_longitude
from app.models.health import HealthResponse
from app.models.imagery import SurfaceImage
from app.models.mission import (
    MissionReport,
    MissionReportRequest,
    MissionState,
    ReportSection,
)
from app.models.regions import (
    AnalysisSettings,
    RegionDataStatus,
    RegionDetail,
    RegionSummary,
    ScienceTarget,
)
from app.models.sites import (
    CriterionScores,
    SiteCandidate,
    SiteEvaluation,
    SiteEvaluationRequest,
    SiteWeights,
)
from app.models.terrain import (
    ContextIndicator,
    LayerValue,
    PointInspection,
    ProfilePoint,
    ProfileRequest,
    ProfileResponse,
)

# Rebuild models with forward references
AgentAnalysisRequest.model_rebuild()
MissionState.model_rebuild()

__all__ = [
    # Enums
    "AssessmentStatus",
    "DataClass",
    "DatasetStatus",
    "DataType",
    "LayerKind",
    "ValueStatus",
    "RouteObjective",
    "PlanStatus",
    "TimelineKind",
    "ContextStatus",
    "ConfidenceLevel",
    "LlmMode",
    "AgentRunStatus",
    "SafetyCheckId",
    "ContextIndicatorId",
    # Geometry
    "GeoPoint",
    "GeoBounds",
    "normalize_longitude",
    # Evidence
    "EvidenceRef",
    "AssumptionRecord",
    # Datasets
    "TemporalCoverage",
    "ProcessingStep",
    "DatasetRecord",
    "LegendCategory",
    "Legend",
    "LayerInfo",
    # Regions
    "ScienceTarget",
    "RegionSummary",
    "AnalysisSettings",
    "RegionDataStatus",
    "RegionDetail",
    # Terrain
    "LayerValue",
    "ContextIndicator",
    "PointInspection",
    "ProfilePoint",
    "ProfileRequest",
    "ProfileResponse",
    # EVA
    "EvaConfig",
    "EvaConfigOverride",
    "Stop",
    "SafetyCheck",
    "SafetyAssessment",
    "RouteLeg",
    "TimelineEntry",
    "RouteTotals",
    "StatSummary",
    "Route",
    "GridInfo",
    "EvaDefaultsResponse",
    "OmittedObjective",
    "RoutePlanRequest",
    "RoutePlanResponse",
    "EnvelopeRequest",
    "EnvelopeResponse",
    # Imagery
    "SurfaceImage",
    # Sites
    "SiteCandidate",
    "SiteWeights",
    "CriterionScores",
    "SiteEvaluation",
    "SiteEvaluationRequest",
    # Agents
    "Finding",
    "AgentResult",
    "AgentSynthesis",
    "AgentAnalysisRequest",
    "AgentAnalysisResponse",
    # Mission
    "MissionState",
    "ReportSection",
    "MissionReportRequest",
    "MissionReport",
    # Health
    "HealthResponse",
]
