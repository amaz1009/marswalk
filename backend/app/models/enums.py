"""Enumerations defined in docs/API_CONTRACTS.md §2."""

from enum import Enum


class AssessmentStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class DataClass(str, Enum):
    MEASURED = "MEASURED"
    DERIVED = "DERIVED"
    MODEL = "MODEL"
    REFERENCE = "REFERENCE"
    ASSUMPTION = "ASSUMPTION"
    SAMPLE = "SAMPLE"
    AI_INTERPRETATION = "AI_INTERPRETATION"


class DatasetStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class DataType(str, Enum):
    ELEVATION = "ELEVATION"
    OPTICAL = "OPTICAL"
    THERMAL = "THERMAL"
    GEOLOGY = "GEOLOGY"
    MINERALOGY = "MINERALOGY"
    RADIATION = "RADIATION"
    SURFACE_IMAGE = "SURFACE_IMAGE"
    ICE = "ICE"
    DERIVED = "DERIVED"


class LayerKind(str, Enum):
    RASTER = "RASTER"
    VECTOR = "VECTOR"


class ValueStatus(str, Enum):
    OK = "OK"
    NO_COVERAGE = "NO_COVERAGE"
    UNAVAILABLE = "UNAVAILABLE"


class RouteObjective(str, Enum):
    LOWEST_RISK = "LOWEST_RISK"
    BALANCED = "BALANCED"
    MAX_SCIENCE = "MAX_SCIENCE"


class PlanStatus(str, Enum):
    OK = "OK"
    NO_FEASIBLE_ROUTE = "NO_FEASIBLE_ROUTE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TimelineKind(str, Enum):
    WALK = "WALK"
    WORK = "WORK"
    MARGIN = "MARGIN"
    RESERVE = "RESERVE"


class ContextStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class LlmMode(str, Enum):
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"


class AgentRunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SafetyCheckId(str, Enum):
    SLOPE_MAX = "SLOPE_MAX"
    HAZARD_INTERSECTION = "HAZARD_INTERSECTION"
    TERRAIN_DATA_COVERAGE = "TERRAIN_DATA_COVERAGE"
    EVA_DURATION = "EVA_DURATION"
    RETURN_RESERVE = "RETURN_RESERVE"
    ROUGHNESS = "ROUGHNESS"
    DISTANCE_FROM_BASE = "DISTANCE_FROM_BASE"


class ContextIndicatorId(str, Enum):
    RADIATION_CONTEXT = "RADIATION_CONTEXT"
    THERMAL_CONTEXT = "THERMAL_CONTEXT"
