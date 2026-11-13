"""Tests for health endpoint and error envelope (T-API-01, T-API-02)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppException, register_exception_handlers
from app.main import RequestIdMiddleware

# Test-specific app to test custom exceptions and 500 handler without polluting main app routes
_test_app = FastAPI()
_test_app.add_middleware(RequestIdMiddleware)
register_exception_handlers(_test_app)


@_test_app.get("/_test/app-error")
def _sample_app_error_endpoint():
    raise AppException(
        error_code="POINT_OUTSIDE_REGION",
        message="The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp.",
        status_code=422,
        details={"region_id": "gale_mount_sharp"},
    )


@_test_app.get("/_test/server-error")
def _sample_server_error_endpoint():
    raise RuntimeError("Simulated unexpected crash")


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
    # Use real contracted endpoint with invalid query parameter to trigger validation
    response = client.get("/api/v1/terrain/point?region_id=gale&lat=not_a_float&lon=100")
    assert response.status_code == 422

    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"
    assert data["message"] == "Request validation failed"
    assert "errors" in data["details"]
    assert "request_id" in data
    assert data["request_id"].startswith("req_")
    assert "traceback" not in response.text.lower()


def test_app_exception_envelope() -> None:
    """T-API-02: Controlled AppException returns specified error envelope and status."""
    with TestClient(_test_app) as client:
        response = client.get("/_test/app-error")
        assert response.status_code == 422

        data = response.json()
        assert data["error_code"] == "POINT_OUTSIDE_REGION"
        assert (
            data["message"] == "The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp."
        )
        assert data["details"] == {"region_id": "gale_mount_sharp"}
        assert data["request_id"].startswith("req_")


def test_500_internal_error_envelope_suppresses_traceback() -> None:
    """T-API-02: Unhandled exception returns 500 INTERNAL_ERROR without leaking traceback."""
    with TestClient(_test_app, raise_server_exceptions=False) as no_raise_client:
        response = no_raise_client.get("/_test/server-error")
        assert response.status_code == 500

        data = response.json()
        assert data["error_code"] == "INTERNAL_ERROR"
        assert data["message"] == "An unexpected server error occurred."
        assert data["details"] == {}
        assert data["request_id"].startswith("req_")
        assert "Simulated unexpected crash" not in response.text
        assert "traceback" not in response.text.lower()
