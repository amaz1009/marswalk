"""Safety check evaluation engine for human planetary EVA traverses.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 9.1.
All seven safety checks are evaluated in fixed order.
Missing, NaN, or non-computable data strictly evaluates to AssessmentStatus.UNKNOWN,
never PASS.
Threshold sources are recorded explicitly as config, spec, or ASSUMPTION.
"""

import math
from typing import Sequence

import numpy as np

from app.models.enums import AssessmentStatus, SafetyCheckId
from app.models.eva import EvaConfig, SafetyCheck
from app.models.evidence import EvidenceRef

# ---------------------------------------------------------------------------
# Named Threshold Constants and Spec Rules (Spec section 9.1)
# ---------------------------------------------------------------------------

# Factor applied to (time_available - reserve_required) for reserve warning (Spec section 9.1)
# Source: spec section 9.1 rule: "WARNING if value > 0.9 * threshold"
RETURN_RESERVE_WARNING_FACTOR: float = 0.9

# Percentile of path roughness evaluated against roughness_warning_m (Spec section 9.1)
# Source: spec section 9.1 rule: "95th percentile roughness on path (m)"
ROUGHNESS_PERCENTILE: float = 95.0

# Max primary DTM post spacing permissible before raising data coverage warning (Spec section 9.1)
# Source: spec section 9.1 rule: "WARNING if the primary DTM post spacing is > 2 m"
DTM_POST_SPACING_WARNING_THRESHOLD_M: float = 2.0

# Standardized limitation statements for each safety check (Spec section 9.1)
SLOPE_LIMITATION_TEXT: str = (
    "Limitation: Obstacles smaller than approximately 3x DTM post spacing may not be resolved."
)
HAZARD_LIMITATION_TEXT: str = (
    "Limitation: Hazard map reflects classified slope/roughness/exclusion zones; "
    "unmapped micro-hazards may exist."
)
COVERAGE_LIMITATION_TEXT: str = (
    "Limitation: Coverage check verifies primary DTM only; secondary or interpolated "
    "context is unverified."
)
DURATION_LIMITATION_TEXT: str = (
    "Limitation: Reference walking speeds are based on Apollo lunar data; "
    "Mars suit mobility and metabolic costs are unmodeled."
)
RESERVE_LIMITATION_TEXT: str = (
    "Limitation: Return reserve fraction is an operational planning baseline, "
    "uncalibrated for Martian terrain emergencies."
)
ROUGHNESS_LIMITATION_TEXT: str = (
    "Limitation: Residual roughness is an uncalibrated proxy for rock obstacles; "
    "actual rock distribution is not directly resolved."
)
DISTANCE_LIMITATION_TEXT: str = (
    "Limitation: Walkback distance limit is an Apollo lunar reference analog; "
    "Mars suit endurance limits are unvalidated."
)

# Exact prototype safety assessment disclaimer from docs/SCIENCE_AND_SAFETY_SPEC.md section 14.1
SAFETY_DISCLAIMER_TEXT: str = (
    "AresNav is a research and planning prototype. Results are computational "
    "assessments under stated assumptions and are not a certified astronaut safety analysis."
)


def evaluate_slope_max(
    path_slopes: Sequence[float] | np.ndarray | None,
    config: EvaConfig,
    analysis_cell_size_m: float | None = None,
) -> SafetyCheck:
    """Evaluate SLOPE_MAX check against caution and hard limits (Spec section 9.1).

    Rule:
        - UNKNOWN if path_slopes is missing, empty, or contains any NaN.
        - BLOCKED if max slope > config.max_slope_deg (strictly greater).
        - WARNING if max slope > config.warning_slope_deg (strictly greater).
        - PASS otherwise.
    """
    if analysis_cell_size_m is not None:
        slope_limitation = (
            "Limitation: Obstacles smaller than approximately 3x DTM post spacing may not be "
            f"resolved. Evaluated using conservative block-max slope on "
            f"{analysis_cell_size_m:.2f} m analysis grid."
        )
    else:
        slope_limitation = SLOPE_LIMITATION_TEXT

    evidence = [
        EvidenceRef(
            source_type="reference",
            source_id="config.max_slope_deg",
            detail=f"Limit: {config.max_slope_deg} deg (REFERENCE PENA2023, spec section 6.2)",
        ),
        EvidenceRef(
            source_type="reference",
            source_id="config.warning_slope_deg",
            detail=f"Limit: {config.warning_slope_deg} deg (REFERENCE JONES1989, spec section 6.2)",
        ),
    ]

    if path_slopes is None or len(path_slopes) == 0:
        return SafetyCheck(
            check_id=SafetyCheckId.SLOPE_MAX,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=float(config.max_slope_deg),
            units="degrees",
            message=f"Slope data unavailable along traverse. {slope_limitation}",
            evidence=evidence,
        )

    arr = np.asarray(path_slopes, dtype=np.float64)
    if np.any(np.isnan(arr)) or np.any(~np.isfinite(arr)):
        return SafetyCheck(
            check_id=SafetyCheckId.SLOPE_MAX,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=float(config.max_slope_deg),
            units="degrees",
            message=(
                f"Slope values along path contain NaN or unmeasured cells. {slope_limitation}"
            ),
            evidence=evidence,
        )

    val = float(np.max(arr))
    max_thresh = float(config.max_slope_deg)
    warn_thresh = float(config.warning_slope_deg)

    if val > max_thresh:
        status = AssessmentStatus.BLOCKED
        msg = (
            f"Maximum slope {val:.2f} deg exceeds hard traversal limit of "
            f"{max_thresh:.1f} deg. {slope_limitation}"
        )
    elif val > warn_thresh:
        status = AssessmentStatus.WARNING
        msg = (
            f"Maximum slope {val:.2f} deg exceeds caution threshold of "
            f"{warn_thresh:.1f} deg. {slope_limitation}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"Maximum slope {val:.2f} deg is within caution threshold of "
            f"{warn_thresh:.1f} deg. {slope_limitation}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.SLOPE_MAX,
        critical=True,
        status=status,
        value=val,
        threshold=max_thresh,
        units="degrees",
        message=msg,
        evidence=evidence,
    )


def evaluate_hazard_intersection(
    impassable_cells_count: int | None,
) -> SafetyCheck:
    """Evaluate HAZARD_INTERSECTION check against impassable cells (Spec section 9.1).

    Rule:
        - UNKNOWN if hazard grid is unavailable or count is None.
        - BLOCKED if impassable_cells_count > 0.
        - PASS otherwise.
    """
    evidence = [
        EvidenceRef(
            source_type="engine",
            source_id="engines.hazards",
            detail="Hard safety constraint (spec section 5 and section 9.1)",
        )
    ]

    if impassable_cells_count is None:
        return SafetyCheck(
            check_id=SafetyCheckId.HAZARD_INTERSECTION,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=0.0,
            units="cells",
            message=(
                "Hazard classification grid unavailable along traverse path. "
                f"{HAZARD_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    val = float(impassable_cells_count)
    if val > 0.0:
        status = AssessmentStatus.BLOCKED
        msg = (
            f"Traverse path intersects {impassable_cells_count} impassable hazard cells. "
            f"{HAZARD_LIMITATION_TEXT}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"Traverse path does not intersect any impassable hazard cells. "
            f"{HAZARD_LIMITATION_TEXT}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.HAZARD_INTERSECTION,
        critical=True,
        status=status,
        value=val,
        threshold=0.0,
        units="cells",
        message=msg,
        evidence=evidence,
    )


def evaluate_terrain_data_coverage(
    primary_coverage_fraction: float | None,
    primary_dtm_post_spacing_m: float | None = 1.0,
) -> SafetyCheck:
    """Evaluate TERRAIN_DATA_COVERAGE check (Spec section 9.1).

    Rule:
        - UNKNOWN if coverage fraction is None or NaN.
        - WARNING if value < 1.0.
        - WARNING if primary DTM post spacing > 2.0 m (spec section 9.1 rule).
        - PASS otherwise.
    """
    evidence = [
        EvidenceRef(
            source_type="reference",
            source_id="spec.post_spacing_threshold",
            detail="Threshold: 2.0 m post-spacing limit (spec section 9.1)",
        )
    ]

    if primary_coverage_fraction is None or not math.isfinite(primary_coverage_fraction):
        return SafetyCheck(
            check_id=SafetyCheckId.TERRAIN_DATA_COVERAGE,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=1.0,
            units="fraction",
            message=(
                "Terrain data coverage fraction could not be determined. "
                f"{COVERAGE_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    val = float(primary_coverage_fraction)
    post_spacing = (
        float(primary_dtm_post_spacing_m) if primary_dtm_post_spacing_m is not None else 1.0
    )

    if val < 1.0:
        status = AssessmentStatus.WARNING
        msg = (
            f"Traverse has incomplete primary DTM coverage ({val * 100.0:.1f}% covered). "
            f"Portions of traverse lack high-resolution terrain validation. "
            f"{COVERAGE_LIMITATION_TEXT}"
        )
    elif post_spacing > DTM_POST_SPACING_WARNING_THRESHOLD_M:
        status = AssessmentStatus.WARNING
        msg = (
            f"Primary DTM post spacing is {post_spacing:.2f} m, which exceeds "
            f"the {DTM_POST_SPACING_WARNING_THRESHOLD_M:.1f} m fidelity threshold. "
            f"{COVERAGE_LIMITATION_TEXT}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"Full primary DTM coverage ({val * 100.0:.1f}%) along entire traverse path "
            f"with native post spacing {post_spacing:.2f} m. {COVERAGE_LIMITATION_TEXT}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.TERRAIN_DATA_COVERAGE,
        critical=True,
        status=status,
        value=val,
        threshold=1.0,
        units="fraction",
        message=msg,
        evidence=evidence,
    )


def evaluate_eva_duration(
    total_time_s: float | None,
    config: EvaConfig,
    return_to_base: bool,
) -> SafetyCheck:
    """Evaluate EVA_DURATION check against total permissible hours (Spec section 9.1).

    Rule:
        - UNKNOWN if total_time_s is None or NaN.
        - If return_to_base is False:
            - BLOCKED if total_time_s > time_available (strictly greater; total can only grow
              when return leg is added, so it already breaches budget).
            - UNKNOWN otherwise (real total with return leg would be higher and is unverified).
        - If return_to_base is True:
            - BLOCKED if total_time_s > time_available (strictly greater).
            - PASS otherwise.
    """
    time_avail_s = float(config.max_eva_hours) * 3600.0
    evidence = [
        EvidenceRef(
            source_type="assumption",
            source_id="config.max_eva_hours",
            detail=f"Budget: {config.max_eva_hours} h (ASSUMPTION ALSJ, spec section 6.2)",
        )
    ]

    if total_time_s is None or not math.isfinite(total_time_s):
        return SafetyCheck(
            check_id=SafetyCheckId.EVA_DURATION,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=time_avail_s,
            units="seconds",
            message=f"Total EVA mission duration could not be computed. {DURATION_LIMITATION_TEXT}",
            evidence=evidence,
        )

    val = float(total_time_s)

    if not return_to_base:
        if val > time_avail_s:
            status = AssessmentStatus.BLOCKED
            msg = (
                f"Total mission duration {val / 3600.0:.2f} h exceeds permissible "
                f"EVA budget of {config.max_eva_hours:.1f} h (return leg not included; "
                f"real total would be higher). {DURATION_LIMITATION_TEXT}"
            )
            ret_val: float | None = val
        else:
            status = AssessmentStatus.UNKNOWN
            msg = (
                f"Return leg not included in route (return_to_base=False); "
                f"mission duration cannot be verified within permissible "
                f"EVA budget of {config.max_eva_hours:.1f} h. {DURATION_LIMITATION_TEXT}"
            )
            ret_val = None
    else:
        if val > time_avail_s:
            status = AssessmentStatus.BLOCKED
            msg = (
                f"Total mission duration {val / 3600.0:.2f} h exceeds permissible "
                f"EVA budget of {config.max_eva_hours:.1f} h. {DURATION_LIMITATION_TEXT}"
            )
        else:
            status = AssessmentStatus.PASS
            msg = (
                f"Total mission duration {val / 3600.0:.2f} h is within permissible "
                f"EVA budget of {config.max_eva_hours:.1f} h. {DURATION_LIMITATION_TEXT}"
            )
        ret_val = val

    return SafetyCheck(
        check_id=SafetyCheckId.EVA_DURATION,
        critical=True,
        status=status,
        value=ret_val,
        threshold=time_avail_s,
        units="seconds",
        message=msg,
        evidence=evidence,
    )


def evaluate_return_reserve(
    total_time_s: float | None,
    config: EvaConfig,
    return_to_base: bool,
) -> SafetyCheck:
    """Evaluate RETURN_RESERVE contingency margin check (Spec section 9.1).

    Rule:
        - If return_to_base is False:
            - BLOCKED if total_time_s > threshold (strictly greater; total can only grow
              when return leg is added, so it already breaches reserve margin).
            - UNKNOWN otherwise (return leg not included in totals).
        - UNKNOWN if total_time_s is None or NaN.
        - Threshold: time_available - reserve_required =
          max_eva_hours * 3600 * (1 - return_reserve_fraction).
        - Warning Threshold: 0.9 * Threshold (spec section 9.1 rule).
        - BLOCKED if total_time_s > threshold (strictly greater).
        - WARNING if total_time_s > warning_threshold (strictly greater).
        - PASS otherwise.
    """
    time_avail_s = float(config.max_eva_hours) * 3600.0
    res_req_s = float(config.return_reserve_fraction) * time_avail_s
    threshold_s = time_avail_s - res_req_s
    warn_threshold_s = RETURN_RESERVE_WARNING_FACTOR * threshold_s

    evidence = [
        EvidenceRef(
            source_type="assumption",
            source_id="config.return_reserve_fraction",
            detail=(
                f"Fraction: {config.return_reserve_fraction} (ASSUMPTION, spec section 6.2); "
                f"Warning factor: {RETURN_RESERVE_WARNING_FACTOR} (spec section 9.1)"
            ),
        )
    ]

    if not return_to_base:
        if (
            total_time_s is not None
            and math.isfinite(total_time_s)
            and float(total_time_s) > threshold_s
        ):
            val = float(total_time_s)
            return SafetyCheck(
                check_id=SafetyCheckId.RETURN_RESERVE,
                critical=True,
                status=AssessmentStatus.BLOCKED,
                value=val,
                threshold=threshold_s,
                units="seconds",
                message=(
                    f"Total mission duration {val:.0f} s leaves insufficient return reserve "
                    f"below required margin of {res_req_s:.0f} s (threshold {threshold_s:.0f} s; "
                    "return leg not included; real total would be higher). "
                    f"{RESERVE_LIMITATION_TEXT}"
                ),
                evidence=evidence,
            )
        return SafetyCheck(
            check_id=SafetyCheckId.RETURN_RESERVE,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=threshold_s,
            units="seconds",
            message=(
                "Return leg not included in route (return_to_base=False); "
                f"return reserve contingency cannot be assessed. {RESERVE_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    if total_time_s is None or not math.isfinite(total_time_s):
        return SafetyCheck(
            check_id=SafetyCheckId.RETURN_RESERVE,
            critical=True,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=threshold_s,
            units="seconds",
            message=(
                f"Total mission duration could not be computed for reserve assessment. "
                f"{RESERVE_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    val = float(total_time_s)
    if val > threshold_s:
        status = AssessmentStatus.BLOCKED
        msg = (
            f"Total mission duration {val:.0f} s leaves insufficient return reserve "
            f"below required margin of {res_req_s:.0f} s (threshold {threshold_s:.0f} s). "
            f"{RESERVE_LIMITATION_TEXT}"
        )
    elif val > warn_threshold_s:
        status = AssessmentStatus.WARNING
        msg = (
            f"Total mission duration {val:.0f} s exceeds caution threshold "
            f"{warn_threshold_s:.0f} s (90% of reserve threshold {threshold_s:.0f} s). "
            f"{RESERVE_LIMITATION_TEXT}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"Total mission duration {val:.0f} s preserves contingency reserve "
            f"above caution threshold {warn_threshold_s:.0f} s. {RESERVE_LIMITATION_TEXT}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.RETURN_RESERVE,
        critical=True,
        status=status,
        value=val,
        threshold=threshold_s,
        units="seconds",
        message=msg,
        evidence=evidence,
    )


def evaluate_roughness(
    path_roughness: Sequence[float] | np.ndarray | None,
    config: EvaConfig,
) -> SafetyCheck:
    """Evaluate ROUGHNESS check (Spec section 9.1).

    Rule:
        - UNKNOWN if path_roughness is missing, empty, or all NaN.
        - Evaluates 95th percentile roughness along path (spec section 9.1 rule).
        - WARNING if p95 > config.roughness_warning_m (strictly greater).
        - PASS otherwise.
    """
    evidence = [
        EvidenceRef(
            source_type="assumption",
            source_id="config.roughness_warning_m",
            detail=(
                f"Limit: {config.roughness_warning_m} m (ASSUMPTION Open Item O-3, "
                f"spec section 6.2; percentile: {ROUGHNESS_PERCENTILE}th per spec section 9.1)"
            ),
        )
    ]

    if path_roughness is None or len(path_roughness) == 0:
        return SafetyCheck(
            check_id=SafetyCheckId.ROUGHNESS,
            critical=False,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=float(config.roughness_warning_m),
            units="metres",
            message=f"Surface roughness data unavailable along path. {ROUGHNESS_LIMITATION_TEXT}",
            evidence=evidence,
        )

    arr = np.asarray(path_roughness, dtype=np.float64)
    valid_arr = arr[np.isfinite(arr)]
    if len(valid_arr) == 0:
        return SafetyCheck(
            check_id=SafetyCheckId.ROUGHNESS,
            critical=False,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=float(config.roughness_warning_m),
            units="metres",
            message=(
                f"No valid surface roughness values found along path. {ROUGHNESS_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    p95_val = float(np.percentile(valid_arr, ROUGHNESS_PERCENTILE))
    threshold_m = float(config.roughness_warning_m)

    if p95_val > threshold_m:
        status = AssessmentStatus.WARNING
        msg = (
            f"95th percentile roughness of {p95_val:.3f} m exceeds warning limit "
            f"of {threshold_m:.2f} m. {ROUGHNESS_LIMITATION_TEXT}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"95th percentile roughness of {p95_val:.3f} m is within warning limit "
            f"of {threshold_m:.2f} m. {ROUGHNESS_LIMITATION_TEXT}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.ROUGHNESS,
        critical=False,
        status=status,
        value=p95_val,
        threshold=threshold_m,
        units="metres",
        message=msg,
        evidence=evidence,
    )


def evaluate_distance_from_base(
    max_distance_from_base_m: float | None,
    config: EvaConfig,
) -> SafetyCheck:
    """Evaluate DISTANCE_FROM_BASE check (Spec section 9.1).

    Rule:
        - UNKNOWN if max_distance_from_base_m is None or NaN.
        - WARNING if value > config.max_distance_from_base_m (strictly greater).
        - PASS otherwise.
    """
    threshold_m = float(config.max_distance_from_base_m)
    evidence = [
        EvidenceRef(
            source_type="reference",
            source_id="config.max_distance_from_base_m",
            detail=(
                f"Limit: {config.max_distance_from_base_m} m (REFERENCE PENA2023, spec section 6.2)"
            ),
        )
    ]

    if max_distance_from_base_m is None or not math.isfinite(max_distance_from_base_m):
        return SafetyCheck(
            check_id=SafetyCheckId.DISTANCE_FROM_BASE,
            critical=False,
            status=AssessmentStatus.UNKNOWN,
            value=None,
            threshold=threshold_m,
            units="metres",
            message=(
                f"Maximum distance from habitat base could not be determined. "
                f"{DISTANCE_LIMITATION_TEXT}"
            ),
            evidence=evidence,
        )

    val = float(max_distance_from_base_m)
    if val > threshold_m:
        status = AssessmentStatus.WARNING
        msg = (
            f"Maximum distance from habitat {val:.1f} m exceeds reference walkback limit "
            f"of {threshold_m:.0f} m. {DISTANCE_LIMITATION_TEXT}"
        )
    else:
        status = AssessmentStatus.PASS
        msg = (
            f"Maximum distance from habitat {val:.1f} m is within reference limit "
            f"of {threshold_m:.0f} m. {DISTANCE_LIMITATION_TEXT}"
        )

    return SafetyCheck(
        check_id=SafetyCheckId.DISTANCE_FROM_BASE,
        critical=False,
        status=status,
        value=val,
        threshold=threshold_m,
        units="metres",
        message=msg,
        evidence=evidence,
    )
