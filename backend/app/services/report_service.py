"""Mission report service implementing docs/API_CONTRACTS.md §4.13."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.core.errors import AppException
from app.engines.report.builder import build_mission_report
from app.models.mission import MissionReport, MissionReportRequest
from app.services.region_service import get_region_raw, list_datasets


class ReportService:
    """Service orchestrating mission report synthesis and validation."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir

    def generate_report(
        self,
        request: MissionReportRequest,
        *,
        now: datetime | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> MissionReport:
        """Validate mission state consistency and synthesize mission report."""
        ms = request.mission_state

        # Validate selected_route_id exists in plan if specified
        if ms.selected_route_id is not None:
            if ms.plan is None:
                raise AppException(
                    error_code="INVALID_MISSION_STATE",
                    message="selected_route_id is specified but plan is None",
                    status_code=422,
                    details={"selected_route_id": ms.selected_route_id},
                )
            valid_ids = [r.route_id for r in ms.plan.routes]
            if ms.selected_route_id not in valid_ids:
                raise AppException(
                    error_code="INVALID_MISSION_STATE",
                    message=f"selected_route_id '{ms.selected_route_id}' not found in plan.routes",
                    status_code=422,
                    details={
                        "selected_route_id": ms.selected_route_id,
                        "valid_route_ids": valid_ids,
                    },
                )

        # Retrieve region metadata (raises REGION_NOT_FOUND 404 if unknown)
        region = get_region_raw(ms.region_id, data_dir=self.data_dir)

        # Retrieve catalog datasets for this region
        catalog = list_datasets(ms.region_id, data_dir=self.data_dir)

        # Build report deterministically
        return build_mission_report(
            mission_state=ms,
            region=region,
            catalog=catalog,
            now=now,
            id_factory=id_factory,
        )
