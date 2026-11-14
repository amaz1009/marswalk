"""Mission report endpoint implementing docs/API_CONTRACTS.md §4.13 (P0, WP-13)."""

from fastapi import APIRouter

from app.models import MissionReport, MissionReportRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/mission", tags=["Mission"])


@router.post(
    "/report",
    response_model=MissionReport,
    summary="Generate mission report",
    description="Synthesizes structured mission documentation, disclaimers, and Markdown report.",
)
def generate_mission_report(request: MissionReportRequest) -> MissionReport:
    """Generate integrated mission briefing report from client mission state."""
    service = ReportService()
    return service.generate_report(request)
