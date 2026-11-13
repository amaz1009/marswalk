"""Evidence and assumption models implementing docs/API_CONTRACTS.md §3.2."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import DataClass


class EvidenceRef(BaseModel):
    """Reference linking an assessment or value to its data or model origin."""

    source_type: Literal["dataset", "engine", "assumption", "reference"] = Field(
        ...,
        description="Type of source backing this evidence",
    )
    source_id: str = Field(
        ...,
        description="Dataset identifier, engine module name, or assumption/reference key",
    )
    detail: str | None = Field(
        default=None,
        description="Field, product, or methodology detail",
    )


class AssumptionRecord(BaseModel):
    """Explicitly documented operational assumption or reference parameter."""

    key: str = Field(
        ...,
        description="Parameter key matching an EvaConfig field or documented parameter",
    )
    value: float | str | bool = Field(
        ...,
        description="Parameter value",
    )
    units: str | None = Field(
        default=None,
        description="Units of measurement if applicable",
    )
    data_class: DataClass = Field(
        ...,
        description="Classification: ASSUMPTION or REFERENCE",
    )
    basis: str = Field(
        ...,
        description="Concise rationale or origin statement",
    )
    citation: str | None = Field(
        default=None,
        description="Reference key from SCIENCE_AND_SAFETY_SPEC.md §15",
    )
