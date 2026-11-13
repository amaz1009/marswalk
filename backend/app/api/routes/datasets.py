"""Dataset endpoints stub implementing docs/API_CONTRACTS.md §4.4-§4.5 (P0, WP-08)."""

from fastapi import APIRouter, Query

from app.core.errors import AppException
from app.models import DatasetRecord

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get(
    "",
    response_model=list[DatasetRecord],
    summary="List catalog datasets",
    description="Returns metadata records for datasets available in a region.",
)
async def list_datasets(
    region_id: str | None = Query(default=None, description="Filter datasets by region ID"),
) -> list[DatasetRecord]:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetRecord,
    summary="Get dataset record",
    description="Returns complete metadata and provenance for a single dataset product.",
)
async def get_dataset(dataset_id: str) -> DatasetRecord:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
