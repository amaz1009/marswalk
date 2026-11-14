"""Data-confidence layer computation.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 11:
Per analysis cell:
- HIGH: Valid primary-DTM slope at <= 2 m post spacing, optical coverage,
  and thermal or geology coverage.
- MEDIUM: Valid DTM slope at any resolution and at least one other layer.
- LOW: Only regional context data, or DTM without any other layer.
- NONE: No valid terrain data.
"""

from enum import IntEnum
from typing import Optional

import numpy as np


class ConfidenceCode(IntEnum):
    """Integer codes for raster confidence encoding."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


def compute_data_confidence(
    has_valid_dtm_slope: np.ndarray,
    dtm_post_spacing_m: float,
    has_optical_coverage: Optional[np.ndarray] = None,
    has_context_coverage: Optional[np.ndarray] = None,
    has_regional_context: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Compute confidence level for each analysis cell.

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 11 table:
    - HIGH: Valid primary-DTM slope at <= 2 m post spacing, optical coverage,
            and thermal or geology coverage.
    - MEDIUM: Valid DTM slope at any resolution and at least one other layer.
    - LOW: Only regional context data, or DTM without any other layer.
    - NONE: No valid terrain data.

    Args:
        has_valid_dtm_slope: Boolean mask where primary DTM slope is valid.
        dtm_post_spacing_m: Primary DTM resolution in metres (e.g. 1.01 m).
        has_optical_coverage: Optional boolean mask of optical (ortho) coverage.
        has_context_coverage: Optional boolean mask of thermal/geology context.
        has_regional_context: Optional boolean mask of regional context (e.g. MOLA).

    Returns:
        2D uint8 numpy array with ConfidenceCode integer values (0=NONE, 1=LOW, 2=MEDIUM, 3=HIGH).
    """
    shape = has_valid_dtm_slope.shape

    optical = (
        has_optical_coverage if has_optical_coverage is not None else np.zeros(shape, dtype=bool)
    )
    context = (
        has_context_coverage if has_context_coverage is not None else np.zeros(shape, dtype=bool)
    )
    regional = (
        has_regional_context if has_regional_context is not None else np.zeros(shape, dtype=bool)
    )

    # Initialize to NONE
    confidence = np.full(shape, ConfidenceCode.NONE, dtype=np.uint8)

    # LOW: Only regional context data, or DTM without any other layer
    low_condition = (regional & ~has_valid_dtm_slope) | (has_valid_dtm_slope & ~optical & ~context)
    confidence[low_condition] = ConfidenceCode.LOW

    # MEDIUM: Valid DTM slope at any resolution and at least one other layer (optical or context)
    medium_condition = has_valid_dtm_slope & (optical | context)
    confidence[medium_condition] = ConfidenceCode.MEDIUM

    # HIGH: Valid primary-DTM slope at <= 2 m post spacing, optical coverage,
    # AND thermal/geology coverage (section 11)
    if dtm_post_spacing_m <= 2.0:
        high_condition = has_valid_dtm_slope & optical & context
        confidence[high_condition] = ConfidenceCode.HIGH

    return confidence
