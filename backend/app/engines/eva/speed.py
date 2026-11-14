"""Human walking-speed model for planetary EVA planning.

Implements the walking speed model on slopes following Tobler's hiking function shape
[TOBLER1993], scaled so that flat-ground speed equals base_speed_kmh per MARSWALK
SCIENCE_AND_SAFETY_SPEC.md sections 6.2, 6.3, and 6.4.
"""

from typing import Union

import numpy as np


def walking_speed(
    gradient: Union[float, np.ndarray],
    base_speed_kmh: float = 2.7,
) -> Union[float, np.ndarray]:
    """Compute walking speed on a slope gradient in km/h.

    The model is:
        v(S) = v_0 * exp(-3.5 * (|S + 0.05| - 0.05))

    where:
        S = delta_z / delta_d_h (signed: positive uphill, negative downhill)
        v_0 = base_speed_kmh on flat ground (default 2.7 km/h)

    Maximum speed occurs on a gentle downhill slope S = -0.05 (-2.86 deg),
    reaching v_0 * exp(0.175) ~= 1.19125 * v_0.

    Args:
        gradient: Slope gradient S = delta_z / delta_d_h (signed float or ndarray).
        base_speed_kmh: Base walking speed on flat terrain in km/h (default 2.7).

    Returns:
        Walking speed in km/h (float or ndarray matching gradient shape).
    """
    if base_speed_kmh <= 0.0:
        raise ValueError(f"base_speed_kmh must be strictly positive, got {base_speed_kmh}")

    grad = np.asarray(gradient, dtype=np.float64)
    exponent = -3.5 * (np.abs(grad + 0.05) - 0.05)
    speed = base_speed_kmh * np.exp(exponent)

    if np.isscalar(gradient):
        return float(speed.item())
    return speed


def walking_speed_ms(
    gradient: Union[float, np.ndarray],
    base_speed_kmh: float = 2.7,
) -> Union[float, np.ndarray]:
    """Compute walking speed on a slope gradient in m/s.

    Converts walking_speed(...) from km/h to m/s by dividing by 3.6.

    Args:
        gradient: Slope gradient S = delta_z / delta_d_h (signed float or ndarray).
        base_speed_kmh: Base walking speed on flat terrain in km/h (default 2.7).

    Returns:
        Walking speed in m/s (float or ndarray matching gradient shape).
    """
    spd_kmh = walking_speed(gradient=gradient, base_speed_kmh=base_speed_kmh)
    return spd_kmh / 3.6


def compute_step_time(
    delta_z: Union[float, np.ndarray],
    delta_d_h: Union[float, np.ndarray],
    base_speed_kmh: float = 2.7,
) -> Union[float, np.ndarray]:
    """Compute traversal time in seconds for a step between adjacent cells.

    The step traversal time is:
        delta_d_s = sqrt(delta_d_h^2 + delta_z^2)
        v_ms = walking_speed(delta_z / delta_d_h, base_speed_kmh) / 3.6
        t = delta_d_s / v_ms

    Args:
        delta_z: Elevation difference z_target - z_source in metres (signed).
        delta_d_h: Horizontal distance in metres (strictly positive).
        base_speed_kmh: Base walking speed on flat terrain in km/h (default 2.7).

    Returns:
        Step traversal time in seconds.
    """
    dz = np.asarray(delta_z, dtype=np.float64)
    dh = np.asarray(delta_d_h, dtype=np.float64)

    if np.any(dh <= 0.0):
        raise ValueError("delta_d_h must be strictly positive")

    gradient = dz / dh
    speed_ms = walking_speed_ms(gradient=gradient, base_speed_kmh=base_speed_kmh)
    slope_dist = np.sqrt(dh * dh + dz * dz)
    step_time = slope_dist / speed_ms

    if np.isscalar(delta_z) and np.isscalar(delta_d_h):
        return float(step_time.item())
    return step_time
