"""Unit tests for the mission report builder and service.

Validates compliance with:
- docs/SCIENCE_AND_SAFETY_SPEC.md §14 (Wording rules, disclaimer, and 12-section fixed order)
- docs/API_CONTRACTS.md §4.13 (Mission report endpoint, schemas, and error codes)
- Acceptance tests T-API-08, T-SAFE-07, and T-E2E-01
"""

import json
import math
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.errors import AppException
from app.engines.report.builder import build_mission_report
from app.engines.safety.checks import SAFETY_DISCLAIMER_TEXT
from app.models.agents import (
    AgentAnalysisResponse,
    AgentResult,
    AgentSynthesis,
)
from app.models.datasets import DatasetRecord
from app.models.enums import (
    AssessmentStatus,
    DataClass,
    DatasetStatus,
    PlanStatus,
    RouteObjective,
    TimelineKind,
)
from app.models.eva import (
    EvaConfig,
    GridInfo,
    ProfilePoint,
    Route,
    RouteLeg,
    RoutePlanRequest,
    RoutePlanResponse,
    RouteTotals,
    SafetyAssessment,
    SafetyCheck,
    StatSummary,
    Stop,
    TimelineEntry,
)
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoPoint
from app.models.mission import (
    MissionReportRequest,
    MissionState,
)
from app.services.eva_service import get_default_eva_response
from app.services.region_service import list_datasets
from app.services.report_service import ReportService
from app.services.route_service import RouteService, get_route_service

PROCESSED_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
REAL_DATA_EXISTS = (
    (PROCESSED_DATA_DIR / "HIRISE_DTM_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_SLOPE_GALE_MOUND.tif").exists()
    and (PROCESSED_DATA_DIR / "HIRISE_ROUGHNESS_GALE_MOUND.tif").exists()
)


def _create_sample_eva_config() -> EvaConfig:
    return get_default_eva_response().config


def _create_sample_datasets() -> list[DatasetRecord]:
    from app.services.region_service import list_datasets

    return list_datasets("gale_mount_sharp")


def _create_sample_checks(
    slope_status: AssessmentStatus = AssessmentStatus.PASS,
    slope_val: float = 8.5,
) -> list[SafetyCheck]:
    ev = [EvidenceRef(source_type="dataset", source_id="HIRISE_DTM_GALE_MOUND")]
    return [
        SafetyCheck(
            check_id="SLOPE_MAX",
            critical=True,
            status=slope_status,
            value=slope_val,
            threshold=15.0,
            units="degrees",
            message=f"Maximum slope {slope_val:.1f}° vs threshold 15.0°",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="HAZARD_INTERSECTION",
            critical=True,
            status=AssessmentStatus.PASS,
            value=0.0,
            threshold=0.0,
            units="cells",
            message="No hazard intersections detected",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="TERRAIN_DATA_COVERAGE",
            critical=True,
            status=AssessmentStatus.PASS,
            value=1.0,
            threshold=1.0,
            units="fraction",
            message="100% terrain data coverage",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="EVA_DURATION",
            critical=False,
            status=AssessmentStatus.PASS,
            value=3450.0,
            threshold=21600.0,
            units="seconds",
            message="EVA duration within available budget",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="RETURN_RESERVE",
            critical=False,
            status=AssessmentStatus.PASS,
            value=18150.0,
            threshold=5400.0,
            units="seconds",
            message="Return reserve margin satisfied",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="ROUGHNESS",
            critical=False,
            status=AssessmentStatus.PASS,
            value=0.05,
            threshold=0.30,
            units="metres",
            message="Roughness within warning threshold",
            evidence=ev,
        ),
        SafetyCheck(
            check_id="DISTANCE_FROM_BASE",
            critical=False,
            status=AssessmentStatus.PASS,
            value=1200.0,
            threshold=2000.0,
            units="metres",
            message="Distance within reference limit",
            evidence=ev,
        ),
    ]


def _create_sample_route(
    route_id: str = "rt_sample_01",
    overall_status: AssessmentStatus = AssessmentStatus.PASS,
    slope_max_status: AssessmentStatus = AssessmentStatus.PASS,
    slope_max_val: float = 8.5,
) -> Route:
    from app.engines.safety.context import (
        build_radiation_context_indicator,
        build_thermal_context_indicator,
    )

    return Route(
        route_id=route_id,
        objective=RouteObjective.LOWEST_RISK,
        legs=[
            RouteLeg(
                from_label="Base",
                to_label="Destination",
                path=[GeoPoint(lat=-4.75, lon=137.28), GeoPoint(lat=-4.78, lon=137.30)],
                horizontal_distance_m=1200.0,
                surface_distance_m=1250.0,
                ascent_m=40.0,
                descent_m=10.0,
                walk_time_s=1800.0,
            )
        ],
        path=[GeoPoint(lat=-4.75, lon=137.28), GeoPoint(lat=-4.78, lon=137.30)],
        elevation_profile=[
            ProfilePoint(
                point=GeoPoint(lat=-4.75, lon=137.28),
                distance_m=0.0,
                elevation_m=-3900.0,
                slope_deg=5.0,
            ),
            ProfilePoint(
                point=GeoPoint(lat=-4.78, lon=137.30),
                distance_m=1250.0,
                elevation_m=-3870.0,
                slope_deg=6.0,
            ),
        ],
        slope_stats=StatSummary(max=slope_max_val, mean=5.5, p95=7.8, units="degrees"),
        roughness_stats=StatSummary(max=0.05, mean=0.015, p95=0.035, units="metres"),
        fraction_above_warning_slope=0.02,
        max_distance_from_base_m=1200.0,
        timeline=[
            TimelineEntry(
                kind=TimelineKind.WALK, label="Walk Outbound", start_s=0.0, duration_s=1800.0
            ),
            TimelineEntry(
                kind=TimelineKind.MARGIN,
                label="Contingency Margin",
                start_s=1800.0,
                duration_s=450.0,
            ),
            TimelineEntry(
                kind=TimelineKind.WORK, label="Science Work", start_s=2250.0, duration_s=1200.0
            ),
        ],
        totals=RouteTotals(
            horizontal_distance_m=1200.0,
            surface_distance_m=1250.0,
            walk_time_s=1800.0,
            margin_time_s=450.0,
            work_time_s=1200.0,
            total_time_s=3450.0,
            time_available_s=21600.0,
            reserve_required_s=5400.0,
            reserve_remaining_s=18150.0,
        ),
        safety=SafetyAssessment(
            overall_status=overall_status,
            checks=_create_sample_checks(slope_max_status, slope_max_val),
            context=[
                build_radiation_context_indicator(),
                build_thermal_context_indicator(),
            ],
            disclaimer=SAFETY_DISCLAIMER_TEXT,
        ),
        primary_coverage_fraction=1.0,
        evidence=[EvidenceRef(source_type="dataset", source_id="HIRISE_DTM_GALE_MOUND")],
        limitations=["Endpoint snapped 2.0 m to passable cell"],
    )


def _create_sample_plan(routes: list[Route] | None = None) -> RoutePlanResponse:
    r_list = routes if routes is not None else [_create_sample_route()]
    return RoutePlanResponse(
        plan_id="pln_test_001",
        region_id="gale_mount_sharp",
        plan_status=PlanStatus.OK,
        blocking_reason=None,
        routes=r_list,
        omitted_objectives=[],
        eva_config=_create_sample_eva_config(),
        assumptions=get_default_eva_response().assumptions,
        grid=GridInfo(
            analysis_crs="+proj=eqc +lat_ts=-4.8 +lon_0=137.3 +units=m",
            cell_size_m=5.0,
            rows=200,
            cols=200,
        ),
        computed_at=datetime(2026, 11, 14, 20, 0, 0, tzinfo=timezone.utc),
        engine_version="0.2.0",
    )


def _create_sample_mission_state(
    selected_route_id: str | None = "rt_sample_01",
    plan: RoutePlanResponse | None = None,
    no_plan: bool = False,
    with_agent: bool = False,
    eva_override: dict | None = None,
    safety_status: AssessmentStatus | None = None,
) -> MissionState:
    cfg = _create_sample_eva_config()
    if eva_override:
        cfg_dict = cfg.model_dump()
        cfg_dict.update(eva_override)
        cfg = EvaConfig(**cfg_dict)

    if safety_status is not None:
        slope_st = (
            AssessmentStatus.BLOCKED
            if safety_status == AssessmentStatus.BLOCKED
            else (
                AssessmentStatus.WARNING
                if safety_status == AssessmentStatus.WARNING
                else AssessmentStatus.PASS
            )
        )
        slope_val = (
            22.4
            if safety_status == AssessmentStatus.BLOCKED
            else (12.0 if safety_status == AssessmentStatus.WARNING else 4.5)
        )
        rt = _create_sample_route(
            overall_status=safety_status,
            slope_max_status=slope_st,
            slope_max_val=slope_val,
        )
        plan = _create_sample_plan(routes=[rt])

    agent_analysis = None
    if with_agent:
        agent_analysis = AgentAnalysisResponse(
            run_id="run_test_01",
            llm_mode="ENABLED",
            agents=[
                AgentResult(
                    agent="safety",
                    status="SUCCESS",
                    mode="deterministic",
                    summary="Safety assessment clear",
                    findings=[],
                    warnings=[],
                    duration_ms=45,
                )
            ],
            synthesis=AgentSynthesis(
                summary="Traverse displays favourable slope profiles across Mount Sharp mound.",
                recommendations=["Maintain visual scan for localized decameter boulders."],
                unresolved_issues=["No high-resolution thermal inertia layer available."],
                data_class=DataClass.AI_INTERPRETATION,
            ),
            computed_at=datetime(2026, 11, 14, 20, 0, 0, tzinfo=timezone.utc),
        )

    effective_plan = None if no_plan else (plan if plan is not None else _create_sample_plan())

    return MissionState(
        mission_id="msn_test_gale_01",
        created_at=datetime(2026, 11, 14, 18, 0, 0, tzinfo=timezone.utc),
        name="Mount Sharp Expedition Alpha",
        region_id="gale_mount_sharp",
        objective_text="Sample geological contact boundary at lower Mount Sharp mound.",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[
            Stop(
                stop_id="stp_01",
                name="Stop 1",
                point=GeoPoint(lat=-4.765, lon=137.29),
                work_time_min=20.0,
            )
        ],
        eva_config=cfg,
        plan=effective_plan,
        selected_route_id=selected_route_id,
        envelope=None,
        agent_analysis=agent_analysis,
        notes="Standard planning profile.",
    )


def test_section_ids_and_order_without_ai():
    """Verify that section IDs match spec 14.2 exactly in fixed order (11 sections without AI)."""
    ms = _create_sample_mission_state(with_agent=False)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    catalog = _create_sample_datasets()

    report = build_mission_report(ms, region, catalog)

    expected_ids = [
        "overview",
        "science",
        "datasets",
        "terrain",
        "selected_route",
        "eva_timeline",
        "safety",
        "alternatives",
        "assumptions",
        "limitations",
        "disclaimer",
    ]
    actual_ids = [s.section_id for s in report.sections]
    assert actual_ids == expected_ids


def test_section_ids_and_order_with_ai():
    """Verify that with agent_analysis, section 11 ai_interpretation appears in order.

    Expected 12 sections.
    """
    ms = _create_sample_mission_state(with_agent=True)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    catalog = _create_sample_datasets()

    report = build_mission_report(ms, region, catalog)

    expected_ids = [
        "overview",
        "science",
        "datasets",
        "terrain",
        "selected_route",
        "eva_timeline",
        "safety",
        "alternatives",
        "assumptions",
        "limitations",
        "ai_interpretation",
        "disclaimer",
    ]
    actual_ids = [s.section_id for s in report.sections]
    assert actual_ids == expected_ids

    ai_sec = next(s for s in report.sections if s.section_id == "ai_interpretation")
    assert ai_sec.data_class == DataClass.AI_INTERPRETATION
    assert "This section is an AI interpretation" in ai_sec.body_markdown


def test_disclaimer_verbatim():
    """Verify character-by-character that report disclaimer equals the verbatim spec 14.1 text."""
    expected_disclaimer = (
        "AresNav is a research and planning prototype. Results are computational "
        "assessments under stated assumptions and are not a certified astronaut safety analysis."
    )
    assert SAFETY_DISCLAIMER_TEXT == expected_disclaimer

    ms = _create_sample_mission_state()
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())

    assert report.disclaimer == expected_disclaimer
    disclaimer_sec = next(s for s in report.sections if s.section_id == "disclaimer")
    assert disclaimer_sec.body_markdown == expected_disclaimer


def test_blocked_route_never_pass_or_acceptable():
    """A BLOCKED route must never be summarized as acceptable, safe, or recommended."""
    blocked_route = _create_sample_route(
        route_id="rt_blocked_01",
        overall_status=AssessmentStatus.BLOCKED,
        slope_max_status=AssessmentStatus.BLOCKED,
        slope_max_val=22.4,
    )
    plan = _create_sample_plan(routes=[blocked_route])
    ms = _create_sample_mission_state(selected_route_id="rt_blocked_01", plan=plan)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }

    report = build_mission_report(ms, region, _create_sample_datasets())

    safety_sec = next(s for s in report.sections if s.section_id == "safety")
    assert "Overall Safety Status: BLOCKED." in safety_sec.body_markdown
    assert "Overall Safety Status: PASS" not in safety_sec.body_markdown
    assert "route not recommended" in safety_sec.body_markdown.lower()
    assert re.search(r"\bsafe\b", safety_sec.body_markdown, re.IGNORECASE) is None
    assert re.search(r"\bacceptable\b", safety_sec.body_markdown, re.IGNORECASE) is None
    assert "SLOPE_MAX" in safety_sec.body_markdown
    assert "22.40" in safety_sec.body_markdown


def test_missing_data_gives_unknown():
    """Missing base/destination coordinates and route plans report UNKNOWN, never PASS or 0."""
    ms = _create_sample_mission_state()
    ms.base = None
    ms.destination = None
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }

    report = build_mission_report(ms, region, _create_sample_datasets())

    overview_sec = next(s for s in report.sections if s.section_id == "overview")
    assert "Base Location**: UNKNOWN (not configured)" in overview_sec.body_markdown
    assert "Destination Location**: UNKNOWN (not configured)" in overview_sec.body_markdown
    assert any("Base coordinate not configured" in lim for lim in report.limitations)


def test_no_plan_state():
    """When plan is None, report generates with UNKNOWN safety status and explicit notices."""
    ms = _create_sample_mission_state(selected_route_id=None, no_plan=True)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }

    report = build_mission_report(ms, region, _create_sample_datasets())

    safety_sec = next(s for s in report.sections if s.section_id == "safety")
    assert "Overall Safety Status: UNKNOWN" in safety_sec.body_markdown

    terrain_sec = next(s for s in report.sections if s.section_id == "terrain")
    assert "not computed because no route plan exists" in terrain_sec.body_markdown

    timeline_sec = next(s for s in report.sections if s.section_id == "eva_timeline")
    assert "not computed because no route plan exists" in timeline_sec.body_markdown

    alt_sec = next(s for s in report.sections if s.section_id == "alternatives")
    assert "not computed because no route plan exists" in alt_sec.body_markdown


def test_no_feasible_route_state():
    """NO_FEASIBLE_ROUTE plan status preserves blocking reason verbatim."""
    plan = RoutePlanResponse(
        plan_id="pln_blocked_01",
        region_id="gale_mount_sharp",
        plan_status=PlanStatus.NO_FEASIBLE_ROUTE,
        blocking_reason="Computation limit: 30.0s exceeded during A* search",
        routes=[],
        omitted_objectives=[],
        eva_config=_create_sample_eva_config(),
        assumptions=get_default_eva_response().assumptions,
        grid=GridInfo(analysis_crs="+proj=eqc", cell_size_m=5.0, rows=10, cols=10),
        computed_at=datetime(2026, 11, 14, 20, 0, 0, tzinfo=timezone.utc),
        engine_version="0.2.0",
    )
    ms = _create_sample_mission_state(selected_route_id=None, plan=plan)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }

    report = build_mission_report(ms, region, _create_sample_datasets())

    sel_sec = next(s for s in report.sections if s.section_id == "selected_route")
    assert "Computation limit: 30.0s exceeded during A* search" in sel_sec.body_markdown

    alt_sec = next(s for s in report.sections if s.section_id == "alternatives")
    assert "Computation limit: 30.0s exceeded during A* search" in alt_sec.body_markdown


def test_nine_assumptions_labels():
    """Verify all 9 parameters from spec 6.2 are present with labels and exact literal values."""
    ms = _create_sample_mission_state()
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())

    keys = {a.key: a for a in report.assumptions}
    assert len(keys) == 9

    expected_labels = {
        "base_speed_kmh": DataClass.REFERENCE,
        "max_slope_deg": DataClass.REFERENCE,
        "warning_slope_deg": DataClass.REFERENCE,
        "max_distance_from_base_m": DataClass.REFERENCE,
        "max_eva_hours": DataClass.ASSUMPTION,
        "return_reserve_fraction": DataClass.ASSUMPTION,
        "traverse_time_margin": DataClass.ASSUMPTION,
        "default_work_time_min": DataClass.ASSUMPTION,
        "roughness_warning_m": DataClass.ASSUMPTION,
    }

    expected_values = {
        "base_speed_kmh": 2.7,
        "max_slope_deg": 15.0,
        "warning_slope_deg": 10.0,
        "max_distance_from_base_m": 2000.0,
        "max_eva_hours": 6.0,
        "return_reserve_fraction": 0.25,
        "traverse_time_margin": 1.25,
        "default_work_time_min": 20.0,
        "roughness_warning_m": 0.30,
    }

    for k, expected_cls in expected_labels.items():
        assert k in keys
        assert keys[k].data_class == expected_cls, f"Mismatch for parameter {k}"
        assert keys[k].value == expected_values[k], f"Mismatch for value {k}"


def test_assumptions_override_r4():
    """R4: An overridden parameter gets data_class ASSUMPTION, override basis, and limitation."""
    ms = _create_sample_mission_state(eva_override={"max_eva_hours": 5.0})
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }

    report = build_mission_report(ms, region, _create_sample_datasets())

    hours_rec = next(a for a in report.assumptions if a.key == "max_eva_hours")
    assert hours_rec.value == 5.0
    assert hours_rec.data_class == DataClass.ASSUMPTION
    assert hours_rec.basis == "user override of default 6.0"

    assert any(
        "EvaConfig override: max_eva_hours set to 5.0 (default 6.0)" in lim
        for lim in report.limitations
    )


@pytest.mark.parametrize(
    "status,with_agent",
    [
        ("PASS", False),
        ("PASS", True),
        ("WARNING", False),
        ("WARNING", True),
        ("BLOCKED", False),
        ("BLOCKED", True),
        ("NO_PLAN", False),
        ("NO_PLAN", True),
        ("NO_FEASIBLE_ROUTE", False),
        ("NO_FEASIBLE_ROUTE", True),
    ],
)
def test_prohibited_wording_audit_r6(status: str, with_agent: bool):
    """R6: Strips exact disclaimer and verifies no prohibited words appear in any report state."""
    if status == "PASS":
        ms = _create_sample_mission_state(
            with_agent=with_agent, safety_status=AssessmentStatus.PASS
        )
    elif status == "WARNING":
        ms = _create_sample_mission_state(
            with_agent=with_agent, safety_status=AssessmentStatus.WARNING
        )
    elif status == "BLOCKED":
        ms = _create_sample_mission_state(
            with_agent=with_agent, safety_status=AssessmentStatus.BLOCKED
        )
    elif status == "NO_PLAN":
        ms = _create_sample_mission_state(with_agent=with_agent, no_plan=True)
    elif status == "NO_FEASIBLE_ROUTE":
        plan = RoutePlanResponse(
            plan_id="pln_blocked_01",
            region_id="gale_mount_sharp",
            plan_status=PlanStatus.NO_FEASIBLE_ROUTE,
            blocking_reason="Computation limit: 30.0s exceeded during A* search",
            routes=[],
            omitted_objectives=[],
            eva_config=_create_sample_eva_config(),
            assumptions=get_default_eva_response().assumptions,
            grid=GridInfo(analysis_crs="+proj=eqc", cell_size_m=5.0, rows=10, cols=10),
            computed_at=datetime(2026, 11, 14, 20, 0, 0, tzinfo=timezone.utc),
            engine_version="0.2.0",
        )
        ms = _create_sample_mission_state(with_agent=with_agent, selected_route_id=None, plan=plan)
    else:
        raise ValueError(f"Unknown status: {status}")

    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())

    md_without_disclaimer = report.markdown.replace(SAFETY_DISCLAIMER_TEXT, "")

    prohibited_pattern = re.compile(
        r"\b(safe route|safe site|astronaut-safe|guaranteed|"
        r"certified|approved|current conditions|live data)\b",
        re.IGNORECASE,
    )
    matches = prohibited_pattern.findall(md_without_disclaimer)
    assert matches == [], f"Found prohibited wording in report markdown ({status}): {matches}"


def test_report_reproducibility():
    """Identical inputs with fixed clock and id factory produce byte-for-byte identical reports."""
    ms = _create_sample_mission_state()
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    catalog = _create_sample_datasets()

    frozen_now = datetime(2026, 11, 14, 20, 30, 0, tzinfo=timezone.utc)

    def id_fn() -> str:
        return "rpt_fixed_id_12345"

    rep1 = build_mission_report(ms, region, catalog, now=frozen_now, id_factory=id_fn)
    rep2 = build_mission_report(ms, region, catalog, now=frozen_now, id_factory=id_fn)

    assert rep1.report_id == rep2.report_id
    assert rep1.generated_at == rep2.generated_at
    assert rep1.markdown == rep2.markdown
    assert [s.model_dump() for s in rep1.sections] == [s.model_dump() for s in rep2.sections]


def test_datasets_list_includes_unavailable_with_reasons():
    """Datasets section and report.datasets include unavailable datasets and their reasons."""
    ms = _create_sample_mission_state()
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    catalog = _create_sample_datasets()

    report = build_mission_report(ms, region, catalog)

    unavail = [d for d in report.datasets if d.status == DatasetStatus.UNAVAILABLE]
    assert len(unavail) >= 1
    assert unavail[0].status_reason is not None

    ds_sec = next(s for s in report.sections if s.section_id == "datasets")
    assert "MSL_RAD_SURFACE_RDR" in ds_sec.body_markdown
    assert "Specific sol tables unverified" in ds_sec.body_markdown
    assert (
        "Datasets read by routing engine: HIRISE_DTM_GALE_MOUND "
        "and the slope and roughness layers derived from it."
    ) in ds_sec.body_markdown


def test_status_sentence_pass():
    """C.5: PASS route uses spec 14.1 sentence and never claims safe or acceptable."""
    ms = _create_sample_mission_state(safety_status=AssessmentStatus.PASS)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())
    safety_sec = next(s for s in report.sections if s.section_id == "safety")

    assert "Overall Safety Status: PASS." in safety_sec.body_markdown
    assert (
        "The traverse meets the configured prototype criteria with no constraint "
        "violations detected."
    ) in safety_sec.body_markdown
    assert re.search(r"\bsafe\b", safety_sec.body_markdown, re.IGNORECASE) is None
    assert re.search(r"\bacceptable\b", safety_sec.body_markdown, re.IGNORECASE) is None


def test_status_sentence_warning():
    """C.5: WARNING route states advisory conditions detected; review recommended."""
    ms = _create_sample_mission_state(safety_status=AssessmentStatus.WARNING)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())
    safety_sec = next(s for s in report.sections if s.section_id == "safety")

    assert "Overall Safety Status: WARNING." in safety_sec.body_markdown
    assert (
        "No hard safety constraint is violated; advisory conditions were detected:"
    ) in safety_sec.body_markdown
    assert "Review is recommended before execution." in safety_sec.body_markdown
    assert "meets the configured prototype criteria" not in safety_sec.body_markdown


def test_status_sentence_blocked():
    """C.5: BLOCKED route states hard constraint violated; PASS never appears."""
    ms = _create_sample_mission_state(safety_status=AssessmentStatus.BLOCKED)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())
    safety_sec = next(s for s in report.sections if s.section_id == "safety")

    assert "Overall Safety Status: BLOCKED." in safety_sec.body_markdown
    assert (
        "At least one hard safety constraint is violated; route not recommended."
    ) in safety_sec.body_markdown
    assert "Overall Safety Status: PASS" not in safety_sec.body_markdown


def test_status_sentence_unknown():
    """C.5: UNKNOWN route states data are insufficient; PASS never appears."""
    ms = _create_sample_mission_state(no_plan=True)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())
    safety_sec = next(s for s in report.sections if s.section_id == "safety")

    assert "Overall Safety Status: UNKNOWN" in safety_sec.body_markdown
    assert (
        "Data are insufficient to evaluate safety constraints; treat as unverified."
    ) in safety_sec.body_markdown
    assert "Overall Safety Status: PASS" not in safety_sec.body_markdown


def test_markdown_contains_every_section_title_body_and_disclaimer_r14():
    """R14: markdown must contain every section title and body in order.

    Followed by the disclaimer.
    """
    ms = _create_sample_mission_state(with_agent=True)
    region = {
        "region_id": "gale_mount_sharp",
        "name": "Gale Crater",
        "analysis": {"analysis_crs": "+proj=eqc"},
    }
    report = build_mission_report(ms, region, _create_sample_datasets())

    for sec in report.sections:
        assert f"## {sec.title}" in report.markdown
        assert sec.body_markdown in report.markdown

    # The report ends with the disclaimer text
    assert report.markdown.strip().endswith(SAFETY_DISCLAIMER_TEXT)


def test_service_invalid_mission_state_route_mismatch():
    """ReportService raises 422 INVALID_MISSION_STATE when selected_route_id is not in plan."""
    ms = _create_sample_mission_state(selected_route_id="nonexistent_route_999")
    req = MissionReportRequest(mission_state=ms)
    svc = ReportService()

    with pytest.raises(AppException) as exc_info:
        svc.generate_report(req)

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code == "INVALID_MISSION_STATE"
    assert "nonexistent_route_999" in exc_info.value.message


def test_service_region_not_found():
    """ReportService raises 404 REGION_NOT_FOUND when region_id does not exist."""
    ms = _create_sample_mission_state()
    ms.region_id = "nonexistent_mars_region"
    req = MissionReportRequest(mission_state=ms)
    svc = ReportService()

    with pytest.raises(AppException) as exc_info:
        svc.generate_report(req)

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "REGION_NOT_FOUND"


def test_e2e_journey_synthetic():
    """B.1: End-to-end journey planning on synthetic EQC rasters and generating report."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "regions").mkdir(parents=True)
        (tmp_path / "manifests").mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        region_json = {
            "region_id": "synthetic_region",
            "name": "Synthetic Test Region",
            "description": "Synthetic testing region",
            "science_objective": "Test mission report pipeline end-to-end",
            "bounds": {"lat_min": -5.0, "lat_max": -4.0, "lon_min": 137.0, "lon_max": 138.0},
            "analysis": {
                "primary_dtm_dataset_id": "HIRISE_DTM_GALE_MOUND",
                "analysis_crs": (
                    "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=137.35 "
                    "+x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
                ),
                "cell_size_m": 5.0,
                "max_grid_cells": 100000,
            },
            "layers": [],
            "science_targets": [],
        }
        (tmp_path / "regions" / "synthetic_region.json").write_text(
            json.dumps(region_json), encoding="utf-8"
        )
        shutil.copy("data/manifests/dataset_catalog.json", tmp_path / "manifests")

        # Create synthetic rasters matching the region CRS
        r_mars = 3396190.0
        lat_c = -4.5
        lon_c = 137.5
        lon_0 = 137.35
        y_c = lat_c * math.pi * r_mars / 180.0
        x_c = (lon_c - lon_0) * math.pi * r_mars / 180.0

        dx, dy = 1.0, 1.0
        h, w = 100, 100
        west = x_c - (w / 2.0) * dx
        north = y_c + (h / 2.0) * dy
        transform = from_origin(west, north, dx, dy)
        crs = region_json["analysis"]["analysis_crs"]

        dtm_arr = np.full((h, w), -3500.0, dtype=np.float32)
        slope_arr = np.full((h, w), 2.0, dtype=np.float32)
        rough_arr = np.full((h, w), 0.05, dtype=np.float32)

        for name, arr in [
            ("HIRISE_DTM_GALE_MOUND.tif", dtm_arr),
            ("HIRISE_SLOPE_GALE_MOUND.tif", slope_arr),
            ("HIRISE_ROUGHNESS_GALE_MOUND.tif", rough_arr),
        ]:
            with rasterio.open(
                tmp_path / "processed" / name,
                "w",
                driver="GTiff",
                height=h,
                width=w,
                count=1,
                dtype="float32",
                crs=crs,
                transform=transform,
            ) as dst:
                dst.write(arr, 1)

        rt_service = RouteService(data_dir=tmp_path)
        req = RoutePlanRequest(
            region_id="synthetic_region",
            base=GeoPoint(lat=-4.5, lon=137.5),
            destination=GeoPoint(lat=-4.5002, lon=137.5002),
            stops=[],
            return_to_base=True,
        )
        plan = rt_service.plan_traverse(req)
        assert plan.plan_status == PlanStatus.OK
        assert len(plan.routes) >= 1

        selected_route = plan.routes[0]
        ms = MissionState(
            mission_id="msn_synth_01",
            name="Synthetic Mission",
            region_id="synthetic_region",
            base=req.base,
            destination=req.destination,
            stops=[],
            objective_text="Synthetic mission objective",
            plan=plan,
            selected_route_id=selected_route.route_id,
            created_at=datetime.now(timezone.utc),
            eva_config=plan.eva_config,
        )

        rep_service = ReportService(data_dir=tmp_path)
        report = rep_service.generate_report(MissionReportRequest(mission_state=ms))

        # Structural invariants only (no hand-typed numbers copied from engine output)
        expected_ids = [
            "overview",
            "science",
            "datasets",
            "terrain",
            "selected_route",
            "eva_timeline",
            "safety",
            "alternatives",
            "assumptions",
            "limitations",
            "disclaimer",
        ]
        assert [s.section_id for s in report.sections] == expected_ids
        assert report.disclaimer == SAFETY_DISCLAIMER_TEXT

        safety_sec = next(s for s in report.sections if s.section_id == "safety")
        assert selected_route.safety.overall_status.value in safety_sec.body_markdown

        for route_lim in selected_route.limitations:
            assert route_lim in report.limitations or any(
                route_lim in s.body_markdown for s in report.sections
            )

        cat_data = json.loads((tmp_path / "manifests" / "dataset_catalog.json").read_text("utf-8"))
        for ds_entry in cat_data["datasets"]:
            assert any(d.dataset_id == ds_entry["dataset_id"] for d in report.datasets)
            if ds_entry.get("status") == "UNAVAILABLE":
                matching = next(
                    d for d in report.datasets if d.dataset_id == ds_entry["dataset_id"]
                )
                assert matching.status_reason == ds_entry.get("status_reason")


@pytest.mark.skipif(not REAL_DATA_EXISTS, reason="Real processed Gale Crater rasters not present")
def test_e2e_real_gale_when_available():
    """B.2: Genuine end-to-end test on real Gale data asserting structural invariants."""
    rt_service = get_route_service()
    req = RoutePlanRequest(
        region_id="gale_mount_sharp",
        base=GeoPoint(lat=-4.75, lon=137.28),
        destination=GeoPoint(lat=-4.78, lon=137.30),
        stops=[],
        return_to_base=True,
    )
    plan = rt_service.plan_traverse(req)
    assert plan.plan_status == PlanStatus.OK
    assert len(plan.routes) >= 1

    selected_route = plan.routes[0]
    ms = MissionState(
        mission_id="msn_real_gale_01",
        name="Real Gale Traverse",
        region_id="gale_mount_sharp",
        base=req.base,
        destination=req.destination,
        stops=[],
        objective_text="Real Gale Mission",
        plan=plan,
        selected_route_id=selected_route.route_id,
        created_at=datetime.now(timezone.utc),
        eva_config=plan.eva_config,
    )

    rep_service = ReportService()
    report = rep_service.generate_report(MissionReportRequest(mission_state=ms))

    # Structural invariants
    expected_ids = [
        "overview",
        "science",
        "datasets",
        "terrain",
        "selected_route",
        "eva_timeline",
        "safety",
        "alternatives",
        "assumptions",
        "limitations",
        "disclaimer",
    ]
    assert [s.section_id for s in report.sections] == expected_ids
    assert report.disclaimer == SAFETY_DISCLAIMER_TEXT

    safety_sec = next(s for s in report.sections if s.section_id == "safety")
    assert selected_route.safety.overall_status.value in safety_sec.body_markdown

    for route_lim in selected_route.limitations:
        assert route_lim in report.limitations or any(
            route_lim in s.body_markdown for s in report.sections
        )

    real_catalog = list_datasets("gale_mount_sharp")
    for cat_ds in real_catalog:
        assert any(d.dataset_id == cat_ds.dataset_id for d in report.datasets)
        if cat_ds.status == DatasetStatus.UNAVAILABLE:
            matching = next(d for d in report.datasets if d.dataset_id == cat_ds.dataset_id)
            assert matching.status_reason == cat_ds.status_reason

    # Prohibited words check across entire report
    md_no_disclaimer = report.markdown.replace(SAFETY_DISCLAIMER_TEXT, "")
    prohibited_pattern = re.compile(
        r"\b(safe route|safe site|astronaut-safe|guaranteed|"
        r"certified|approved|current conditions|live data)\b",
        re.IGNORECASE,
    )
    matches = prohibited_pattern.findall(md_no_disclaimer)
    assert matches == [], f"Found prohibited wording in real Gale report: {matches}"


def test_api_route_handler_in_process():
    """Verify router function generate_mission_report in-process without socket network calls."""
    from app.api.routes.mission import generate_mission_report

    ms = _create_sample_mission_state()
    req = MissionReportRequest(mission_state=ms)
    report = generate_mission_report(req)
    assert report.report_id.startswith("rpt_")
    assert report.mission_id == ms.mission_id
    assert report.disclaimer == SAFETY_DISCLAIMER_TEXT
    assert len(report.sections) == 11
    assert report.markdown.strip().endswith(SAFETY_DISCLAIMER_TEXT)
