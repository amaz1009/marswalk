"""Tests for health endpoint and error envelope (T-API-01, T-API-02)."""

from fastapi import APIRouter, Query
from fastapi.testclient import TestClient

from app.core.errors import AppException
from app.main import app

# Add a test-only router to verify validation and internal error handlers
_test_router = APIRouter(prefix="/_test", tags=["TestOnly"])


@_test_router.get("/validation")
def _sample_validation_endpoint(count: int = Query(..., description="Integer count")):
    return {"count": count}


@_test_router.get("/app-error")
def _sample_app_error_endpoint():
    raise AppException(
        error_code="POINT_OUTSIDE_REGION",
        message="The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp.",
        status_code=422,
        details={"region_id": "gale_mount_sharp"},
    )


@_test_router.get("/server-error")
def _sample_server_error_endpoint():
    raise RuntimeError("Simulated unexpected crash")


app.include_router(_test_router)


def test_health_returns_schema_and_disabled_mode(client: TestClient) -> None:
    """T-API-01: Health returns documented schema with llm_mode DISABLED by default."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["llm_mode"] == "DISABLED"
    assert data["llm_provider"] is None
    assert data["regions_loaded"] == 0
    assert data["datasets_available"] == 0
    assert data["datasets_unavailable"] == 0

    # Ensure X-Request-ID header is present and formatted
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"].startswith("req_")


def test_404_error_envelope(client: TestClient) -> None:
    """T-API-02: 404 response uses standard error envelope with request_id and no stack trace."""
    response = client.get("/api/v1/nonexistent_path")
    assert response.status_code == 404

    data = response.json()
    assert "error_code" in data
    assert data["error_code"] == "NOT_FOUND"
    assert "message" in data
    assert "details" in data
    assert "request_id" in data
    assert data["request_id"].startswith("req_")

    # Verify no stack trace or traceback leaked in response
    assert "traceback" not in response.text.lower()
    assert "exception" not in response.text.lower()


def test_422_validation_error_envelope(client: TestClient) -> None:
    """T-API-02: 422 validation response replaces FastAPI default with envelope."""
    response = client.get("/_test/validation?count=not_an_int")
    assert response.status_code == 422

    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"
    assert data["message"] == "Request validation failed"
    assert "errors" in data["details"]
    assert "request_id" in data
    assert data["request_id"].startswith("req_")
    assert "traceback" not in response.text.lower()


def test_app_exception_envelope(client: TestClient) -> None:
    """T-API-02: Controlled AppException returns specified error envelope and status."""
    response = client.get("/_test/app-error")
    assert response.status_code == 422

    data = response.json()
    assert data["error_code"] == "POINT_OUTSIDE_REGION"
    assert data["message"] == "The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp."
    assert data["details"] == {"region_id": "gale_mount_sharp"}
    assert data["request_id"].startswith("req_")


def test_500_internal_error_envelope_suppresses_traceback() -> None:
    """T-API-02: Unhandled exception returns 500 INTERNAL_ERROR without leaking traceback."""
    # Use client with raise_server_exceptions=False to receive the 500 response
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        response = no_raise_client.get("/_test/server-error")
        assert response.status_code == 500

        data = response.json()
        assert data["error_code"] == "INTERNAL_ERROR"
        assert data["message"] == "An unexpected server error occurred."
        assert data["details"] == {}
        assert data["request_id"].startswith("req_")
        assert "Simulated unexpected crash" not in response.text
        assert "traceback" not in response.text.lower()
