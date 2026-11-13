"""Data pipeline processing stages.

Implements requirements from docs/SYSTEM_ARCHITECTURE.md section 7.2:
- Nodata normalisation (source nodata converted to NaN, never 0)
- Array clipping to region geographic bounds
- Cloud Optimized GeoTIFF (COG) generation
- Coverage statistics computation
- Processing step manifest recording
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.datasets import ProcessingStep

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def normalize_nodata(
    data: Any,
    source_nodata: float | int | None,
) -> Any:
    """Normalize raster nodata to IEEE 754 NaN.

    Per SCIENCE_AND_SAFETY_SPEC.md section 3:
    - Nodata in any source is converted to NaN on ingestion.
    - It is NEVER converted to 0.
    """
    if np is None:
        raise RuntimeError("numpy is required for raster processing")

    # Ensure array is floating point to hold NaNs
    if np.issubdtype(data.dtype, np.integer):
        out = data.astype(np.float32)
    elif np.issubdtype(data.dtype, np.floating):
        out = data.copy()
    else:
        out = data.astype(np.float32)

    if source_nodata is not None:
        if np.isnan(source_nodata):
            pass  # Already NaNs
        else:
            mask = np.isclose(data, source_nodata, equal_nan=True) | (data == source_nodata)
            out[mask] = np.nan

    return out


def compute_coverage_statistics(data: Any) -> dict[str, Any]:
    """Compute cell coverage statistics ignoring NaNs."""
    if np is None:
        raise RuntimeError("numpy is required for coverage statistics")

    total_cells = int(data.size)
    if total_cells == 0:
        return {
            "total_cells": 0,
            "valid_cells": 0,
            "nodata_cells": 0,
            "valid_fraction": 0.0,
        }

    nan_mask = np.isnan(data)
    nodata_cells = int(np.count_nonzero(nan_mask))
    valid_cells = total_cells - nodata_cells
    valid_fraction = float(valid_cells / total_cells)

    return {
        "total_cells": total_cells,
        "valid_cells": valid_cells,
        "nodata_cells": nodata_cells,
        "valid_fraction": valid_fraction,
    }


def create_processing_step(
    step_name: str,
    tool_name: str,
    parameters: dict[str, Any],
) -> ProcessingStep:
    """Build a standard ProcessingStep provenance record."""
    return ProcessingStep(
        step=step_name,
        tool=tool_name,
        parameters=parameters,
        completed_at=datetime.now(timezone.utc),
    )


def append_to_processing_manifest(
    manifest_path: Path,
    output_path: str,
    dataset_id: str,
    inputs: list[str],
    steps: list[ProcessingStep],
    status: str = "COMPLETED",
    status_reason: str | None = None,
) -> None:
    """Record execution history for a processed raster product in processing_manifest.json."""
    entries: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = [e for e in raw if e.get("dataset_id") != dataset_id]
        except Exception:
            entries = []

    step_dicts = [
        {
            "step": s.step,
            "tool": s.tool,
            "parameters": s.parameters,
            "completed_at": s.completed_at.isoformat(),
        }
        for s in steps
    ]

    record = {
        "output_path": output_path,
        "dataset_id": dataset_id,
        "inputs": inputs,
        "steps": step_dicts,
        "status": status,
        "status_reason": status_reason,
    }
    entries.append(record)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def write_cog_geotiff(
    output_path: Path,
    data: Any,
    transform: Any,
    crs: Any,
    nodata: float | None = None,
) -> None:
    """Write array to Cloud-Optimized GeoTIFF with tiling and compression.

    Uses rasterio if available.
    """
    try:
        import rasterio
    except ImportError as err:
        raise RuntimeError("rasterio is required to write GeoTIFF rasters") from err

    output_path.parent.mkdir(parents=True, exist_ok=True)

    height, width = data.shape
    out_nodata = np.nan if nodata is None else nodata

    blockx = 256 if width >= 256 else (max(16, (width // 16) * 16) if width >= 16 else 16)
    blocky = 256 if height >= 256 else (max(16, (height // 16) * 16) if height >= 16 else 16)

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": data.dtype,
        "crs": crs,
        "transform": transform,
        "nodata": out_nodata,
        "tiled": True,
        "blockxsize": blockx,
        "blockysize": blocky,
        "compress": "deflate",
    }

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data, 1)
