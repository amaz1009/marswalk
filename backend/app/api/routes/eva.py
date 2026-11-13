"""EVA endpoints stub implementing docs/API_CONTRACTS.md §4.11 and §4.14 (P0/P1)."""

from fastapi import APIRouter

from app.core.errors import AppException
from app.models import EnvelopeRequest, EnvelopeResponse, EvaDefaultsResponse

router = APIRouter(prefix="/eva", tags=["EVA"])


@router.get(
    "/defaults",
    response_model=EvaDefaultsResponse,
    summary="Get default EVA configuration",
    description="Returns baseline EVA physiological parameters and explicit reference assumptions.",
)
async def get_eva_defaults() -> EvaDefaultsResponse:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )


@router.post(
    "/envelope",
    response_model=EnvelopeResponse,
    summary="Compute walk-back envelope",
    description="Computes reachable safety perimeter from a habitat base given consumable limits.",
)
async def compute_envelope(request: EnvelopeRequest) -> EnvelopeResponse:
    raise AppException(
        error_code="NOT_IMPLEMENTED",
        message="Endpoint belongs to an unmerged work package",
        status_code=501,
    )
