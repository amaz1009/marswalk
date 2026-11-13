"""Health check model implementing docs/API_CONTRACTS.md §4.1."""

from pydantic import BaseModel, Field

from app.models.enums import LlmMode


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(default="ok", description="Service status indicator")
    version: str = Field(..., description="API package version")
    llm_mode: LlmMode = Field(..., description="LLM enablement mode")
    llm_provider: str | None = Field(default=None, description="Active LLM provider if enabled")
    regions_loaded: int = Field(default=0, description="Number of loaded regions", ge=0)
    datasets_available: int = Field(default=0, description="Count of online datasets", ge=0)
    datasets_unavailable: int = Field(
        default=0, description="Count of offline or unretrieved datasets", ge=0
    )
