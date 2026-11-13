"""FastAPI application entry point for MARSWALK."""

import uuid

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.api.routes import health
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging

# Initialize logging
setup_logging()
settings = get_settings()

app = FastAPI(
    title="MARSWALK API",
    description="Human-scale Mars EVA route planning backend",
    version=__version__,
    docs_url="/docs",
    redoc_url=None,
)


class RequestIdMiddleware:
    """Pure ASGI middleware ensuring every HTTP request has an assigned request ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check incoming headers for existing X-Request-ID
        req_id = None
        for key, value in scope.get("headers", []):
            if key.lower() == b"x-request-id":
                req_id = value.decode("latin1")
                break
        if not req_id:
            req_id = f"req_{uuid.uuid4().hex[:12]}"

        # Store in scope state so request.state.request_id is populated
        state = scope.setdefault("state", {})
        state["request_id"] = req_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", req_id.encode("latin1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# Wrap with RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers (including standard error envelope)
register_exception_handlers(app)

# Mount API v1 router
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)

app.include_router(api_v1_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.MARSWALK_API_HOST,
        port=settings.MARSWALK_API_PORT,
        reload=(settings.MARSWALK_ENV == "development"),
    )
