"""API tests for POST /api/v1/mission/report (T-API-08, T-SAFE-07).

Validates:
- Successful report synthesis returning 200 with MissionReport schema
- INVALID_MISSION_STATE returning 422 error envelope on mismatched route
- REGION_NOT_FOUND returning 404 error envelope on unknown region
- Fixed disclaimer and section order at API level
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.engines.safety.checks import SAFETY_DISCLAIMER_TEXT
from app.main import app
from app.models.enums import AssessmentStatus, PlanStatus, RouteObjective, TimelineKind
from app.models.eva import (
    GridInfo,
    ProfilePoint,
    Route,
    RouteLeg,
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
from app.models.mission import MissionReport, MissionReportRequest, MissionState
from app.services.eva_service import get_default_eva_response

client = TestClient(app)


def _create_sample_checks() -> list[SafetyCheck]:
    ev = [EvidenceRef(source_type="dataset", source_id="HIRISE_DTM_GALE_MOUND")]
    return [
        SafetyCheck(
            check_id="SLOPE_MAX",
            critical=True,
            status=AssessmentStatus.PASS,
            value=7.5,
            threshold=15.0,
            units="degrees",
            message="Maximum slope 7.5° vs threshold 15.0°",
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
            value=0.04,
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


def _build_test_mission_state(
    selected_route_id: str | None = "rt_01",
    region_id: str = "gale_mount_sharp",
) -> MissionState:
    from app.engines.safety.context import (
        build_radiation_context_indicator,
        build_thermal_context_indicator,
    )

    cfg = get_default_eva_response().config
    route = Route(
        route_id="rt_01",
        objective=RouteObjective.LOWEST_RISK,
        legs=[
            RouteLeg(
                from_label="Base",
                to_label="Destination",
                path=[GeoPoint(lat=-4.75, lon=137.28), GeoPoint(lat=-4.78, lon=137.30)],
                horizontal_distance_m=1200.0,
                surface_distance_m=1250.0,
                ascent_m=30.0,
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
                elevation_m=-3880.0,
                slope_deg=5.0,
            ),
        ],
        slope_stats=StatSummary(max=7.5, mean=4.5, p95=6.8, units="degrees"),
        roughness_stats=StatSummary(max=0.04, mean=0.015, p95=0.03, units="metres"),
        fraction_above_warning_slope=0.0,
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
            overall_status=AssessmentStatus.PASS,
            checks=_create_sample_checks(),
            context=[
                build_radiation_context_indicator(),
                build_thermal_context_indicator(),
            ],
            disclaimer=SAFETY_DISCLAIMER_TEXT,
        ),
        primary_coverage_fraction=1.0,
        evidence=[EvidenceRef(source_type="dataset", source_id="HIRISE_DTM_GALE_MOUND")],
        limitations=[],
    )

    plan = RoutePlanResponse(
        plan_id="pln_api_01",
        region_id=region_id,
        plan_status=PlanStatus.OK,
        blocking_reason=None,
        routes=[route],
        omitted_objectives=[],
        eva_config=cfg,
        assumptions=get_default_eva_response().assumptions,
        grid=GridInfo(analysis_crs="+proj=eqc", cell_size_m=5.0, rows=100, cols=100),
        computed_at=datetime(2026, 11, 14, 20, 0, 0, tzinfo=timezone.utc),
        engine_version="0.2.0",
    )

    return MissionState(
        mission_id="msn_api_test_01",
        created_at=datetime(2026, 11, 14, 18, 0, 0, tzinfo=timezone.utc),
        name="API Test Mission",
        region_id=region_id,
        objective_text="Test mission report synthesis API.",
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
        plan=plan,
        selected_route_id=selected_route_id,
        envelope=None,
        agent_analysis=None,
        notes="API test run.",
    )


def test_post_mission_report_success():
    """POST /api/v1/mission/report returns 200 with valid MissionReport payload."""
    ms = _build_test_mission_state()
    req = MissionReportRequest(mission_state=ms)

    response = client.post("/api/v1/mission/report", json=req.model_dump(mode="json"))
    assert response.status_code == 200

    report = MissionReport.model_validate(response.json())
    assert report.report_id.startswith("rpt_")
    assert report.mission_id == ms.mission_id
    assert report.disclaimer == SAFETY_DISCLAIMER_TEXT
    assert len(report.sections) == 11
    assert len(report.assumptions) == 9
    assert report.markdown.strip().endswith(SAFETY_DISCLAIMER_TEXT)


def test_post_mission_report_no_plan():
    """POST /api/v1/mission/report with plan=None returns 200 with UNKNOWN safety state."""
    ms = _build_test_mission_state(selected_route_id=None)
    ms.plan = None
    req = MissionReportRequest(mission_state=ms)

    response = client.post("/api/v1/mission/report", json=req.model_dump(mode="json"))
    assert response.status_code == 200

    report = MissionReport.model_validate(response.json())
    safety_sec = next(s for s in report.sections if s.section_id == "safety")
    assert "Overall Safety Status: UNKNOWN" in safety_sec.body_markdown


def test_post_mission_report_invalid_route_422():
    """POST /api/v1/mission/report with mismatched selected_route_id returns 422 error envelope."""
    ms = _build_test_mission_state(selected_route_id="nonexistent_route_id")
    req = MissionReportRequest(mission_state=ms)

    response = client.post("/api/v1/mission/report", json=req.model_dump(mode="json"))
    assert response.status_code == 422

    body = response.json()
    assert body["error_code"] == "INVALID_MISSION_STATE"
    assert "nonexistent_route_id" in body["message"]


def test_post_mission_report_unknown_region_404():
    """POST /api/v1/mission/report with unknown region_id returns 404 error envelope."""
    ms = _build_test_mission_state(region_id="nonexistent_region")
    req = MissionReportRequest(mission_state=ms)

    response = client.post("/api/v1/mission/report", json=req.model_dump(mode="json"))
    assert response.status_code == 404

    body = response.json()
    assert body["error_code"] == "REGION_NOT_FOUND"
