"""Human EVA models and walking speed engines."""

from app.engines.eva.speed import (
    compute_step_time,
    walking_speed,
    walking_speed_ms,
)

__all__ = [
    "compute_step_time",
    "walking_speed",
    "walking_speed_ms",
]
