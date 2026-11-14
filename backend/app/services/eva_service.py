"""EVA service implementing operational defaults retrieval.

Implements AresNav API_CONTRACTS.md §4.11 GET /api/v1/eva/defaults.
"""

from app.engines.eva.defaults import get_default_eva_response
from app.models.eva import EvaDefaultsResponse


class EvaService:
    """Service providing EVA operational configurations and defaults."""

    def get_defaults(self) -> EvaDefaultsResponse:
        """Return default EVA configuration and supporting assumption records."""
        return get_default_eva_response()


_eva_service = EvaService()


def get_eva_service() -> EvaService:
    """Dependency provider returning singleton EvaService."""
    return _eva_service
