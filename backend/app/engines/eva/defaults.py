"""Default EVA physiological parameters and baseline assumption records.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 6.2 and docs/API_CONTRACTS.md section 3.6.
All parameter defaults and citations match spec section 6.2 and section 15.
"""

from app.models.enums import DataClass
from app.models.eva import EvaConfig, EvaConfigOverride, EvaDefaultsResponse
from app.models.evidence import AssumptionRecord

# Exact parameter defaults from docs/SCIENCE_AND_SAFETY_SPEC.md section 6.2
DEFAULT_BASE_SPEED_KMH: float = 2.7
DEFAULT_MAX_SLOPE_DEG: float = 15.0
DEFAULT_WARNING_SLOPE_DEG: float = 10.0
DEFAULT_MAX_EVA_HOURS: float = 6.0
DEFAULT_RETURN_RESERVE_FRACTION: float = 0.25
DEFAULT_TRAVERSE_TIME_MARGIN: float = 1.25
DEFAULT_WORK_TIME_MIN: float = 20.0
DEFAULT_MAX_DISTANCE_FROM_BASE_M: float = 2000.0
DEFAULT_ROUGHNESS_WARNING_M: float = 0.30


def get_default_eva_config() -> EvaConfig:
    """Return baseline EVA operational configuration."""
    return EvaConfig(
        base_speed_kmh=DEFAULT_BASE_SPEED_KMH,
        max_slope_deg=DEFAULT_MAX_SLOPE_DEG,
        warning_slope_deg=DEFAULT_WARNING_SLOPE_DEG,
        max_eva_hours=DEFAULT_MAX_EVA_HOURS,
        return_reserve_fraction=DEFAULT_RETURN_RESERVE_FRACTION,
        traverse_time_margin=DEFAULT_TRAVERSE_TIME_MARGIN,
        default_work_time_min=DEFAULT_WORK_TIME_MIN,
        max_distance_from_base_m=DEFAULT_MAX_DISTANCE_FROM_BASE_M,
        roughness_warning_m=DEFAULT_ROUGHNESS_WARNING_M,
    )


def get_default_assumption_records() -> list[AssumptionRecord]:
    """Return explicit assumption records for all nine default EvaConfig parameters.

    Classes and citation reference keys are taken directly from
    docs/SCIENCE_AND_SAFETY_SPEC.md section 6.2 and section 15.
    """
    return [
        AssumptionRecord(
            key="base_speed_kmh",
            value=DEFAULT_BASE_SPEED_KMH,
            units="km/h",
            data_class=DataClass.REFERENCE,
            basis=(
                "Apollo planners assumed 2.7 km/h average speed for walkbacks "
                "longer than one hour. Lunar data; Mars gravity differs."
            ),
            citation="JONES-GAITS",
        ),
        AssumptionRecord(
            key="max_slope_deg",
            value=DEFAULT_MAX_SLOPE_DEG,
            units="degrees",
            data_class=DataClass.REFERENCE,
            basis=(
                "A lunar walking-traverse planning study limits slopes to 15 degrees. Lunar data."
            ),
            citation="PENA2023",
        ),
        AssumptionRecord(
            key="warning_slope_deg",
            value=DEFAULT_WARNING_SLOPE_DEG,
            units="degrees",
            data_class=DataClass.REFERENCE,
            basis=(
                "The Apollo 14 climb of a ten-degree slope to Cone Crater was the most "
                "difficult Apollo walking traverse."
            ),
            citation="JONES1989",
        ),
        AssumptionRecord(
            key="max_eva_hours",
            value=DEFAULT_MAX_EVA_HOURS,
            units="hours",
            data_class=DataClass.ASSUMPTION,
            basis="Conservative relative to Apollo surface EVAs of about seven hours.",
            citation="ALSJ",
        ),
        AssumptionRecord(
            key="return_reserve_fraction",
            value=DEFAULT_RETURN_RESERVE_FRACTION,
            units="fraction",
            data_class=DataClass.ASSUMPTION,
            basis="Prototype planning margin. No validated Mars value.",
            citation=None,
        ),
        AssumptionRecord(
            key="traverse_time_margin",
            value=DEFAULT_TRAVERSE_TIME_MARGIN,
            units="factor",
            data_class=DataClass.ASSUMPTION,
            basis=(
                "A field evaluation of an EVA traverse planner found actual traverse times "
                "significantly longer than predicted. The factor value itself is an assumption."
            ),
            citation="GILKEY2011",
        ),
        AssumptionRecord(
            key="default_work_time_min",
            value=DEFAULT_WORK_TIME_MIN,
            units="minutes",
            data_class=DataClass.ASSUMPTION,
            basis="Placeholder science time per stop. Set per stop by the operator.",
            citation=None,
        ),
        AssumptionRecord(
            key="max_distance_from_base_m",
            value=DEFAULT_MAX_DISTANCE_FROM_BASE_M,
            units="metres",
            data_class=DataClass.REFERENCE,
            basis=(
                "The same lunar study restricts walking traverses to within 2 km of the lander. "
                "Lunar data."
            ),
            citation="PENA2023",
        ),
        AssumptionRecord(
            key="roughness_warning_m",
            value=DEFAULT_ROUGHNESS_WARNING_M,
            units="metres",
            data_class=DataClass.ASSUMPTION,
            basis=(
                "Uncalibrated. To be reviewed against the region's roughness distribution in "
                "WP-11. Reviewed in WP-11 against the Gale Mount Sharp HiRISE DTM roughness "
                "layer (native cells): 0.06% of valid cells exceed 0.30 m and the 99th "
                "percentile is 0.114 m, so this check rarely triggers; the value remains an "
                "uncalibrated assumption."
            ),
            citation=None,
        ),
    ]


def get_default_eva_response() -> EvaDefaultsResponse:
    """Return EvaDefaultsResponse combining baseline config and assumption records."""
    return EvaDefaultsResponse(
        config=get_default_eva_config(),
        assumptions=get_default_assumption_records(),
    )


def resolve_eva_config(override: EvaConfigOverride | None = None) -> EvaConfig:
    """Merge an optional EvaConfigOverride onto default EvaConfig values."""
    base = get_default_eva_config()
    if override is None:
        return base

    updates = override.model_dump(exclude_unset=True)
    return base.model_copy(update=updates)
