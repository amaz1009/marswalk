"""Unit tests for safety check framework and aggregation (T-SAFE-01..05, T-SAFE-07).

Implements testing requirements from docs/SCIENCE_AND_SAFETY_SPEC.md section 9 and section 14.1:
- T-SAFE-01: Slope max pass, warning, and blocked states.
- T-SAFE-02: Hazard intersection pass and blocked.
- T-SAFE-03: Return reserve warning and blocked.
- T-SAFE-04: Distance from base warning.
- T-SAFE-05: Deterministic aggregation rules (spec section 9.2).
- T-SAFE-07: Context indicators never affect overall safety status.
- Note: T-SAFE-06 belongs to the site-selection WP (WP-19), not WP-11.
- Strict boundary tests and explicit hand-derived aggregation truth table.
- Missing, NaN, or non-computable input strictly evaluates to UNKNOWN.
"""

import math

import pytest

from app.engines.eva.defaults import get_default_eva_config
from app.engines.safety.aggregate import (
    aggregate_safety_status,
    build_safety_assessment,
)
from app.engines.safety.checks import (
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
from app.models.enums import (
    AssessmentStatus,
    ContextStatus,
    DataClass,
    SafetyCheckId,
)
from app.models.eva import SafetyCheck
from app.models.evidence import EvidenceRef


def _make_dummy_check(
    check_id: SafetyCheckId,
    status: AssessmentStatus,
    critical: bool,
) -> SafetyCheck:
    """Helper creating minimal valid SafetyCheck for aggregation tests."""
    return SafetyCheck(
        check_id=check_id,
        critical=critical,
        status=status,
        value=1.0 if status == AssessmentStatus.PASS else None,
        threshold=1.0,
        units="test",
        message="test",
        evidence=[EvidenceRef(source_type="engine", source_id="test")],
    )


# ---------------------------------------------------------------------------
# Individual Check Evaluations (T-SAFE-01 to T-SAFE-04)
# ---------------------------------------------------------------------------


def test_t_safe_01_slope_max_pass_warning_blocked() -> None:
    """T-SAFE-01: SLOPE_MAX evaluates caution (10 deg) and hard limit (15 deg)."""
    config = get_default_eva_config()

    # Pass: 8.0 deg <= 10.0 deg
    c_pass = evaluate_slope_max([5.0, 8.0, 3.0], config)
    assert c_pass.status == AssessmentStatus.PASS
    assert c_pass.critical is True
    assert math.isclose(c_pass.value, 8.0, rel_tol=1e-9)

    # Warning: 12.0 deg > 10.0 deg and <= 15.0 deg
    c_warn = evaluate_slope_max([8.0, 12.0, 5.0], config)
    assert c_warn.status == AssessmentStatus.WARNING
    assert math.isclose(c_warn.value, 12.0, rel_tol=1e-9)

    # Blocked: 16.5 deg > 15.0 deg
    c_block = evaluate_slope_max([10.0, 16.5, 4.0], config)
    assert c_block.status == AssessmentStatus.BLOCKED
    assert math.isclose(c_block.value, 16.5, rel_tol=1e-9)


def test_t_safe_02_hazard_intersection_pass_and_blocked() -> None:
    """T-SAFE-02: HAZARD_INTERSECTION blocks if any impassable cells are crossed."""
    # Pass: 0 cells
    c_pass = evaluate_hazard_intersection(0)
    assert c_pass.status == AssessmentStatus.PASS
    assert c_pass.critical is True
    assert c_pass.value == 0.0

    # Blocked: 3 cells
    c_block = evaluate_hazard_intersection(3)
    assert c_block.status == AssessmentStatus.BLOCKED
    assert c_block.value == 3.0


def test_t_safe_03_return_reserve_warning_and_blocked() -> None:
    """T-SAFE-03: RETURN_RESERVE evaluates warning threshold (14580 s) and hard limit (16200 s).

    Hand Derivation:
        Available = 6.0 * 3600 = 21600.0 s
        Reserve required = 0.25 * 21600 = 5400.0 s
        Threshold = 21600 - 5400 = 16200.0 s
        Warning threshold = 0.9 * 16200 = 14580.0 s
    """
    config = get_default_eva_config()

    # Pass: total_time 14000 s <= 14580 s
    c_pass = evaluate_return_reserve(14000.0, config, return_to_base=True)
    assert c_pass.status == AssessmentStatus.PASS
    assert c_pass.critical is True

    # Warning: total_time 15000 s > 14580 s and <= 16200 s
    c_warn = evaluate_return_reserve(15000.0, config, return_to_base=True)
    assert c_warn.status == AssessmentStatus.WARNING

    # Blocked: total_time 17000 s > 16200 s
    c_block = evaluate_return_reserve(17000.0, config, return_to_base=True)
    assert c_block.status == AssessmentStatus.BLOCKED


def test_t_safe_04_distance_from_base_warning() -> None:
    """T-SAFE-04: DISTANCE_FROM_BASE warns if distance exceeds 2000 m (non-critical)."""
    config = get_default_eva_config()

    # Pass: 1800 m <= 2000 m
    c_pass = evaluate_distance_from_base(1800.0, config)
    assert c_pass.status == AssessmentStatus.PASS
    assert c_pass.critical is False

    # Warning: 2200 m > 2000 m
    c_warn = evaluate_distance_from_base(2200.0, config)
    assert c_warn.status == AssessmentStatus.WARNING
    assert c_warn.critical is False


# ---------------------------------------------------------------------------
# Strict Boundary Tests (Ruling 4)
# ---------------------------------------------------------------------------


def test_boundary_slope_strict_inequalities() -> None:
    """Ruling 4: Strict inequality checks at slope boundaries.

    - slope == 10.0 -> PASS (not > 10.0)
    - slope == 15.0 -> WARNING (exceeds 10.0, but not > 15.0)
    - slope == 15.0000001 -> BLOCKED (exceeds 15.0)
    """
    config = get_default_eva_config()

    c_exact_10 = evaluate_slope_max([10.0], config)
    assert c_exact_10.status == AssessmentStatus.PASS

    c_exact_15 = evaluate_slope_max([15.0], config)
    assert c_exact_15.status == AssessmentStatus.WARNING

    c_exceed_15 = evaluate_slope_max([15.0000001], config)
    assert c_exceed_15.status == AssessmentStatus.BLOCKED


def test_boundary_return_reserve_strict_inequalities() -> None:
    """Ruling 4: Strict inequality checks at return reserve boundaries.

    Threshold = 16200.0 s, Warning Threshold = 14580.0 s.
    - total_time == 14580.0 -> PASS (not > 14580.0)
    - total_time == 16200.0 -> WARNING (exceeds 14580.0, but not > 16200.0)
    - total_time == 16200.01 -> BLOCKED (exceeds 16200.0)
    """
    config = get_default_eva_config()

    c_exact_warn = evaluate_return_reserve(14580.0, config, return_to_base=True)
    assert c_exact_warn.status == AssessmentStatus.PASS

    c_exact_thresh = evaluate_return_reserve(16200.0, config, return_to_base=True)
    assert c_exact_thresh.status == AssessmentStatus.WARNING

    c_exceed_thresh = evaluate_return_reserve(16200.01, config, return_to_base=True)
    assert c_exceed_thresh.status == AssessmentStatus.BLOCKED


def test_boundary_at_exact_time_available() -> None:
    """Ruling 4: At exact time_available (21600.0 s), EVA_DURATION is PASS and
    RETURN_RESERVE is BLOCKED.

    - EVA_DURATION compares against time_available (21600.0 s). Value 21600.0 is
      not > 21600.0 -> PASS.
    - RETURN_RESERVE compares against 16200.0 s. Value 21600.0 is > 16200.0 -> BLOCKED.
    """
    config = get_default_eva_config()

    c_dur = evaluate_eva_duration(21600.0, config, return_to_base=True)
    assert c_dur.status == AssessmentStatus.PASS

    c_res = evaluate_return_reserve(21600.0, config, return_to_base=True)
    assert c_res.status == AssessmentStatus.BLOCKED


# ---------------------------------------------------------------------------
# Missing, NaN, and Non-Computable Input Rules (Ruling 2 & Ruling 3)
# ---------------------------------------------------------------------------


def test_unknown_slope_max_when_nan_or_none() -> None:
    """Ruling 2: Missing or NaN slope strictly returns UNKNOWN, never PASS."""
    config = get_default_eva_config()
    assert evaluate_slope_max(None, config).status == AssessmentStatus.UNKNOWN
    assert evaluate_slope_max([], config).status == AssessmentStatus.UNKNOWN
    assert evaluate_slope_max([5.0, float("nan"), 8.0], config).status == AssessmentStatus.UNKNOWN


def test_unknown_hazard_intersection_when_none() -> None:
    """Ruling 2: Missing hazard count strictly returns UNKNOWN, never PASS."""
    assert evaluate_hazard_intersection(None).status == AssessmentStatus.UNKNOWN


def test_unknown_terrain_data_coverage_when_nan_or_none() -> None:
    """Ruling 2: Missing coverage fraction strictly returns UNKNOWN, never PASS."""
    assert evaluate_terrain_data_coverage(None).status == AssessmentStatus.UNKNOWN
    assert evaluate_terrain_data_coverage(float("nan")).status == AssessmentStatus.UNKNOWN


def test_unknown_eva_duration_when_nan_or_none() -> None:
    """Ruling 2: Missing or NaN total_time strictly returns UNKNOWN, never PASS."""
    config = get_default_eva_config()
    assert (
        evaluate_eva_duration(None, config, return_to_base=True).status == AssessmentStatus.UNKNOWN
    )
    assert (
        evaluate_eva_duration(float("nan"), config, return_to_base=True).status
        == AssessmentStatus.UNKNOWN
    )


def test_unknown_return_reserve_when_nan_or_none() -> None:
    """Ruling 2: Missing or NaN return reserve duration strictly returns UNKNOWN, never PASS."""
    config = get_default_eva_config()
    assert (
        evaluate_return_reserve(None, config, return_to_base=True).status
        == AssessmentStatus.UNKNOWN
    )
    assert (
        evaluate_return_reserve(float("nan"), config, return_to_base=True).status
        == AssessmentStatus.UNKNOWN
    )


def test_omitting_return_to_base_raises_type_error() -> None:
    """Omitting required return_to_base parameter must raise TypeError."""
    config = get_default_eva_config()
    with pytest.raises(TypeError):
        evaluate_eva_duration(10000.0, config)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        evaluate_return_reserve(10000.0, config)  # type: ignore[call-arg]


def test_return_to_base_false_hand_derived_three_cases() -> None:
    """EVA_DURATION and RETURN_RESERVE when return_to_base=False.

    Hand Derivation:
        Config:
            max_eva_hours = 6.0 h -> time_available = 6.0 * 3600 = 21600.0 s
            return_reserve_fraction = 0.25 -> reserve_required = 0.25 * 21600 = 5400.0 s
            RETURN_RESERVE threshold = time_available - reserve_required = 16200.0 s

        Rule:
            Total mission duration can only increase when the return leg is added.
            Therefore, if a partial outbound total already exceeds a check's hard
            BLOCKED threshold, that check is deterministically BLOCKED even without
            the return leg.
            If the partial total is below the BLOCKED threshold, the check is UNKNOWN
            because the final total with return leg cannot be verified.

        Case 1: total_time_s = 10000.0 s, return_to_base = False
            - 10000.0 <= 21600.0 (time_available) -> EVA_DURATION is UNKNOWN
            - 10000.0 <= 16200.0 (reserve threshold) -> RETURN_RESERVE is UNKNOWN
        Case 2: total_time_s = 17000.0 s, return_to_base = False
            - 17000.0 <= 21600.0 (time_available) -> EVA_DURATION is UNKNOWN
            - 17000.0 > 16200.0 (reserve threshold) -> RETURN_RESERVE is BLOCKED
        Case 3: total_time_s = 22000.0 s, return_to_base = False
            - 22000.0 > 21600.0 (time_available) -> EVA_DURATION is BLOCKED
            - 22000.0 > 16200.0 (reserve threshold) -> RETURN_RESERVE is BLOCKED

        Return included (return_to_base = True) baseline verification:
            - total_time_s = 10000.0 s: EVA_DURATION PASS, RETURN_RESERVE PASS
            - total_time_s = 17000.0 s: EVA_DURATION PASS, RETURN_RESERVE BLOCKED
            - total_time_s = 22000.0 s: EVA_DURATION BLOCKED, RETURN_RESERVE BLOCKED
    """
    config = get_default_eva_config()

    # Case 1: total 10000.0 s
    c_dur_1 = evaluate_eva_duration(10000.0, config, return_to_base=False)
    c_res_1 = evaluate_return_reserve(10000.0, config, return_to_base=False)
    assert c_dur_1.status == AssessmentStatus.UNKNOWN
    assert c_dur_1.value is None
    assert "return_to_base=False" in c_dur_1.message
    assert c_res_1.status == AssessmentStatus.UNKNOWN
    assert c_res_1.value is None
    assert "return_to_base=False" in c_res_1.message

    # Case 2: total 17000.0 s
    c_dur_2 = evaluate_eva_duration(17000.0, config, return_to_base=False)
    c_res_2 = evaluate_return_reserve(17000.0, config, return_to_base=False)
    assert c_dur_2.status == AssessmentStatus.UNKNOWN
    assert c_dur_2.value is None
    assert "return_to_base=False" in c_dur_2.message
    assert c_res_2.status == AssessmentStatus.BLOCKED
    assert c_res_2.value == 17000.0
    assert "return leg not included" in c_res_2.message

    # Case 3: total 22000.0 s
    c_dur_3 = evaluate_eva_duration(22000.0, config, return_to_base=False)
    c_res_3 = evaluate_return_reserve(22000.0, config, return_to_base=False)
    assert c_dur_3.status == AssessmentStatus.BLOCKED
    assert c_dur_3.value == 22000.0
    assert "return leg not included" in c_dur_3.message
    assert c_res_3.status == AssessmentStatus.BLOCKED
    assert c_res_3.value == 22000.0
    assert "return leg not included" in c_res_3.message

    # Baseline with return_to_base=True
    assert (
        evaluate_eva_duration(10000.0, config, return_to_base=True).status == AssessmentStatus.PASS
    )
    assert (
        evaluate_return_reserve(10000.0, config, return_to_base=True).status
        == AssessmentStatus.PASS
    )
    assert (
        evaluate_eva_duration(17000.0, config, return_to_base=True).status == AssessmentStatus.PASS
    )
    assert (
        evaluate_return_reserve(17000.0, config, return_to_base=True).status
        == AssessmentStatus.BLOCKED
    )
    assert (
        evaluate_eva_duration(22000.0, config, return_to_base=True).status
        == AssessmentStatus.BLOCKED
    )
    assert (
        evaluate_return_reserve(22000.0, config, return_to_base=True).status
        == AssessmentStatus.BLOCKED
    )


def test_unknown_roughness_when_nan_or_empty() -> None:
    """Ruling 2: Missing or all-NaN roughness strictly returns UNKNOWN, never PASS."""
    config = get_default_eva_config()
    assert evaluate_roughness(None, config).status == AssessmentStatus.UNKNOWN
    assert evaluate_roughness([], config).status == AssessmentStatus.UNKNOWN
    assert (
        evaluate_roughness([float("nan"), float("nan")], config).status == AssessmentStatus.UNKNOWN
    )


def test_unknown_distance_from_base_when_nan_or_none() -> None:
    """Ruling 2: Missing distance strictly returns UNKNOWN, never PASS."""
    config = get_default_eva_config()
    assert evaluate_distance_from_base(None, config).status == AssessmentStatus.UNKNOWN
    assert evaluate_distance_from_base(float("nan"), config).status == AssessmentStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Aggregation Logic & Truth Table (Ruling 5, T-SAFE-05, T-SAFE-06)
# ---------------------------------------------------------------------------


def test_safety_aggregation_hand_derived_truth_table() -> None:
    """Ruling 5: Explicit literal truth table for aggregation rules (spec section 9.2).

    Precedence Rule:
        1. If ANY check is BLOCKED -> BLOCKED
        2. Else if ANY critical check is UNKNOWN -> UNKNOWN
        3. Else if ANY check is WARNING or UNKNOWN -> WARNING
        4. Else -> PASS

    Table covers critical and non-critical mixes across all states.
    Expected values are written by hand (NOT recomputed by the rule under test).
    """
    # Columns: [crit1, crit2, crit3, crit4, crit5, noncrit1, noncrit2] -> expected_status
    P = AssessmentStatus.PASS
    W = AssessmentStatus.WARNING
    B = AssessmentStatus.BLOCKED
    U = AssessmentStatus.UNKNOWN

    truth_table: list[tuple[list[AssessmentStatus], AssessmentStatus]] = [
        # 1. All PASS -> PASS
        ([P, P, P, P, P, P, P], P),
        # 2. Non-critical WARNING, all critical PASS -> WARNING
        ([P, P, P, P, P, W, P], W),
        # 3. Critical WARNING, all others PASS -> WARNING
        ([W, P, P, P, P, P, P], W),
        # 4. Multiple WARNINGs (critical + non-critical) -> WARNING
        ([W, P, P, P, P, W, W], W),
        # 5. Non-critical UNKNOWN, all critical PASS -> WARNING
        ([P, P, P, P, P, U, P], W),
        # 6. Both non-critical UNKNOWN, critical PASS -> WARNING
        ([P, P, P, P, P, U, U], W),
        # 7. Non-critical UNKNOWN + critical WARNING -> WARNING
        ([W, P, P, P, P, U, P], W),
        # 8. Single critical UNKNOWN -> UNKNOWN
        ([U, P, P, P, P, P, P], U),
        # 9. Critical UNKNOWN + critical WARNING -> UNKNOWN (critical UNKNOWN precedes WARNING)
        ([U, W, P, P, P, P, P], U),
        # 10. Critical UNKNOWN + non-critical UNKNOWN -> UNKNOWN
        ([U, P, P, P, P, U, P], U),
        # 11. Single non-critical BLOCKED -> BLOCKED (BLOCKED has highest precedence)
        ([P, P, P, P, P, B, P], B),
        # 12. Critical BLOCKED with all others PASS -> BLOCKED
        ([B, P, P, P, P, P, P], B),
        # 13. Critical BLOCKED + critical UNKNOWN -> BLOCKED
        ([B, U, P, P, P, P, P], B),
        # 14. Non-critical BLOCKED + critical UNKNOWN + warnings -> BLOCKED
        ([W, U, P, P, P, B, W], B),
    ]

    check_ids = [
        (SafetyCheckId.SLOPE_MAX, True),
        (SafetyCheckId.HAZARD_INTERSECTION, True),
        (SafetyCheckId.TERRAIN_DATA_COVERAGE, True),
        (SafetyCheckId.EVA_DURATION, True),
        (SafetyCheckId.RETURN_RESERVE, True),
        (SafetyCheckId.ROUGHNESS, False),
        (SafetyCheckId.DISTANCE_FROM_BASE, False),
    ]

    for statuses, expected in truth_table:
        checks = [
            _make_dummy_check(cid, st, crit)
            for (cid, crit), st in zip(check_ids, statuses, strict=True)
        ]
        actual = aggregate_safety_status(checks)
        assert actual == expected, (
            f"Failed for statuses {statuses}: expected {expected}, got {actual}"
        )


def test_t_safe_05_aggregation_logic_critical_unknown() -> None:
    """T-SAFE-05: Critical UNKNOWN yields overall UNKNOWN; non-critical UNKNOWN yields WARNING."""
    crit_unknown_checks = [
        _make_dummy_check(SafetyCheckId.SLOPE_MAX, AssessmentStatus.UNKNOWN, critical=True),
        _make_dummy_check(SafetyCheckId.HAZARD_INTERSECTION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(
            SafetyCheckId.TERRAIN_DATA_COVERAGE, AssessmentStatus.PASS, critical=True
        ),
        _make_dummy_check(SafetyCheckId.EVA_DURATION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.RETURN_RESERVE, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.ROUGHNESS, AssessmentStatus.PASS, critical=False),
        _make_dummy_check(SafetyCheckId.DISTANCE_FROM_BASE, AssessmentStatus.PASS, critical=False),
    ]
    assert aggregate_safety_status(crit_unknown_checks) == AssessmentStatus.UNKNOWN

    noncrit_unknown_checks = [
        _make_dummy_check(SafetyCheckId.SLOPE_MAX, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.HAZARD_INTERSECTION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(
            SafetyCheckId.TERRAIN_DATA_COVERAGE, AssessmentStatus.PASS, critical=True
        ),
        _make_dummy_check(SafetyCheckId.EVA_DURATION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.RETURN_RESERVE, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.ROUGHNESS, AssessmentStatus.UNKNOWN, critical=False),
        _make_dummy_check(SafetyCheckId.DISTANCE_FROM_BASE, AssessmentStatus.PASS, critical=False),
    ]
    assert aggregate_safety_status(noncrit_unknown_checks) == AssessmentStatus.WARNING


def test_t_safe_05_blocked_always_dominates_aggregation() -> None:
    """T-SAFE-05: BLOCKED check status deterministically forces overall BLOCKED (spec 9.2)."""
    blocked_checks = [
        _make_dummy_check(SafetyCheckId.SLOPE_MAX, AssessmentStatus.BLOCKED, critical=True),
        _make_dummy_check(SafetyCheckId.HAZARD_INTERSECTION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(
            SafetyCheckId.TERRAIN_DATA_COVERAGE, AssessmentStatus.PASS, critical=True
        ),
        _make_dummy_check(SafetyCheckId.EVA_DURATION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.RETURN_RESERVE, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.ROUGHNESS, AssessmentStatus.PASS, critical=False),
        _make_dummy_check(SafetyCheckId.DISTANCE_FROM_BASE, AssessmentStatus.PASS, critical=False),
    ]
    # Overall status is deterministically BLOCKED regardless of any external score
    overall = aggregate_safety_status(blocked_checks)
    assert overall == AssessmentStatus.BLOCKED


# ---------------------------------------------------------------------------
# Context Indicators & Disclaimer (Ruling 8, Ruling 9, T-SAFE-07)
# ---------------------------------------------------------------------------


def test_t_safe_07_context_indicators_never_change_safety() -> None:
    """T-SAFE-07: Context indicators are informational and never affect safety status."""
    pass_checks = [
        _make_dummy_check(SafetyCheckId.SLOPE_MAX, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.HAZARD_INTERSECTION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(
            SafetyCheckId.TERRAIN_DATA_COVERAGE, AssessmentStatus.PASS, critical=True
        ),
        _make_dummy_check(SafetyCheckId.EVA_DURATION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.RETURN_RESERVE, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.ROUGHNESS, AssessmentStatus.PASS, critical=False),
        _make_dummy_check(SafetyCheckId.DISTANCE_FROM_BASE, AssessmentStatus.PASS, critical=False),
    ]

    # Both indicators UNAVAILABLE
    ctx_unavail = build_context_indicators(radiation_available=False)
    assessment1 = build_safety_assessment(pass_checks, ctx_unavail)
    assert assessment1.overall_status == AssessmentStatus.PASS

    # Radiation AVAILABLE with high dose rate
    ctx_avail = build_context_indicators(
        radiation_available=True,
        radiation_value=250.0,
        radiation_period="Sol 13-500",
    )
    assessment2 = build_safety_assessment(pass_checks, ctx_avail)
    assert assessment2.overall_status == AssessmentStatus.PASS


def test_context_indicators_unavailability_reasons() -> None:
    """Ruling 8: When unavailable, indicators state honest reasons without inventing data."""
    rad_indicator = build_radiation_context_indicator(is_available=False)
    assert rad_indicator.status == ContextStatus.UNAVAILABLE
    assert rad_indicator.value is None
    assert "UNAVAILABLE in local region catalog" in rad_indicator.summary
    assert rad_indicator.data_class == DataClass.MEASURED
    assert rad_indicator.evidence[0].source_id == "MSL_RAD_SURFACE_RDR"

    therm_indicator = build_thermal_context_indicator()
    assert therm_indicator.status == ContextStatus.UNAVAILABLE
    assert therm_indicator.value is None
    assert "UNAVAILABLE in Scope A" in therm_indicator.summary
    assert "no local thermal dataset is catalogued" in therm_indicator.summary
    assert therm_indicator.data_class == DataClass.MEASURED
    assert therm_indicator.evidence[0].source_id == "THEMIS_DAY_IR_GLOBAL"


def test_safety_disclaimer_verbatim_match() -> None:
    """Ruling 9: Exact disclaimer string from spec section 14.1 (lines 575-577)."""
    expected = (
        "AresNav is a research and planning prototype. Results are computational "
        "assessments under stated assumptions and are not a certified astronaut safety analysis."
    )
    assert SAFETY_DISCLAIMER_TEXT == expected

    pass_checks = [
        _make_dummy_check(SafetyCheckId.SLOPE_MAX, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.HAZARD_INTERSECTION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(
            SafetyCheckId.TERRAIN_DATA_COVERAGE, AssessmentStatus.PASS, critical=True
        ),
        _make_dummy_check(SafetyCheckId.EVA_DURATION, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.RETURN_RESERVE, AssessmentStatus.PASS, critical=True),
        _make_dummy_check(SafetyCheckId.ROUGHNESS, AssessmentStatus.PASS, critical=False),
        _make_dummy_check(SafetyCheckId.DISTANCE_FROM_BASE, AssessmentStatus.PASS, critical=False),
    ]
    assessment = build_safety_assessment(pass_checks, [])
    assert assessment.disclaimer == expected


# ---------------------------------------------------------------------------
# Limitation Sentence Standard (Spec section 9.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "check_evaluator_fn,expected_statuses",
    [
        (
            lambda st, cfg: (
                evaluate_slope_max(None, cfg)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_slope_max([5.0], cfg)
                    if st == AssessmentStatus.PASS
                    else (
                        evaluate_slope_max([12.0], cfg)
                        if st == AssessmentStatus.WARNING
                        else evaluate_slope_max([18.0], cfg)
                    )
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.WARNING,
                AssessmentStatus.BLOCKED,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_hazard_intersection(None)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_hazard_intersection(0)
                    if st == AssessmentStatus.PASS
                    else evaluate_hazard_intersection(2)
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.BLOCKED,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_terrain_data_coverage(None)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_terrain_data_coverage(1.0, 1.0)
                    if st == AssessmentStatus.PASS
                    else evaluate_terrain_data_coverage(0.8, 1.0)
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.WARNING,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_eva_duration(None, cfg, return_to_base=True)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_eva_duration(10000.0, cfg, return_to_base=True)
                    if st == AssessmentStatus.PASS
                    else evaluate_eva_duration(25000.0, cfg, return_to_base=True)
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.BLOCKED,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_return_reserve(None, cfg, return_to_base=True)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_return_reserve(10000.0, cfg, return_to_base=True)
                    if st == AssessmentStatus.PASS
                    else (
                        evaluate_return_reserve(15000.0, cfg, return_to_base=True)
                        if st == AssessmentStatus.WARNING
                        else evaluate_return_reserve(18000.0, cfg, return_to_base=True)
                    )
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.WARNING,
                AssessmentStatus.BLOCKED,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_roughness(None, cfg)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_roughness([0.05], cfg)
                    if st == AssessmentStatus.PASS
                    else evaluate_roughness([0.45], cfg)
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.WARNING,
                AssessmentStatus.UNKNOWN,
            ],
        ),
        (
            lambda st, cfg: (
                evaluate_distance_from_base(None, cfg)
                if st == AssessmentStatus.UNKNOWN
                else (
                    evaluate_distance_from_base(1500.0, cfg)
                    if st == AssessmentStatus.PASS
                    else evaluate_distance_from_base(2500.0, cfg)
                )
            ),
            [
                AssessmentStatus.PASS,
                AssessmentStatus.WARNING,
                AssessmentStatus.UNKNOWN,
            ],
        ),
    ],
)
def test_all_seven_checks_contain_limitation_sentence(
    check_evaluator_fn,
    expected_statuses: list[AssessmentStatus],
) -> None:
    """Spec 9.1: Every check message must end with a sentence starting with 'Limitation:'."""
    config = get_default_eva_config()
    for status in expected_statuses:
        check = check_evaluator_fn(status, config)
        assert check.status == status
        assert "Limitation:" in check.message
        limitation_part = check.message.split("Limitation:")[1].strip()
        assert len(limitation_part) > 0
        assert check.message.rstrip().endswith(".")
