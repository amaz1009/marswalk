"""Error models, custom exceptions, and exception handlers implementing docs/API_CONTRACTS.md §6."""

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import logger


class ErrorEnvelope(BaseModel):
    """Standard error envelope for all non-2xx responses."""

    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class AppException(Exception):
    """Base application exception for controlled API errors."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _get_request_id(request: Request) -> str:
    """Retrieve existing request ID from request state or generate a fallback."""
    req_id = getattr(request.state, "request_id", None)
    if req_id:
        return str(req_id)
    return f"req_{uuid.uuid4().hex[:12]}"


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.warning(
            "AppException [%s]: %s (request_id=%s)",
            exc.error_code,
            exc.message,
            request_id,
        )
        content = ErrorEnvelope(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        ).model_dump()
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.warning(
            "Request validation error (request_id=%s): %s",
            request_id,
            exc.errors(),
        )
        # Simplify errors for serialization if needed
        errors_serialized = []
        for err in exc.errors():
            loc = [str(x) for x in err.get("loc", [])]
            errors_serialized.append(
                {
                    "loc": loc,
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        content = ErrorEnvelope(
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": errors_serialized},
            request_id=request_id,
        ).model_dump()
        return JSONResponse(status_code=422, content=content)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        # Default error code mapping
        code_map = {
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            501: "NOT_IMPLEMENTED",
            504: "GATEWAY_TIMEOUT",
        }
        error_code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(exc.detail) if exc.detail else "HTTP error"
        content = ErrorEnvelope(
            error_code=error_code,
            message=message,
            details={},
            request_id=request_id,
        ).model_dump()
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.exception("Unhandled server exception (request_id=%s): %s", request_id, exc)
        content = ErrorEnvelope(
            error_code="INTERNAL_ERROR",
            message="An unexpected server error occurred.",
            details={},
            request_id=request_id,
        ).model_dump()
        return JSONResponse(status_code=500, content=content)
