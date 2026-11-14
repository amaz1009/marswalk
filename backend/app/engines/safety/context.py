"""Environmental context indicator generators.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 9.3:
- Context indicators provide mission context (MSL RAD radiation, THEMIS IR thermal).
- Status is ContextStatus.AVAILABLE or ContextStatus.UNAVAILABLE.
- Context indicators are strictly informational and are NEVER aggregated into
  SafetyAssessment.overall_status.
- Values come only from real processed or catalogued sources, never invented.
"""

from app.models.enums import ContextIndicatorId, ContextStatus, DataClass
from app.models.evidence import EvidenceRef
from app.models.terrain import ContextIndicator


def build_radiation_context_indicator(
    source_id: str = "MSL_RAD_SURFACE_RDR",
    is_available: bool = False,
    dose_rate_microgy_per_day: float | None = None,
    observation_period: str | None = None,
) -> ContextIndicator:
    """Build RADIATION_CONTEXT indicator from MSL RAD surface observations (Spec section 9.3).

    Note on Gale Crater region configuration:
        `backend/data/regions/gale_mount_sharp.json` records:
        `context_sources.radiation = "MSL_RAD_SURFACE_RDR"`.
        In Scope A, MSL RAD surface sol tables remain unintegrated and are marked
        UNAVAILABLE in the dataset catalog. When unavailable, this function honestly
        reports UNAVAILABLE with the real reason, never inventing values.
    """
    evidence = [
        EvidenceRef(
            source_type="dataset",
            source_id=source_id,
            detail="MSL RAD surface radiation observation context (spec section 9.3)",
        )
    ]

    limitations = [
        (
            "Historical point observation at Curiosity rover location; does"
            " not forecast space weather."
        ),
        (
            "Dose rates cannot be extrapolated across Gale Crater or future"
            " solar cycle phases without transport modeling."
        ),
    ]

    if is_available and dose_rate_microgy_per_day is not None:
        return ContextIndicator(
            indicator_id=ContextIndicatorId.RADIATION_CONTEXT,
            status=ContextStatus.AVAILABLE,
            summary=(
                f"MSL RAD surface observation indicates approximately "
                f"{dose_rate_microgy_per_day:.1f} uGy/day surface dose rate."
            ),
            value=dose_rate_microgy_per_day,
            units="uGy/day",
            period=observation_period,
            data_class=DataClass.MEASURED,
            evidence=evidence,
            limitations=limitations,
        )

    return ContextIndicator(
        indicator_id=ContextIndicatorId.RADIATION_CONTEXT,
        status=ContextStatus.UNAVAILABLE,
        summary=(
            "MSL RAD surface radiation observation data is UNAVAILABLE in local region catalog. "
            "Radiation context is not evaluated for this traverse."
        ),
        value=None,
        units=None,
        period=None,
        data_class=DataClass.MEASURED,
        evidence=evidence,
        limitations=limitations,
    )


def build_thermal_context_indicator() -> ContextIndicator:
    """Build THERMAL_CONTEXT indicator from THEMIS IR surface temperature (Spec section 9.3).

    Note:
        In Scope A, THEMIS Daytime Infrared Global Mosaic (THEMIS_DAY_IR_GLOBAL) is
        UNAVAILABLE (not selected for download in scope A core), and no local thermal
        dataset is catalogued for this region. The indicator honestly reports UNAVAILABLE
        per spec section 9.3 and dataset_catalog.json.
    """
    evidence = [
        EvidenceRef(
            source_type="dataset",
            source_id="THEMIS_DAY_IR_GLOBAL",
            detail=(
                "THEMIS Daytime Infrared Global Mosaic v12 (spec section 9.3, dataset_catalog.json)"
            ),
        )
    ]

    limitations = [
        "Brightness temperature is not air temperature or astronaut suit boundary temperature.",
        "Single local-time observation does not represent diurnal thermal extrema.",
        (
            "Global mosaic not downloaded in Scope A core; "
            "no local thermal dataset catalogued for region."
        ),
    ]

    return ContextIndicator(
        indicator_id=ContextIndicatorId.THERMAL_CONTEXT,
        status=ContextStatus.UNAVAILABLE,
        summary=(
            "THEMIS daytime infrared mosaic (THEMIS_DAY_IR_GLOBAL) is UNAVAILABLE in Scope A "
            "and no local thermal dataset is catalogued for this region. "
            "Diurnal surface temperature context is not evaluated for this traverse."
        ),
        value=None,
        units=None,
        period=None,
        data_class=DataClass.MEASURED,
        evidence=evidence,
        limitations=limitations,
    )


def build_context_indicators(
    radiation_source_id: str = "MSL_RAD_SURFACE_RDR",
    radiation_available: bool = False,
    radiation_value: float | None = None,
    radiation_period: str | None = None,
) -> list[ContextIndicator]:
    """Return both environmental context indicators for an assessment."""
    return [
        build_radiation_context_indicator(
            source_id=radiation_source_id,
            is_available=radiation_available,
            dose_rate_microgy_per_day=radiation_value,
            observation_period=radiation_period,
        ),
        build_thermal_context_indicator(),
    ]
