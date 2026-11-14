"""Region and dataset services.

Implements business logic for:
- GET /api/v1/regions
- GET /api/v1/regions/{region_id}
- GET /api/v1/datasets
- GET /api/v1/datasets/{dataset_id}
- Service health catalog counts
"""

import re
from pathlib import Path
from typing import Any

from app.core.errors import AppException
from app.data.loaders import get_default_data_dir, load_catalog
from app.models.datasets import DatasetRecord
from app.models.enums import DatasetStatus
from app.models.evidence import EvidenceRef
from app.models.regions import (
    AnalysisSettings,
    RegionDataStatus,
    RegionDetail,
    RegionSummary,
    ScienceTarget,
)

SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def validate_identifier(identifier: str, name: str = "identifier") -> None:
    """Validate that an ID does not contain path traversal or illegal characters."""
    if not identifier or not SAFE_ID_PATTERN.match(identifier):
        raise AppException(
            error_code="VALIDATION_ERROR",
            message=f"Invalid {name} '{identifier}': alphanumeric and underscore only",
            status_code=422,
            details={"field": name, "value": identifier},
        )


def get_region_raw(region_id: str, data_dir: Path | None = None) -> dict[str, Any]:
    """Load raw JSON configuration for a region."""
    validate_identifier(region_id, name="region_id")
    base_dir = data_dir or get_default_data_dir()
    region_file = base_dir / "regions" / f"{region_id}.json"

    if not region_file.exists() or not region_file.is_file():
        raise AppException(
            error_code="REGION_NOT_FOUND",
            message=f"Region '{region_id}' not found",
            status_code=404,
            details={"region_id": region_id},
        )

    import json

    try:
        data = json.loads(region_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppException(
            error_code="REGION_CONFIG_CORRUPT",
            message=f"Failed to parse region configuration for '{region_id}': {exc}",
            status_code=500,
            details={"region_id": region_id, "error": str(exc)},
        ) from exc

    return data


def list_regions(data_dir: Path | None = None) -> list[RegionSummary]:
    """List high-level summaries for all exploration regions."""
    base_dir = data_dir or get_default_data_dir()
    regions_dir = base_dir / "regions"
    if not regions_dir.exists():
        return []

    summaries: list[RegionSummary] = []
    for region_path in sorted(regions_dir.glob("*.json")):
        try:
            raw = get_region_raw(region_path.stem, data_dir=base_dir)
            summary = RegionSummary(
                region_id=raw["region_id"],
                name=raw["name"],
                description=raw["description"],
                science_objective=raw["science_objective"],
                bounds=raw["bounds"],
            )
            summaries.append(summary)
        except Exception:
            # Skip unparseable files in listing
            continue

    return summaries


def get_region_detail(region_id: str, data_dir: Path | None = None) -> RegionDetail:
    """Retrieve full configuration and metadata for a region."""
    base_dir = data_dir or get_default_data_dir()
    raw = get_region_raw(region_id, data_dir=base_dir)

    # Compute dataset availability status
    catalog_path = base_dir / "manifests" / "dataset_catalog.json"
    catalog = load_catalog(catalog_path)
    avail_count = sum(1 for ds in catalog if ds.status == DatasetStatus.AVAILABLE)
    unavail_count = sum(1 for ds in catalog if ds.status != DatasetStatus.AVAILABLE)

    # Extract configured layer IDs
    layers_data = raw.get("layers", [])
    layer_ids = [
        layer_item["layer_id"]
        for layer_item in layers_data
        if isinstance(layer_item, dict) and "layer_id" in layer_item
    ]

    # Normalize science targets and evidence
    science_targets: list[ScienceTarget] = []
    for st_raw in raw.get("science_targets", []):
        evidence_list: list[EvidenceRef] = []
        for ev in st_raw.get("evidence", []):
            if "source_type" in ev and "source_id" in ev:
                evidence_list.append(EvidenceRef(**ev))
            elif "dataset_id" in ev:
                evidence_list.append(
                    EvidenceRef(
                        source_type="dataset",
                        source_id=ev["dataset_id"],
                        detail=ev.get("citation"),
                    )
                )
        st_clean = {
            "target_id": st_raw["target_id"],
            "name": st_raw["name"],
            "point": st_raw["point"],
            "rationale": st_raw["rationale"],
            "data_class": st_raw["data_class"],
            "evidence": evidence_list,
            "citation": st_raw.get("citation"),
        }
        science_targets.append(ScienceTarget(**st_clean))

    detail = RegionDetail(
        region_id=raw["region_id"],
        name=raw["name"],
        description=raw["description"],
        science_objective=raw["science_objective"],
        bounds=raw["bounds"],
        analysis=AnalysisSettings(**raw["analysis"]),
        default_base=raw.get("default_base"),
        default_base_basis=raw.get("default_base_basis"),
        science_targets=science_targets,
        layer_ids=layer_ids,
        data_status=RegionDataStatus(
            datasets_available=avail_count,
            datasets_unavailable=unavail_count,
        ),
    )
    return detail


def list_datasets(
    region_id: str | None = None, data_dir: Path | None = None
) -> list[DatasetRecord]:
    """List catalog datasets, optionally filtered by region."""
    base_dir = data_dir or get_default_data_dir()
    if region_id is not None:
        # Validates that the region exists; raises 404 if not found
        get_region_raw(region_id, data_dir=base_dir)

    catalog_path = base_dir / "manifests" / "dataset_catalog.json"
    catalog = load_catalog(catalog_path)
    return catalog


def get_dataset(dataset_id: str, data_dir: Path | None = None) -> DatasetRecord:
    """Retrieve metadata record for a single dataset product."""
    validate_identifier(dataset_id, name="dataset_id")
    base_dir = data_dir or get_default_data_dir()
    catalog_path = base_dir / "manifests" / "dataset_catalog.json"
    catalog = load_catalog(catalog_path)

    for ds in catalog:
        if ds.dataset_id == dataset_id:
            return ds

    raise AppException(
        error_code="DATASET_NOT_FOUND",
        message=f"Dataset '{dataset_id}' not found in catalog",
        status_code=404,
        details={"dataset_id": dataset_id},
    )


def get_data_counts(data_dir: Path | None = None) -> tuple[int, int, int]:
    """Return counts of loaded regions, available datasets, and unavailable datasets."""
    base_dir = data_dir or get_default_data_dir()
    regions = list_regions(data_dir=base_dir)
    catalog_path = base_dir / "manifests" / "dataset_catalog.json"
    catalog = load_catalog(catalog_path)

    avail_count = sum(1 for ds in catalog if ds.status == DatasetStatus.AVAILABLE)
    unavail_count = sum(1 for ds in catalog if ds.status != DatasetStatus.AVAILABLE)
    return len(regions), avail_count, unavail_count
