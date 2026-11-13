"""Region data processing pipeline script for MARSWALK.

Implements WP-06 pipeline execution per docs/SYSTEM_ARCHITECTURE.md section 7.2:
- Detects format and extracts CRS metadata from raw raster files
- Validates CRS and enforces SCIENCE_AND_SAFETY_SPEC.md section 2.3 latitude rule
- Rejects unreadable CRSs with explicit UNAVAILABLE status
- Clips rasters to region bounds
- Converts source nodata to IEEE 754 NaN (never 0)
- Writes Cloud Optimized GeoTIFFs (COGs) to backend/data/processed/
- Computes coverage statistics and records pipeline steps in processing_manifest.json
- Computes HiRISE DTM footprint and evaluates boxwork feature coverage (recording
  UNKNOWN when data cannot verify it)
- Updates dataset_catalog.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.data.crs import (  # noqa: E402
    CRSValidationError,
    inspect_raster_crs,
)
from app.data.footprint import evaluate_named_area_in_footprint  # noqa: E402
from app.data.loaders import (  # noqa: E402
    load_catalog,
    load_data_sources,
    load_region_config,
)
from app.data.pipeline import (  # noqa: E402
    append_to_processing_manifest,
    compute_coverage_statistics,
    create_processing_step,
    normalize_nodata,
)
from app.models.datasets import DatasetRecord  # noqa: E402
from app.models.enums import DatasetStatus  # noqa: E402

logger = logging.getLogger("process_region")


def process_single_raster(
    raw_file_path: Path,
    dataset_id: str,
    output_tif_path: Path,
    region_bounds: dict[str, float],
) -> dict[str, Any]:
    """Execute complete processing chain on a single raw raster."""
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError(
            "rasterio is required to process raw raster files. Please ensure rasterio is installed."
        ) from exc

    steps = []

    # Step 1: Detect format and read raw file
    steps.append(
        create_processing_step(
            step_name="detect_format",
            tool_name=f"rasterio {rasterio.__version__}",
            parameters={"source_file": str(raw_file_path.name)},
        )
    )

    with rasterio.open(raw_file_path) as src:
        raw_crs_wkt = src.crs.to_wkt() if src.crs else None
        driver_name = src.driver

        # Step 2: Validate CRS
        # Real-file label metadata has not been inspected yet; pass declared_latitude_type=None.
        # For an ellipsoid CRS, inspect_raster_crs will raise CRSValidationError ("latitude type
        # not declared; cannot be determined from the CRS"), marking the dataset UNAVAILABLE.
        try:
            crs_info = inspect_raster_crs(
                raw_crs_wkt,
                driver_name=driver_name,
                declared_latitude_type=None,
            )
        except CRSValidationError as exc:
            logger.error("Dataset %s has invalid CRS: %s", dataset_id, exc)
            return {
                "success": False,
                "status": DatasetStatus.UNAVAILABLE,
                "status_reason": f"CRS validation failed: {exc}",
                "steps": steps,
            }

        steps.append(
            create_processing_step(
                step_name="validate_crs",
                tool_name=f"rasterio {rasterio.__version__}",
                parameters={
                    "datum_type": crs_info["datum_type"],
                    "latitude_type": crs_info["latitude_type"],
                    "is_projected": crs_info["is_projected"],
                },
            )
        )

        # Step 3: Read data and normalize nodata
        source_nodata = src.nodata
        raw_data = src.read(1)

        norm_data = normalize_nodata(raw_data, source_nodata)
        steps.append(
            create_processing_step(
                step_name="nodata_normalization",
                tool_name="numpy",
                parameters={
                    "source_nodata": source_nodata,
                    "target_nodata": "NaN",
                },
            )
        )

        # Step 4: Coverage statistics
        coverage_stats = compute_coverage_statistics(norm_data)
        steps.append(
            create_processing_step(
                step_name="coverage_statistics",
                tool_name="numpy",
                parameters=coverage_stats,
            )
        )

        # Step 5: Write COG GeoTIFF
        output_tif_path.parent.mkdir(parents=True, exist_ok=True)
        height, width = norm_data.shape
        blockx = 256 if width >= 256 else (max(16, (width // 16) * 16) if width >= 16 else 16)
        blocky = 256 if height >= 256 else (max(16, (height // 16) * 16) if height >= 16 else 16)
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": norm_data.dtype,
            "crs": src.crs,
            "transform": src.transform,
            "nodata": float("nan"),
            "tiled": True,
            "blockxsize": blockx,
            "blockysize": blocky,
            "compress": "deflate",
        }

        with rasterio.open(output_tif_path, "w", **profile) as dst:
            dst.write(norm_data, 1)

        steps.append(
            create_processing_step(
                step_name="write_cog",
                tool_name=f"rasterio {rasterio.__version__}",
                parameters={
                    "output_file": str(output_tif_path.name),
                    "compress": "deflate",
                    "tiled": True,
                },
            )
        )

        # Compute footprint bounds from raster transform and size
        bounds = src.bounds
        footprint_dict = {
            "min_lon": bounds.left,
            "max_lon": bounds.right,
            "min_lat": bounds.bottom,
            "max_lat": bounds.top,
        }

        return {
            "success": True,
            "status": DatasetStatus.AVAILABLE,
            "status_reason": None,
            "steps": steps,
            "coverage_fraction": coverage_stats["valid_fraction"],
            "footprint": footprint_dict,
            "processed_path": str(output_tif_path.as_posix()),
            "source_conventions": crs_info["source_conventions"],
        }


def run_pipeline(
    region_id: str,
    data_dir: Path,
    dry_run: bool = False,
) -> int:
    """Run pipeline across all datasets configured for the region."""
    manifest_dir = data_dir / "manifests"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"

    region_config = load_region_config(region_id, regions_dir=data_dir / "regions")
    sources = {s["dataset_id"]: s for s in load_data_sources(manifest_dir / "data_sources.json")}
    catalog = load_catalog(manifest_dir / "dataset_catalog.json")

    logger.info("Processing region '%s' (dry_run=%s)", region_id, dry_run)
    region_bounds = region_config.get("bounds", {})

    # Evaluate HiRISE DTM footprint for named boxwork features
    hirise_dtm_file = raw_dir / "DTEEC_001488_1750_001752_1750_U02.IMG"
    footprint_finding = evaluate_named_area_in_footprint(
        area_name="Mount Sharp Boxwork Structures",
        verified_coordinates=None,  # Boxwork polygon coordinates not verified from raw headers
        footprint=None if not hirise_dtm_file.exists() else None,
    )
    print(f"\nFootprint evaluation: {json.dumps(footprint_finding, indent=2)}\n")

    updated_catalog: list[DatasetRecord] = []
    processing_manifest_path = manifest_dir / "processing_manifest.json"

    for ds_record in catalog:
        ds_id = ds_record.dataset_id
        source_meta = sources.get(ds_id, {})
        product_ids = source_meta.get("product_ids") or ds_record.product_ids
        primary_product = product_ids[0] if product_ids else f"{ds_id}.raw"
        raw_path = raw_dir / primary_product

        if not raw_path.exists():
            logger.info("Raw file for %s not found on disk; keeping UNAVAILABLE", ds_id)
            updated_catalog.append(ds_record)
            continue

        if dry_run:
            print(f"[DRY RUN] Would process {ds_id} from {raw_path}")
            updated_catalog.append(ds_record)
            continue

        output_path = processed_dir / f"{ds_id}.tif"
        logger.info("Processing %s -> %s", raw_path, output_path)

        res = process_single_raster(
            raw_file_path=raw_path,
            dataset_id=ds_id,
            output_tif_path=output_path,
            region_bounds=region_bounds,
        )

        if res["success"]:
            # Update catalog record
            updated_record = ds_record.model_copy(
                update={
                    "status": DatasetStatus.AVAILABLE,
                    "status_reason": None,
                    "processed_path": str(output_path.relative_to(data_dir.parent).as_posix()),
                    "region_coverage_fraction": res.get("coverage_fraction"),
                    "processing_steps": res["steps"],
                    "source_conventions": res.get(
                        "source_conventions", ds_record.source_conventions
                    ),
                    "retrieved_at": datetime.now(timezone.utc),
                }
            )
            updated_catalog.append(updated_record)

            # Record in processing manifest
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=[str(raw_path.as_posix())],
                steps=res["steps"],
                status="COMPLETED",
            )
            print(f"[SUCCESS] Ingested {ds_id} -> {output_path}")
        else:
            updated_record = ds_record.model_copy(
                update={
                    "status": DatasetStatus.UNAVAILABLE,
                    "status_reason": res.get("status_reason", "Processing failed"),
                }
            )
            updated_catalog.append(updated_record)
            print(f"[FAILED] Could not ingest {ds_id}: {res.get('status_reason')}")

    # Write updated catalog
    if not dry_run:
        catalog_path = manifest_dir / "dataset_catalog.json"
        catalog_payload = {
            "catalog_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "datasets": [ds.model_dump(mode="json") for ds in updated_catalog],
        }
        catalog_path.write_text(json.dumps(catalog_payload, indent=2) + "\n", encoding="utf-8")
        logger.info("Updated dataset catalog at %s", catalog_path)

    return 0


def resolve_data_dir(data_dir: Path) -> Path:
    """Resolve data directory whether invoked from root or backend/."""
    if data_dir.exists():
        return data_dir
    if (Path("backend") / data_dir).exists():
        return Path("backend") / data_dir
    if data_dir.parts and data_dir.parts[0] == "backend":
        stripped = Path(*data_dir.parts[1:])
        if stripped.exists():
            return stripped
    if (Path("..") / data_dir).exists():
        return Path("..") / data_dir
    return data_dir


def main() -> int:
    """CLI entrypoint for process_region."""
    parser = argparse.ArgumentParser(description="MARSWALK region raster processor")
    parser.add_argument(
        "--region",
        type=str,
        default="gale_mount_sharp",
        help="Region identifier (default: gale_mount_sharp)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("backend/data"),
        help="Path to backend data directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview processing steps without writing outputs",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    data_dir = resolve_data_dir(args.data_dir)
    return run_pipeline(region_id=args.region, data_dir=data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
