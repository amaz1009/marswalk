"""Agent evaluation endpoints stub implementing docs/API_CONTRACTS.md §4.18 (P1, WP-17)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import AgentAnalysisRequest, AgentAnalysisResponse

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post(
    "/analyze",
    response_model=AgentAnalysisResponse,
    summary="Multi-agent plan evaluation",
    description="Invokes specialist agents to review mission traverse and synthesize guidance.",
)
async def analyze_mission(request: AgentAnalysisRequest) -> AgentAnalysisResponse:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
