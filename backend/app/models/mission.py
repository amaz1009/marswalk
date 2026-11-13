"""Mission state and reporting models implementing docs/API_CONTRACTS.md §3.7 and §4.13."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.agents import AgentAnalysisResponse
from app.models.datasets import DatasetRecord
from app.models.enums import DataClass
from app.models.eva import EnvelopeResponse, EvaConfig, RoutePlanResponse, Stop
from app.models.evidence import AssumptionRecord
from app.models.geometry import GeoPoint


class MissionState(BaseModel):
    """Client-managed mission planning state."""

    mission_id: str = Field(..., description="Unique mission identifier starting with msn_")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    name: str = Field(..., description="Mission display name")
    region_id: str = Field(..., description="Target exploration region identifier")
    objective_text: str = Field(..., description="Science objective statement")
    base: GeoPoint | None = Field(default=None, description="Habitat or landing base coordinate")
    destination: GeoPoint | None = Field(default=None, description="Primary destination coordinate")
    stops: list[Stop] = Field(..., description="Ordered scientific waypoints")
    eva_config: EvaConfig = Field(..., description="Active EVA configuration")
    plan: RoutePlanResponse | None = Field(default=None, description="Latest calculated route plan")
    selected_route_id: str | None = Field(
        default=None, description="Currently selected route profile ID"
    )
    envelope: EnvelopeResponse | None = Field(
        default=None, description="Computed walk-back envelope"
    )
    agent_analysis: AgentAnalysisResponse | None = Field(
        default=None, description="Latest agent assessment"
    )
    notes: str | None = Field(default=None, description="Operator mission notes")

    @field_validator("mission_id")
    @classmethod
    def validate_mission_id_prefix(cls, v: str) -> str:
        if not v.startswith("msn_"):
            raise ValueError(f"mission_id must start with 'msn_' (got '{v}')")
        return v


class ReportSection(BaseModel):
    """Structured markdown chapter within a mission report."""

    section_id: str = Field(..., description="Unique section key")
    title: str = Field(..., description="Chapter title")
    body_markdown: str = Field(..., description="Markdown section content")
    data_class: DataClass = Field(..., description="Scientific classification of chapter content")


class MissionReportRequest(BaseModel):
    """Request payload to synthesize a mission briefing report."""

    mission_state: MissionState = Field(..., description="Current mission state to compile")


class MissionReport(BaseModel):
    """Integrated mission report document."""

    report_id: str = Field(..., description="Unique report identifier with rpt_ prefix")
    generated_at: datetime = Field(..., description="Report synthesis timestamp in UTC")
    mission_id: str = Field(..., description="Originating mission identifier")
    disclaimer: str = Field(..., description="Prototype safety disclaimer")
    sections: list[ReportSection] = Field(..., description="Ordered report chapters")
    datasets: list[DatasetRecord] = Field(..., description="All contributing datasets")
    assumptions: list[AssumptionRecord] = Field(..., description="Applied assumptions")
    limitations: list[str] = Field(..., description="Mission limitations")
    unresolved_issues: list[str] = Field(..., description="Open issues and safety warnings")
    markdown: str = Field(..., description="Full concatenated markdown document")
    engine_version: str = Field(..., description="Generating engine version")

    @field_validator("report_id")
    @classmethod
    def validate_report_id_prefix(cls, v: str) -> str:
        if not v.startswith("rpt_"):
            raise ValueError(f"report_id must start with 'rpt_' (got '{v}')")
        return v
