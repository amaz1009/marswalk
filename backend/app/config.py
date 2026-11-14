"""Configuration settings loaded from environment or .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (three levels up: app/ -> backend/ -> repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """AresNav application settings implementing docs/API_CONTRACTS.md §7."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    ARESNAV_ENV: str = Field(default="development", description="development or test")
    ARESNAV_LOG_LEVEL: str = Field(default="INFO", description="Python log level")

    # --- API server ---
    ARESNAV_API_HOST: str = Field(default="127.0.0.1", description="Uvicorn bind host")
    ARESNAV_API_PORT: int = Field(default=8000, description="Uvicorn port")
    ARESNAV_CORS_ORIGINS: str = Field(
        default="http://localhost:5173",
        description="Comma-separated allowed origins",
    )

    # --- Data ---
    ARESNAV_DATA_DIR: Path = Field(
        default=Path("backend/data"),
        description="Data directory, relative to repository root",
    )
    ARESNAV_DEFAULT_REGION: str = Field(
        default="gale_mount_sharp",
        description="Region shown at start-up",
    )

    # --- Routing limits ---
    ARESNAV_MAX_GRID_CELLS: int = Field(
        default=4000000,
        description="Analysis grid cap per route request",
    )
    ARESNAV_ROUTE_TIMEOUT_S: float = Field(
        default=20.0,
        description="Hard timeout for one route plan in seconds",
    )

    # --- Optional LLM (default: none = deterministic mode) ---
    ARESNAV_LLM_PROVIDER: str = Field(
        default="none",
        description="none, anthropic, or openai",
    )
    ARESNAV_LLM_MODEL: str = Field(
        default="",
        description="Model name, required when provider is not none",
    )
    ANTHROPIC_API_KEY: str = Field(
        default="",
        description="API key for Anthropic provider",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for OpenAI provider",
    )
    ARESNAV_AGENT_NODE_TIMEOUT_S: float = Field(
        default=30.0,
        description="Per-agent-node timeout in seconds",
    )

    # --- Optional tracing ---
    LANGFUSE_PUBLIC_KEY: str = Field(default="", description="Optional Langfuse public key")
    LANGFUSE_SECRET_KEY: str = Field(default="", description="Optional Langfuse secret key")
    LANGFUSE_HOST: str = Field(default="", description="Optional Langfuse host URL")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        return [origin.strip() for origin in self.ARESNAV_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def resolved_data_dir(self) -> Path:
        """Resolve ARESNAV_DATA_DIR against REPO_ROOT if relative."""
        if self.ARESNAV_DATA_DIR.is_absolute():
            return self.ARESNAV_DATA_DIR
        return (REPO_ROOT / self.ARESNAV_DATA_DIR).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
