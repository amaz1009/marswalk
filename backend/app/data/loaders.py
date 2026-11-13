"""Data loaders and region/catalog manifest parsers.

Implements loaders for docs/API_CONTRACTS.md section 8:
- regions/<region_id>.json
- manifests/data_sources.json
- manifests/dataset_catalog.json
- manifests/source_ledger.json
- manifests/processing_manifest.json
"""

import json
from pathlib import Path
from typing import Any

from app.models.datasets import DatasetRecord


def get_default_data_dir() -> Path:
    """Return default data directory path relative to project root."""
    return Path(__file__).resolve().parents[2] / "data"


def load_data_sources(manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """Load data sources list from manifests/data_sources.json."""
    path = manifest_path or (get_default_data_dir() / "manifests" / "data_sources.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_source_ledger(ledger_path: Path | None = None) -> list[dict[str, Any]]:
    """Load source ledger records from manifests/source_ledger.json."""
    path = ledger_path or (get_default_data_dir() / "manifests" / "source_ledger.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_processing_manifest(manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """Load processing manifest records from manifests/processing_manifest.json."""
    path = manifest_path or (get_default_data_dir() / "manifests" / "processing_manifest.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_catalog(catalog_path: Path | None = None) -> list[DatasetRecord]:
    """Load dataset catalog and validate every record against DatasetRecord schema."""
    path = catalog_path or (get_default_data_dir() / "manifests" / "dataset_catalog.json")
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    datasets = payload.get("datasets", [])
    return [DatasetRecord.model_validate(ds) for ds in datasets]


def get_dataset_record(dataset_id: str, catalog_path: Path | None = None) -> DatasetRecord | None:
    """Retrieve a single DatasetRecord by dataset_id."""
    catalog = load_catalog(catalog_path)
    return next((ds for ds in catalog if ds.dataset_id == dataset_id), None)


def load_region_config(region_id: str, regions_dir: Path | None = None) -> dict[str, Any]:
    """Load region definition JSON for the given region_id."""
    dir_path = regions_dir or (get_default_data_dir() / "regions")
    region_file = dir_path / f"{region_id}.json"
    if not region_file.exists():
        raise FileNotFoundError(f"Region config file not found: {region_file}")
    data = json.loads(region_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid region config in {region_file}: expected JSON object")
    return data


def validate_region_config(region_data: dict[str, Any], catalog: list[DatasetRecord]) -> list[str]:
    """Validate region configuration against the dataset catalog and geometry rules."""
    errors: list[str] = []
    catalog_ids = {ds.dataset_id for ds in catalog}

    # 1. Primary DTM check
    analysis = region_data.get("analysis", {})
    primary_dtm = analysis.get("primary_dtm_dataset_id")
    if not primary_dtm:
        errors.append("Missing analysis.primary_dtm_dataset_id in region config")
    elif primary_dtm not in catalog_ids:
        errors.append(
            f"primary_dtm_dataset_id '{primary_dtm}' is not present in the dataset catalog"
        )

    # 2. Layers check
    layers = region_data.get("layers", [])
    for idx, layer in enumerate(layers):
        layer_id = layer.get("layer_id", f"layer_{idx}")
        layer_dataset_ids = layer.get("dataset_ids", [])
        for ds_id in layer_dataset_ids:
            if ds_id not in catalog_ids:
                errors.append(f"Layer '{layer_id}' references dataset '{ds_id}' not in catalog")

    # 3. Bounds sanity
    bounds = region_data.get("bounds", {})
    lat_min = bounds.get("lat_min", bounds.get("min_lat"))
    lat_max = bounds.get("lat_max", bounds.get("max_lat"))
    lon_min = bounds.get("lon_min", bounds.get("min_lon"))
    lon_max = bounds.get("lon_max", bounds.get("max_lon"))

    if None in (lat_min, lat_max, lon_min, lon_max):
        errors.append("Region bounds must define lat_min, lat_max, lon_min, lon_max")
    else:
        if lat_min > lat_max:
            errors.append(f"Invalid latitude bounds: lat_min ({lat_min}) > lat_max ({lat_max})")
        if lon_min > lon_max:
            errors.append(f"Invalid longitude bounds: lon_min ({lon_min}) > lon_max ({lon_max})")

    return errors
