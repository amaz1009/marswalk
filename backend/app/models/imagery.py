"""Surface imagery models implementing docs/API_CONTRACTS.md §4.15-§4.16."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import DataClass
from app.models.geometry import GeoPoint


class SurfaceImage(BaseModel):
    """Rover ground-level surface image metadata."""

    image_id: str = Field(..., description="Unique surface image identifier")
    dataset_id: str = Field(..., description="Originating catalog dataset product ID")
    mission: str = Field(..., description="Rover mission name (e.g. MSL)")
    camera: str = Field(..., description="Camera instrument name")
    product_id: str = Field(..., description="Archive product identifier")
    sol: int | None = Field(default=None, description="Mission sol of acquisition", ge=0)
    acquired_at: datetime | None = Field(default=None, description="Acquisition timestamp in UTC")
    point: GeoPoint = Field(..., description="Rover location when image was taken")
    position_basis: str = Field(..., description="Method used to localize rover position")
    distance_m: float = Field(..., description="Distance from query coordinate in metres", ge=0.0)
    image_url: str = Field(..., description="Relative API URL to retrieve image file")
    caption: str = Field(..., description="Descriptive image caption")
    source_url: str = Field(..., description="Archive source URL")
    data_class: DataClass = Field(..., description="Scientific classification")
