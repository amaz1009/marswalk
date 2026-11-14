"""Step cost formulation and profile weighting for EVA route optimization.

Implements the multi-criteria traversal cost function defined in
MARSWALK SCIENCE_AND_SAFETY_SPEC.md sections 7.2 and 7.3.
"""

from dataclasses import dataclass
from typing import Union

import numpy as np

from app.engines.eva.speed import compute_step_time
from app.engines.hazards.grid import HazardState
from app.models.enums import RouteObjective


@dataclass(frozen=True)
class ObjectiveWeights:
    """Weight coefficients for multi-objective route cost calculation.

    Attributes:
        w_s: Slope penalty weight (dimensionless).
        w_r: Roughness penalty weight (dimensionless).
        w_h: Hazard proximity penalty weight (dimensionless).
        w_sci: Science attraction weight (in [0.0, 0.5]).
    """

    w_s: float
    w_r: float
    w_h: float
    w_sci: float

    def __post_init__(self) -> None:
        if self.w_s < 0.0 or self.w_r < 0.0 or self.w_h < 0.0:
            raise ValueError("Risk weights (w_s, w_r, w_h) must be non-negative")
        if not (0.0 <= self.w_sci <= 0.5):
            raise ValueError(f"w_sci must be within [0.0, 0.5], got {self.w_sci}")


# Default profile weights defined in SCIENCE_AND_SAFETY_SPEC.md section 7.3 (ASSUMPTION)
PROFILE_WEIGHTS: dict[RouteObjective, ObjectiveWeights] = {
    RouteObjective.LOWEST_RISK: ObjectiveWeights(w_s=3.0, w_r=2.0, w_h=2.0, w_sci=0.0),
    RouteObjective.BALANCED: ObjectiveWeights(w_s=1.0, w_r=1.0, w_h=1.0, w_sci=0.25),
    RouteObjective.MAX_SCIENCE: ObjectiveWeights(w_s=0.5, w_r=0.5, w_h=1.0, w_sci=0.5),
}


def compute_normalized_roughness(
    roughness_m: Union[float, np.ndarray],
    roughness_warning_m: float,
) -> Union[float, np.ndarray]:
    """Compute normalized roughness rho in [0, 1].

    Formula:
        rho = min(roughness_m / roughness_warning_m, 2.0) / 2.0

    Args:
        roughness_m: Residual surface roughness in metres (float or ndarray).
        roughness_warning_m: Roughness warning threshold in metres.

    Returns:
        Normalized roughness value(s) in [0.0, 1.0].
    """
    if roughness_warning_m <= 0.0:
        raise ValueError("roughness_warning_m must be strictly positive")

    r = np.asarray(roughness_m, dtype=np.float64)
    # Clip negative to zero defensively
    r_pos = np.maximum(r, 0.0)
    norm = np.minimum(r_pos / roughness_warning_m, 2.0) / 2.0

    if np.isscalar(roughness_m):
        return float(norm.item())
    return norm


def precompute_cell_cost_factors(
    slope_deg: np.ndarray,
    roughness_m: np.ndarray,
    hazard_states: np.ndarray,
    weights: ObjectiveWeights,
    max_slope_deg: float,
    roughness_warning_m: float,
    near_hazard: np.ndarray | None = None,
    science_interest: np.ndarray | None = None,
) -> np.ndarray:
    """Precompute the static cell-dependent cost factor for all cells in a grid.

    The cost of moving from cell a to neighbour b is:
        cost(a -> b) = step_time(a -> b) * cell_cost_factor[b]

    where:
        cell_cost_factor[b] = (
            1.0
            + w_s * (slope_b / max_slope_deg)^2
            + w_r * rho_b
            + w_h * eta_b
        ) * (1.0 - w_sci * iota_b)

    Args:
        slope_deg: 2D array of slopes in degrees.
        roughness_m: 2D array of residual roughness in metres.
        hazard_states: 2D array of HazardState enum values or integer codes.
        weights: ObjectiveWeights instance for the selected profile.
        max_slope_deg: Hard slope threshold in degrees.
        roughness_warning_m: Caution roughness threshold in metres.
        near_hazard: Optional 2D boolean array of NEAR_HAZARD flags.
        science_interest: Optional 2D array of normalized science interest in [0, 1].

    Returns:
        2D float64 array of cell cost multiplier factors.
    """
    if max_slope_deg <= 0.0:
        raise ValueError("max_slope_deg must be strictly positive")
    if roughness_warning_m <= 0.0:
        raise ValueError("roughness_warning_m must be strictly positive")

    rows, cols = slope_deg.shape
    factors = np.ones((rows, cols), dtype=np.float64)

    # Slope term: w_s * (sigma_b / max_slope_deg)^2
    slope_ratio = np.clip(slope_deg / max_slope_deg, 0.0, 2.0)
    factors += weights.w_s * (slope_ratio**2)

    # Roughness term: w_r * rho_b
    rho = compute_normalized_roughness(roughness_m, roughness_warning_m)
    factors += weights.w_r * rho

    # Hazard proximity term: w_h * eta_b (eta_b = 1 if NEAR_HAZARD else 0)
    if near_hazard is not None:
        factors += weights.w_h * near_hazard.astype(np.float64)
    elif weights.w_h > 0.0:
        # Derive near_hazard if not provided
        impassable_mask = hazard_states != HazardState.PASSABLE
        pad_imp = np.pad(impassable_mask, 1, mode="constant", constant_values=False)
        is_near = (
            pad_imp[:-2, :-2]
            | pad_imp[:-2, 1:-1]
            | pad_imp[:-2, 2:]
            | pad_imp[1:-1, :-2]
            | pad_imp[1:-1, 2:]
            | pad_imp[2:, :-2]
            | pad_imp[2:, 1:-1]
            | pad_imp[2:, 2:]
        )
        is_passable = hazard_states == HazardState.PASSABLE
        factors += weights.w_h * (is_near & is_passable).astype(np.float64)

    # Science attraction term: (1.0 - w_sci * iota_b)
    if science_interest is not None and weights.w_sci > 0.0:
        clipped_sci = np.clip(science_interest, 0.0, 1.0)
        factors *= 1.0 - weights.w_sci * clipped_sci

    return factors


def compute_step_cost(
    delta_z: float,
    delta_d_h: float,
    cell_factor_b: float,
    base_speed_kmh: float,
) -> float:
    """Compute directional traversal cost from cell a to adjacent cell b.

    Args:
        delta_z: Elevation difference z_b - z_a in metres.
        delta_d_h: Horizontal step distance in metres.
        cell_factor_b: Precomputed static cost factor for cell b.
        base_speed_kmh: Base walking speed in km/h.

    Returns:
        Step cost (time-weighted, strictly positive).
    """
    step_time = compute_step_time(delta_z, delta_d_h, base_speed_kmh=base_speed_kmh)
    return float(step_time * cell_factor_b)
