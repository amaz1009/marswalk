"""Mission report endpoints stub implementing docs/API_CONTRACTS.md §4.13 (P0, WP-13)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import MissionReport, MissionReportRequest

router = APIRouter(prefix="/mission", tags=["Mission"])


@router.post(
    "/report",
    response_model=MissionReport,
    summary="Generate mission report",
    description="Synthesizes structured mission documentation, disclaimers, and Markdown report.",
)
async def generate_mission_report(request: MissionReportRequest) -> MissionReport:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
