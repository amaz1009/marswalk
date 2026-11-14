"""Safety evaluation framework, check evaluators, and assessment aggregation."""

from app.engines.safety.aggregate import (
    REQUIRED_SAFETY_CHECK_COUNT,
    aggregate_safety_status,
    build_safety_assessment,
)
from app.engines.safety.checks import (
    DTM_POST_SPACING_WARNING_THRESHOLD_M,
    RETURN_RESERVE_WARNING_FACTOR,
    ROUGHNESS_PERCENTILE,
    SAFETY_DISCLAIMER_TEXT,
    evaluate_distance_from_base,
    evaluate_eva_duration,
    evaluate_hazard_intersection,
    evaluate_return_reserve,
    evaluate_roughness,
    evaluate_slope_max,
    evaluate_terrain_data_coverage,
)
from app.engines.safety.context import (
    build_context_indicators,
    build_radiation_context_indicator,
    build_thermal_context_indicator,
)

__all__ = [
    "DTM_POST_SPACING_WARNING_THRESHOLD_M",
    "REQUIRED_SAFETY_CHECK_COUNT",
    "RETURN_RESERVE_WARNING_FACTOR",
    "ROUGHNESS_PERCENTILE",
    "SAFETY_DISCLAIMER_TEXT",
    "aggregate_safety_status",
    "build_context_indicators",
    "build_radiation_context_indicator",
    "build_safety_assessment",
    "build_thermal_context_indicator",
    "evaluate_distance_from_base",
    "evaluate_eva_duration",
    "evaluate_hazard_intersection",
    "evaluate_return_reserve",
    "evaluate_roughness",
    "evaluate_slope_max",
    "evaluate_terrain_data_coverage",
]
