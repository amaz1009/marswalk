"""Human EVA models, walking speed engines, and timeline calculations."""

from app.engines.eva.defaults import (
    DEFAULT_BASE_SPEED_KMH,
    DEFAULT_MAX_DISTANCE_FROM_BASE_M,
    DEFAULT_MAX_EVA_HOURS,
    DEFAULT_MAX_SLOPE_DEG,
    DEFAULT_RETURN_RESERVE_FRACTION,
    DEFAULT_ROUGHNESS_WARNING_M,
    DEFAULT_TRAVERSE_TIME_MARGIN,
    DEFAULT_WARNING_SLOPE_DEG,
    DEFAULT_WORK_TIME_MIN,
    get_default_assumption_records,
    get_default_eva_config,
    get_default_eva_response,
    resolve_eva_config,
)
from app.engines.eva.speed import (
    compute_step_time,
    walking_speed,
    walking_speed_ms,
)
from app.engines.eva.timeline import compute_eva_timeline

__all__ = [
    "DEFAULT_BASE_SPEED_KMH",
    "DEFAULT_MAX_DISTANCE_FROM_BASE_M",
    "DEFAULT_MAX_EVA_HOURS",
    "DEFAULT_MAX_SLOPE_DEG",
    "DEFAULT_RETURN_RESERVE_FRACTION",
    "DEFAULT_ROUGHNESS_WARNING_M",
    "DEFAULT_TRAVERSE_TIME_MARGIN",
    "DEFAULT_WARNING_SLOPE_DEG",
    "DEFAULT_WORK_TIME_MIN",
    "compute_eva_timeline",
    "compute_step_time",
    "get_default_assumption_records",
    "get_default_eva_config",
    "get_default_eva_response",
    "resolve_eva_config",
    "walking_speed",
    "walking_speed_ms",
]
