"""Health check model implementing docs/API_CONTRACTS.md §4.1."""

from pydantic import BaseModel, Field

from app.models.enums import LlmMode


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Service status indicator")
    version: str = Field(..., description="API package version")
    llm_mode: LlmMode = Field(..., description="LLM enablement mode")
    llm_provider: str | None = Field(default=None, description="Active LLM provider if enabled")
    regions_loaded: int = Field(..., description="Number of loaded regions", ge=0)
    datasets_available: int = Field(..., description="Count of online datasets", ge=0)
    datasets_unavailable: int = Field(
        ..., description="Count of offline or unretrieved datasets", ge=0
    )
