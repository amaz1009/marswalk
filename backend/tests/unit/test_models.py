"""Unit tests for shared models, OpenAPI schema, and endpoint stubs (T-MODEL-01, T-API-09)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import (
    AgentRunStatus,
    AssessmentStatus,
    ConfidenceLevel,
    ContextIndicatorId,
    ContextStatus,
    DataClass,
    DatasetRecord,
    DatasetStatus,
    DataType,
    EvaConfig,
    EvidenceRef,
    Finding,
    GeoBounds,
    GeoPoint,
    LayerKind,
    LlmMode,
    MissionReport,
    MissionState,
    PlanStatus,
    RouteObjective,
    SafetyCheckId,
    SiteWeights,
    TemporalCoverage,
    TimelineKind,
    ValueStatus,
)


def test_t_model_01_enum_values() -> None:
    """T-MODEL-01: Enum values match docs/API_CONTRACTS.md §2 exactly."""
    assert [e.value for e in AssessmentStatus] == ["PASS", "WARNING", "BLOCKED", "UNKNOWN"]
    assert [e.value for e in DataClass] == [
        "MEASURED",
        "DERIVED",
        "MODEL",
        "REFERENCE",
        "ASSUMPTION",
        "SAMPLE",
        "AI_INTERPRETATION",
    ]
    assert [e.value for e in DatasetStatus] == ["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    assert [e.value for e in DataType] == [
        "ELEVATION",
        "OPTICAL",
        "THERMAL",
        "GEOLOGY",
        "MINERALOGY",
        "RADIATION",
        "SURFACE_IMAGE",
        "ICE",
        "DERIVED",
    ]
    assert [e.value for e in LayerKind] == ["RASTER", "VECTOR"]
    assert [e.value for e in ValueStatus] == ["OK", "NO_COVERAGE", "UNAVAILABLE"]
    assert [e.value for e in RouteObjective] == ["LOWEST_RISK", "BALANCED", "MAX_SCIENCE"]
    assert [e.value for e in PlanStatus] == ["OK", "NO_FEASIBLE_ROUTE", "INSUFFICIENT_DATA"]
    assert [e.value for e in TimelineKind] == ["WALK", "WORK", "MARGIN", "RESERVE"]
    assert [e.value for e in ContextStatus] == ["AVAILABLE", "UNAVAILABLE"]
    assert [e.value for e in ConfidenceLevel] == ["HIGH", "MEDIUM", "LOW", "NONE"]
    assert [e.value for e in LlmMode] == ["DISABLED", "ENABLED"]
    assert [e.value for e in AgentRunStatus] == ["SUCCESS", "DEGRADED", "FAILED", "SKIPPED"]
    assert [e.value for e in SafetyCheckId] == [
        "SLOPE_MAX",
        "HAZARD_INTERSECTION",
        "TERRAIN_DATA_COVERAGE",
        "EVA_DURATION",
        "RETURN_RESERVE",
        "ROUGHNESS",
        "DISTANCE_FROM_BASE",
    ]
    assert [e.value for e in ContextIndicatorId] == ["RADIATION_CONTEXT", "THERMAL_CONTEXT"]


def test_t_model_01_geopoint_validation() -> None:
    """T-MODEL-01: GeoPoint validates latitude and normalizes longitude."""
    # Valid normal coordinates
    pt = GeoPoint(lat=-5.3, lon=137.4)
    assert pt.lat == -5.3
    assert pt.lon == 137.4

    # Normalization of negative longitude [-180, 0)
    pt_neg = GeoPoint(lat=0.0, lon=-180.0)
    assert pt_neg.lon == 180.0

    pt_neg2 = GeoPoint(lat=10.0, lon=-22.5)
    assert pt_neg2.lon == 337.5

    # Out of range latitude
    with pytest.raises(ValidationError):
        GeoPoint(lat=-90.1, lon=100.0)
    with pytest.raises(ValidationError):
        GeoPoint(lat=90.1, lon=100.0)

    # Out of range longitude (outside [-180, 360))
    with pytest.raises(ValidationError):
        GeoPoint(lat=0.0, lon=-180.1)
    with pytest.raises(ValidationError):
        GeoPoint(lat=0.0, lon=360.0)


def test_t_model_01_geobounds_validation() -> None:
    """T-MODEL-01: GeoBounds rejects lat_min >= lat_max and allows wrapping lon."""
    bounds = GeoBounds(lat_min=-10.0, lat_max=10.0, lon_min=350.0, lon_max=10.0)
    assert bounds.lat_min == -10.0
    assert bounds.lon_min == 350.0

    with pytest.raises(ValidationError):
        GeoBounds(lat_min=10.0, lat_max=5.0, lon_min=0.0, lon_max=10.0)
    with pytest.raises(ValidationError):
        GeoBounds(lat_min=5.0, lat_max=5.0, lon_min=0.0, lon_max=10.0)


def test_t_model_01_evaconfig_validation() -> None:
    """T-MODEL-01: EvaConfig enforces slope relationships and valid ranges."""
    cfg = EvaConfig(base_speed_kmh=2.7, max_slope_deg=20.0, warning_slope_deg=15.0)
    assert cfg.base_speed_kmh == 2.7

    # warning_slope_deg >= max_slope_deg rejected
    with pytest.raises(ValidationError):
        EvaConfig(max_slope_deg=15.0, warning_slope_deg=15.0)
    with pytest.raises(ValidationError):
        EvaConfig(max_slope_deg=15.0, warning_slope_deg=20.0)

    # Out of range speed
    with pytest.raises(ValidationError):
        EvaConfig(base_speed_kmh=0.0)
    with pytest.raises(ValidationError):
        EvaConfig(base_speed_kmh=6.1)


def test_t_model_01_dataset_record_validation() -> None:
    """T-MODEL-01: DatasetRecord requires status_reason when not AVAILABLE and min 1 limitation."""
    # Valid available record
    ds = DatasetRecord(
        dataset_id="TEST_DTM",
        name="Test DTM",
        mission="MRO",
        instrument="HiRISE",
        source_archive="NASA PDS",
        source_url="https://example.com",
        product_ids=["PROD_1"],
        citation="Test citation",
        data_type=DataType.ELEVATION,
        data_class=DataClass.MEASURED,
        source_crs="+proj=eqc",
        source_conventions="planetocentric",
        temporal_coverage=TemporalCoverage(description="Static"),
        status=DatasetStatus.AVAILABLE,
        limitations=["Resolution limited to 1m"],
    )
    assert ds.dataset_id == "TEST_DTM"

    # Missing limitations rejected
    with pytest.raises(ValidationError):
        DatasetRecord(
            dataset_id="TEST_DTM",
            name="Test DTM",
            mission="MRO",
            instrument="HiRISE",
            source_archive="NASA PDS",
            source_url="https://example.com",
            product_ids=["PROD_1"],
            citation="Test citation",
            data_type=DataType.ELEVATION,
            data_class=DataClass.MEASURED,
            source_crs="+proj=eqc",
            source_conventions="planetocentric",
            temporal_coverage=TemporalCoverage(description="Static"),
            status=DatasetStatus.AVAILABLE,
            limitations=[],
        )

    # UNAVAILABLE without status_reason rejected
    with pytest.raises(ValidationError):
        DatasetRecord(
            dataset_id="TEST_DTM",
            name="Test DTM",
            mission="MRO",
            instrument="HiRISE",
            source_archive="NASA PDS",
            source_url="https://example.com",
            product_ids=["PROD_1"],
            citation="Test citation",
            data_type=DataType.ELEVATION,
            data_class=DataClass.MEASURED,
            source_crs="+proj=eqc",
            source_conventions="planetocentric",
            temporal_coverage=TemporalCoverage(description="Static"),
            status=DatasetStatus.UNAVAILABLE,
            limitations=["None"],
        )


def test_t_model_01_siteweights_validation() -> None:
    """T-MODEL-01: SiteWeights must sum to 1.0 +- 0.001."""
    weights = SiteWeights(
        terrain=0.2, human_safety=0.2, science=0.2, resources=0.2, accessibility=0.2
    )
    assert weights.terrain == 0.2

    with pytest.raises(ValidationError):
        SiteWeights(terrain=0.1, human_safety=0.1, science=0.1, resources=0.1, accessibility=0.1)


def test_t_model_01_finding_evidence_validation() -> None:
    """T-MODEL-01: Finding requires at least one evidence item."""
    finding = Finding(
        statement="Safe slope detected",
        data_class=DataClass.DERIVED,
        evidence=[EvidenceRef(source_type="engine", source_id="engines.routing")],
        confidence=ConfidenceLevel.HIGH,
    )
    assert len(finding.evidence) == 1

    with pytest.raises(ValidationError):
        Finding(
            statement="No evidence",
            data_class=DataClass.DERIVED,
            evidence=[],
            confidence=ConfidenceLevel.LOW,
        )


def test_t_model_01_mission_state_and_report_prefixes() -> None:
    """T-MODEL-01: Identifiers enforce msn_ and rpt_ prefixes."""
    now = datetime.now(timezone.utc)
    msn = MissionState(
        mission_id="msn_12345678",
        created_at=now,
        name="Test EVA",
        region_id="gale_mount_sharp",
        objective_text="Test geology",
        eva_config=EvaConfig(),
    )
    assert msn.mission_id == "msn_12345678"

    with pytest.raises(ValidationError):
        MissionState(
            mission_id="invalid_id",
            created_at=now,
            name="Test EVA",
            region_id="gale_mount_sharp",
            objective_text="Test geology",
            eva_config=EvaConfig(),
        )

    rpt = MissionReport(
        report_id="rpt_12345678",
        generated_at=now,
        mission_id="msn_12345678",
        disclaimer="Prototype",
        sections=[],
        markdown="# Report",
        engine_version="0.1.0",
    )
    assert rpt.report_id == "rpt_12345678"

    with pytest.raises(ValidationError):
        MissionReport(
            report_id="invalid_rpt",
            generated_at=now,
            mission_id="msn_12345678",
            disclaimer="Prototype",
            sections=[],
            markdown="# Report",
            engine_version="0.1.0",
        )


def test_stubs_return_not_implemented_envelope(client: TestClient) -> None:
    """Verify stub endpoints return 501 NOT_IMPLEMENTED with standard error envelope."""
    # Test a representative set of stub endpoints
    stub_calls = [
        ("GET", "/api/v1/regions"),
        ("GET", "/api/v1/regions/gale_mount_sharp"),
        ("GET", "/api/v1/datasets"),
        ("GET", "/api/v1/layers"),
        ("GET", "/api/v1/eva/defaults"),
        (
            "POST",
            "/api/v1/routes/plan",
            {
                "region_id": "gale",
                "base": {"lat": 0, "lon": 0},
                "destination": {"lat": 0, "lon": 0},
            },
        ),
        (
            "POST",
            "/api/v1/mission/report",
            {
                "mission_state": {
                    "mission_id": "msn_1",
                    "created_at": "2026-11-14T00:00:00Z",
                    "name": "n",
                    "region_id": "gale",
                    "objective_text": "obj",
                    "eva_config": {},
                }
            },
        ),
        (
            "POST",
            "/api/v1/agents/analyze",
            {
                "mission_state": {
                    "mission_id": "msn_1",
                    "created_at": "2026-11-14T00:00:00Z",
                    "name": "n",
                    "region_id": "gale",
                    "objective_text": "obj",
                    "eva_config": {},
                }
            },
        ),
    ]

    for item in stub_calls:
        method = item[0]
        path = item[1]
        json_body = item[2] if len(item) > 2 else None

        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json=json_body)

        assert response.status_code == 501, f"{path} returned status {response.status_code}"
        data = response.json()
        assert data["error_code"] == "NOT_IMPLEMENTED"
        assert data["message"] == "Endpoint belongs to an unmerged work package"
        assert "request_id" in data
        assert data["request_id"].startswith("req_")


def test_t_api_09_openapi_schema_drift() -> None:
    """T-API-09: scripts/export_openapi.py output equals committed docs/openapi.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    openapi_file = repo_root / "docs" / "openapi.json"
    assert openapi_file.exists(), "docs/openapi.json does not exist"

    committed_text = openapi_file.read_text(encoding="utf-8")
    generated_schema = app.openapi()
    generated_text = json.dumps(generated_schema, indent=2, sort_keys=True) + "\n"

    assert committed_text == generated_text, (
        "OpenAPI schema drift detected between app.openapi() and docs/openapi.json"
    )
