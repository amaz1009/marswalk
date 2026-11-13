"""Agent system models implementing docs/API_CONTRACTS.md §4.18."""

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from app.models.enums import AgentRunStatus, ConfidenceLevel, DataClass, LlmMode
from app.models.evidence import EvidenceRef

if TYPE_CHECKING:
    from app.models.mission import MissionState


class Finding(BaseModel):
    """Specific factual finding produced by an AI or deterministic agent."""

    statement: str = Field(..., description="Factual observation or analytical conclusion")
    data_class: DataClass = Field(..., description="Scientific classification")
    evidence: list[EvidenceRef] = Field(
        ...,
        min_length=1,
        description="Supporting evidence references (mandatory for all findings)",
    )
    confidence: ConfidenceLevel = Field(..., description="Confidence assessment")


class AgentResult(BaseModel):
    """Outcome and analytical output from an individual specialized agent."""

    agent: Literal[
        "coordinator",
        "terrain",
        "geology",
        "thermal",
        "resource",
        "safety",
        "traverse",
        "mission",
        "synthesis",
    ] = Field(..., description="Agent specialist role")
    status: AgentRunStatus = Field(..., description="Execution status")
    mode: Literal["deterministic", "llm"] = Field(..., description="Execution engine mode")
    summary: str = Field(..., description="Executive summary of agent findings")
    findings: list[Finding] = Field(default_factory=list, description="Structured agent findings")
    warnings: list[str] = Field(
        default_factory=list, description="Operational warnings or safety concerns"
    )
    duration_ms: int = Field(..., description="Execution time in milliseconds", ge=0)


class AgentSynthesis(BaseModel):
    """Integrated multi-agent consensus synthesis and mission guidance."""

    summary: str = Field(..., description="Executive synthesis across all agent domains")
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable mission recommendations"
    )
    unresolved_issues: list[str] = Field(
        default_factory=list, description="Identified conflicts or open questions"
    )
    data_class: DataClass = Field(
        default=DataClass.AI_INTERPRETATION,
        description="Scientific classification of synthesis",
    )


class AgentAnalysisRequest(BaseModel):
    """Request payload for multi-agent mission evaluation."""

    mission_state: "MissionState" = Field(..., description="Mission state to analyze")
    question: str | None = Field(default=None, description="Optional operator query")


class AgentAnalysisResponse(BaseModel):
    """Complete multi-agent analysis response."""

    run_id: str = Field(..., description="Unique run identifier with run_ prefix")
    llm_mode: LlmMode = Field(..., description="LLM enablement mode")
    agents: list[AgentResult] = Field(..., description="Outputs from individual agents")
    synthesis: AgentSynthesis = Field(..., description="Integrated consensus synthesis")
    computed_at: datetime = Field(..., description="Completion timestamp in UTC")
