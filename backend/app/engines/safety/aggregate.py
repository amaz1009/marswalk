"""Deterministic safety check aggregation and assessment synthesis.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 9.2:
- if any check is BLOCKED                     -> BLOCKED
- elif any critical check is UNKNOWN          -> UNKNOWN  (assessment incomplete)
- elif any check is WARNING or UNKNOWN        -> WARNING
- else                                        -> PASS     (prototype criteria only)

No score, objective, API parameter, or agent output can change a check status
or the overall status (T-SAFE-06).
"""

from typing import Sequence

from app.engines.safety.checks import SAFETY_DISCLAIMER_TEXT
from app.models.enums import AssessmentStatus
from app.models.eva import SafetyAssessment, SafetyCheck
from app.models.terrain import ContextIndicator

REQUIRED_SAFETY_CHECK_COUNT: int = 7


def aggregate_safety_status(checks: Sequence[SafetyCheck]) -> AssessmentStatus:
    """Aggregate individual safety checks into a single traverse assessment status.

    Follows the deterministic precedence rule from docs/SCIENCE_AND_SAFETY_SPEC.md section 9.2:
        1. If ANY check is BLOCKED -> BLOCKED
        2. Else if ANY critical check is UNKNOWN -> UNKNOWN (assessment incomplete)
        3. Else if ANY check is WARNING or UNKNOWN -> WARNING
        4. Else -> PASS (prototype criteria only)

    Args:
        checks: Sequence of SafetyCheck results.

    Returns:
        AssessmentStatus enum value.
    """
    # 1. Any BLOCKED (critical or non-critical) forces overall BLOCKED
    if any(c.status == AssessmentStatus.BLOCKED for c in checks):
        return AssessmentStatus.BLOCKED

    # 2. Any critical check UNKNOWN forces overall UNKNOWN
    if any(c.critical and c.status == AssessmentStatus.UNKNOWN for c in checks):
        return AssessmentStatus.UNKNOWN

    # 3. Any check WARNING or non-critical UNKNOWN forces overall WARNING
    if any(
        c.status == AssessmentStatus.WARNING or c.status == AssessmentStatus.UNKNOWN for c in checks
    ):
        return AssessmentStatus.WARNING

    # 4. All checks passed
    return AssessmentStatus.PASS


def build_safety_assessment(
    checks: Sequence[SafetyCheck],
    context: Sequence[ContextIndicator],
    disclaimer: str = SAFETY_DISCLAIMER_TEXT,
) -> SafetyAssessment:
    """Construct SafetyAssessment dataclass containing checks, context, and disclaimer.

    Args:
        checks: All 7 required SafetyCheck instances (evaluated in fixed order).
        context: Environmental ContextIndicator records (never aggregated).
        disclaimer: Mandatory prototype safety assessment disclaimer string.

    Returns:
        SafetyAssessment instance satisfying frozen API contract.

    Raises:
        ValueError: If fewer or more than 7 checks are provided, or if duplicate
            check_ids exist.
    """
    check_list = list(checks)
    if len(check_list) != REQUIRED_SAFETY_CHECK_COUNT:
        raise ValueError(
            f"SafetyAssessment requires exactly {REQUIRED_SAFETY_CHECK_COUNT} checks, "
            f"got {len(check_list)}"
        )

    seen_ids = set()
    for c in check_list:
        if c.check_id in seen_ids:
            raise ValueError(f"Duplicate SafetyCheckId in assessment: {c.check_id}")
        seen_ids.add(c.check_id)

    overall_status = aggregate_safety_status(check_list)

    return SafetyAssessment(
        overall_status=overall_status,
        checks=check_list,
        context=list(context),
        disclaimer=disclaimer,
    )
