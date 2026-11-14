"""Hazard grid computation engine.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 5:
- Each analysis cell is in exactly one state:
    IMPASSABLE_NODATA: Elevation or slope is NaN, or cell fails validity rule in section 4.4
    IMPASSABLE_SLOPE: Slope > max_slope_deg (default 15.0 deg from section 6.2 / [PENA2023])
    IMPASSABLE_EXCLUSION: Inside exclusion polygon (P2)
    PASSABLE: Otherwise
- NEAR_HAZARD flag: A passable cell is flagged NEAR_HAZARD if it lies within one cell
  (8-neighbour) of an impassable cell. Feeds hazard cost in routing (section 7.2).
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import numpy as np


class HazardState(IntEnum):
    """Integer codes for cell hazard classification per spec section 5."""

    PASSABLE = 0
    IMPASSABLE_NODATA = 1
    IMPASSABLE_SLOPE = 2
    IMPASSABLE_EXCLUSION = 3


@dataclass(frozen=True)
class HazardGridResult:
    """Output of hazard grid calculation."""

    states: np.ndarray  # 2D uint8 array with HazardState values
    near_hazard: np.ndarray  # 2D bool array with NEAR_HAZARD flags


def compute_hazard_grid(
    elevation: np.ndarray,
    slope: np.ndarray,
    max_slope_deg: float = 15.0,
    exclusion_mask: Optional[np.ndarray] = None,
    valid_mask: Optional[np.ndarray] = None,
) -> HazardGridResult:
    """Compute hazard classification and NEAR_HAZARD flags for the analysis grid.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 5:
    1. Priority 1: IMPASSABLE_NODATA if elevation is NaN, slope is NaN, or valid_mask is False.
    2. Priority 2: IMPASSABLE_EXCLUSION if inside exclusion polygon.
    3. Priority 3: IMPASSABLE_SLOPE if slope > max_slope_deg.
    4. Default: PASSABLE.
    5. NEAR_HAZARD: Passable cell within 1 cell (8-neighbour) of ANY impassable cell.

    Args:
        elevation: 2D float32 array of elevations.
        slope: 2D float32 array of slopes in degrees.
        max_slope_deg: Maximum passable slope in degrees (default 15.0).
        exclusion_mask: Optional 2D boolean array where True indicates an exclusion zone.
        valid_mask: Optional 2D boolean array where True indicates cell meets
            validity rule (section 4.4).

    Returns:
        HazardGridResult containing 'states' (uint8) and 'near_hazard' (bool).
    """
    shape = elevation.shape
    states = np.full(shape, HazardState.PASSABLE, dtype=np.uint8)

    # 1. IMPASSABLE_NODATA: elevation is NaN, slope is NaN, or fails validity rule
    is_nodata = np.isnan(elevation) | np.isnan(slope)
    if valid_mask is not None:
        is_nodata = is_nodata | (~valid_mask)
    states[is_nodata] = HazardState.IMPASSABLE_NODATA

    # 2. IMPASSABLE_EXCLUSION: inside exclusion zone (P2)
    if exclusion_mask is not None:
        is_exclusion = exclusion_mask & (~is_nodata)
        states[is_exclusion] = HazardState.IMPASSABLE_EXCLUSION

    # 3. IMPASSABLE_SLOPE: slope > max_slope_deg
    is_steep = (~is_nodata) & (slope > max_slope_deg)
    if exclusion_mask is not None:
        is_steep = is_steep & (~exclusion_mask)
    states[is_steep] = HazardState.IMPASSABLE_SLOPE

    # 4. NEAR_HAZARD flag:
    # A passable cell is flagged NEAR_HAZARD if it lies within one cell (8-neighbour)
    # of an impassable cell.
    impassable_mask = states != HazardState.PASSABLE

    # 8-neighbourhood dilation using pure numpy slicing
    pad_imp = np.pad(impassable_mask, 1, mode="constant", constant_values=False)

    # Shift in all 8 directions
    neigh_impassable = (
        pad_imp[:-2, :-2]  # NW
        | pad_imp[:-2, 1:-1]  # N
        | pad_imp[:-2, 2:]  # NE
        | pad_imp[1:-1, :-2]  # W
        | pad_imp[1:-1, 2:]  # E
        | pad_imp[2:, :-2]  # SW
        | pad_imp[2:, 1:-1]  # S
        | pad_imp[2:, 2:]  # SE
    )

    passable_mask = states == HazardState.PASSABLE
    near_hazard = passable_mask & neigh_impassable

    return HazardGridResult(states=states, near_hazard=near_hazard)
