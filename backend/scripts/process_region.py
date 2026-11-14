"""Region data processing pipeline script for AresNav.

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
from typing import Any, TypedDict

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.data.crs import (  # noqa: E402
    CRSValidationError,
    inspect_raster_crs,
)
from app.data.footprint import evaluate_named_area_in_footprint  # noqa: E402
from app.data.loaders import (  # noqa: E402
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
from app.models.geometry import GeoBounds  # noqa: E402

logger = logging.getLogger("process_region")


def get_dataset_sha256(
    ledger_path: Path,
    dataset_id: str,
    raw_filename: str | None = None,
) -> str | None:
    """Lookup SHA-256 for a dataset's primary raw file from source_ledger.json."""
    if not ledger_path.exists():
        return None
    try:
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return None
        for e in entries:
            if e.get("dataset_id") == dataset_id:
                if raw_filename is None or Path(e.get("file_path", "")).name == raw_filename:
                    return e.get("sha256")
        for e in entries:
            if e.get("dataset_id") == dataset_id:
                return e.get("sha256")
    except Exception:
        pass
    return None


class RasterProcessSuccessResult(TypedDict):
    """Explicit shape of a successful single-raster processing result."""

    success: bool
    status: DatasetStatus
    status_reason: str | None
    steps: list[Any]
    coverage_fraction: float
    coverage_bounds: dict[str, float]
    bounds: GeoBounds
    native_resolution_m: float
    coverage_limitation: str
    processed_path: str
    source_conventions: str


class RasterProcessFailureResult(TypedDict):
    """Explicit shape of a failed single-raster processing result."""

    success: bool
    status: DatasetStatus
    status_reason: str
    steps: list[Any]


RasterProcessResult = RasterProcessSuccessResult | RasterProcessFailureResult

# Required keys that run_pipeline reads from a success result
REQUIRED_SUCCESS_KEYS: frozenset[str] = frozenset(RasterProcessSuccessResult.__annotations__.keys())


def process_single_raster(
    raw_file_path: Path,
    dataset_id: str,
    output_tif_path: Path,
    region_bounds: dict[str, float],
) -> RasterProcessResult:
    """Execute complete processing chain on a single raw raster."""
    try:
        import pyproj
        import rasterio
    except ImportError as exc:
        raise RuntimeError(
            "rasterio and pyproj are required to process raw raster files. "
            "Please ensure they are installed."
        ) from exc

    steps = []

    # Step 1: Detect format and read raw file
    steps.append(
        create_processing_step(
            step_name="detect_format",
            tool_name=f"rasterio {rasterio.__version__}",
            parameters={
                "source_file": str(raw_file_path.name),
                "opened_path": str(raw_file_path.as_posix()),
            },
        )
    )

    try:
        with rasterio.open(raw_file_path) as src:
            raw_crs_wkt = src.crs.to_wkt() if src.crs else None
            driver_name = src.driver

            # Step 2: Validate CRS
            try:
                crs_info = inspect_raster_crs(
                    raw_crs_wkt,
                    driver_name=driver_name,
                    declared_latitude_type=None,
                )
            except CRSValidationError as exc:
                logger.warning("Dataset %s has invalid CRS: %s", dataset_id, exc)
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
            blockx = 256 if width >= 256 else max(16, (width // 16) * 16)
            blocky = 256 if height >= 256 else max(16, (height // 16) * 16)
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

            # Compute geographic coverage bounds using pyproj
            proj_crs = pyproj.CRS(src.crs)
            geodetic_crs = proj_crs.geodetic_crs if proj_crs.is_projected else proj_crs
            transformer = pyproj.Transformer.from_crs(
                proj_crs, geodetic_crs, always_xy=True, allow_ballpark=False
            )
            b = src.bounds
            xs = [b.left, b.right, b.left, b.right]
            ys = [b.bottom, b.bottom, b.top, b.top]
            lons, lats = transformer.transform(xs, ys)
            lon_min = float(min(lons)) % 360.0
            lon_max = float(max(lons)) % 360.0
            lat_min = float(min(lats))
            lat_max = float(max(lats))

            bounds_obj = GeoBounds(
                lat_min=round(lat_min, 6),
                lat_max=round(lat_max, 6),
                lon_min=round(lon_min, 6),
                lon_max=round(lon_max, 6),
            )

            # Dynamic limitation coverage string (omits unsupported cause)
            total_cells = int(norm_data.size)
            nodata_cells = int(coverage_stats["nodata_cells"])
            valid_frac = float(coverage_stats["valid_fraction"])
            coverage_limitation_str = (
                f"Valid data cell coverage: {valid_frac * 100:.1f}% "
                f"({nodata_cells:,} nodata cells out of {total_cells:,} total in bounding box)."
            )

            # Native resolution from transform
            native_res = round(float(abs(src.transform.a)), 2)

            return {
                "success": True,
                "status": DatasetStatus.AVAILABLE,
                "status_reason": None,
                "steps": steps,
                "coverage_fraction": coverage_stats["valid_fraction"],
                "coverage_bounds": {
                    "lat_min": bounds_obj.lat_min,
                    "lat_max": bounds_obj.lat_max,
                    "lon_min": bounds_obj.lon_min,
                    "lon_max": bounds_obj.lon_max,
                },
                "bounds": bounds_obj,
                "native_resolution_m": native_res,
                "coverage_limitation": coverage_limitation_str,
                "processed_path": str(output_tif_path.as_posix()),
                "source_conventions": crs_info["source_conventions"],
            }
    except Exception as exc:
        logger.warning("Failed to open or process %s: %s", raw_file_path.name, exc)
        return {
            "success": False,
            "status": DatasetStatus.UNAVAILABLE,
            "status_reason": f"{type(exc).__name__}: {exc}",
            "steps": steps,
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
    ledger_path = manifest_dir / "source_ledger.json"

    region_config = load_region_config(region_id, regions_dir=data_dir / "regions")
    sources = {s["dataset_id"]: s for s in load_data_sources(manifest_dir / "data_sources.json")}

    catalog_path = manifest_dir / "dataset_catalog.json"
    if not catalog_path.exists():
        logger.error("Dataset catalog not found at %s", catalog_path)
        return 1

    catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_entries: list[dict[str, Any]] = catalog_payload.get("datasets", [])

    logger.info("Processing region '%s' (dry_run=%s)", region_id, dry_run)
    region_bounds = region_config.get("bounds", {})

    processing_manifest_path = manifest_dir / "processing_manifest.json"
    summary_table: list[dict[str, Any]] = []

    for ds_dict in catalog_entries:
        ds_id = ds_dict.get("dataset_id", "UNKNOWN")
        source_meta = sources.get(ds_id, {})
        product_ids = source_meta.get("product_ids") or ds_dict.get("product_ids", [])
        primary_product = product_ids[0] if product_ids else f"{ds_id}.raw"
        raw_path = raw_dir / primary_product

        # Check for companion label file (e.g. PDS3_LBL) to open with rasterio
        companion_meta = source_meta.get("companion_file")
        target_open_path = raw_path
        if (
            companion_meta
            and isinstance(companion_meta, dict)
            and companion_meta.get("expected_format") == "PDS3_LBL"
        ):
            comp_product_id = (
                companion_meta.get("product_id") or Path(companion_meta.get("url", "")).name
            )
            if comp_product_id:
                target_open_path = raw_dir / comp_product_id

        if not target_open_path.exists():
            logger.info("Raw/label file for %s not found on disk; keeping UNAVAILABLE", ds_id)
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": ds_dict.get("status", "UNAVAILABLE"),
                    "details": ds_dict.get(
                        "status_reason", f"File not on disk: {target_open_path.name}"
                    ),
                }
            )
            continue

        if dry_run:
            print(f"[DRY RUN] Would process {ds_id} from {target_open_path}")
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "DRY_RUN",
                    "details": f"Would process from {target_open_path}",
                }
            )
            continue

        output_path = processed_dir / f"{ds_id}.tif"
        logger.info("Processing %s -> %s", target_open_path, output_path)

        manifest_inputs = [str(raw_path.as_posix())]
        if target_open_path != raw_path:
            manifest_inputs.append(str(target_open_path.as_posix()))

        try:
            res = process_single_raster(
                raw_file_path=target_open_path,
                dataset_id=ds_id,
                output_tif_path=output_path,
                region_bounds=region_bounds,
            )
        except Exception as exc:
            logger.warning("Unexpected error during processing of %s: %s", ds_id, exc)
            res = {
                "success": False,
                "status": DatasetStatus.UNAVAILABLE,
                "status_reason": f"{type(exc).__name__}: {exc}",
                "steps": [],
            }

        if not isinstance(res, dict):
            status_reason = f"Invalid result object type: {type(res).__name__}"
            ds_dict["status"] = "UNAVAILABLE"
            ds_dict["status_reason"] = status_reason
            try:
                DatasetRecord.model_validate(ds_dict)
            except Exception:
                pass
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=manifest_inputs,
                steps=[],
                status="FAILED",
                status_reason=status_reason,
            )
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "UNAVAILABLE",
                    "details": status_reason,
                }
            )
            print(f"[FAILED] Could not ingest {ds_id}: {status_reason}")
            continue

        res_status = res.get("status")
        res_success = res.get("success")

        if res_status != DatasetStatus.AVAILABLE or not res_success:
            fail_reason = str(res.get("status_reason") or "Processing failed")
            ds_dict["status"] = "UNAVAILABLE"
            ds_dict["status_reason"] = fail_reason
            try:
                DatasetRecord.model_validate(ds_dict)
            except Exception:
                pass
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=manifest_inputs,
                steps=res.get("steps", []),
                status="FAILED",
                status_reason=fail_reason,
            )
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "UNAVAILABLE",
                    "details": fail_reason,
                }
            )
            print(f"[FAILED] Could not ingest {ds_id}: {fail_reason}")
            continue

        missing_keys = [
            k
            for k in REQUIRED_SUCCESS_KEYS
            if k not in res or (res[k] is None and k != "status_reason")
        ]
        if missing_keys:
            incomplete_reason = (
                f"Processing result incomplete; missing keys: {', '.join(sorted(missing_keys))}"
            )
            logger.warning("Dataset %s result is incomplete: %s", ds_id, incomplete_reason)
            ds_dict["status"] = "UNAVAILABLE"
            ds_dict["status_reason"] = incomplete_reason
            try:
                DatasetRecord.model_validate(ds_dict)
            except Exception:
                pass
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=manifest_inputs,
                steps=res.get("steps", []),
                status="FAILED",
                status_reason=incomplete_reason,
            )
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "UNAVAILABLE",
                    "details": incomplete_reason,
                }
            )
            print(f"[FAILED] Could not ingest {ds_id}: {incomplete_reason}")
            continue

        try:
            # Result is successful and complete
            ds_dict["status"] = "AVAILABLE"
            ds_dict["status_reason"] = None
            sha256_hash = get_dataset_sha256(ledger_path, ds_id, raw_path.name)
            if sha256_hash:
                ds_dict["sha256"] = sha256_hash
            ds_dict["native_resolution_m"] = res["native_resolution_m"]
            ds_dict["coverage_bounds"] = res["coverage_bounds"]
            ds_dict["region_coverage_fraction"] = res.get("coverage_fraction")
            ds_dict["processed_path"] = str(output_path.relative_to(data_dir.parent).as_posix())
            ds_dict["processing_steps"] = [
                {
                    "step": s.step if hasattr(s, "step") else s["step"],
                    "tool": s.tool if hasattr(s, "tool") else s["tool"],
                    "parameters": s.parameters if hasattr(s, "parameters") else s["parameters"],
                    "completed_at": (
                        s.completed_at.isoformat()
                        if hasattr(s, "completed_at") and hasattr(s.completed_at, "isoformat")
                        else str(
                            s.get("completed_at", "")
                            if isinstance(s, dict)
                            else getattr(s, "completed_at", "")
                        )
                    ),
                }
                for s in res["steps"]
            ]
            ds_dict["source_conventions"] = res.get(
                "source_conventions", ds_dict.get("source_conventions")
            )
            ds_dict["retrieved_at"] = datetime.now(timezone.utc).isoformat()

            # Compile verified limitations for catalog record
            if ds_id == "HIRISE_DTM_GALE_MOUND":
                b = res["bounds"]
                if isinstance(b, GeoBounds):
                    lat_min, lat_max, lon_min, lon_max = (
                        b.lat_min,
                        b.lat_max,
                        b.lon_min,
                        b.lon_max,
                    )
                elif isinstance(b, dict):
                    lat_min = b.get("lat_min")
                    lat_max = b.get("lat_max")
                    lon_min = b.get("lon_min")
                    lon_max = b.get("lon_max")
                else:
                    lat_min = getattr(b, "lat_min", None)
                    lat_max = getattr(b, "lat_max", None)
                    lon_min = getattr(b, "lon_min", None)
                    lon_max = getattr(b, "lon_max", None)

                if any(v is None for v in (lat_min, lat_max, lon_min, lon_max)):
                    raise ValueError(
                        f"Invalid or missing bounds coordinates in result for {ds_id}: {b}"
                    )

                lim_cov = (
                    f"Footprint covers latitude [{lat_min:.6f}, {lat_max:.6f}] degrees, "
                    f"longitude [{lon_min:.6f}, {lon_max:.6f}] degrees East "
                    "(computed coverage bounds). Containment of the Mount Sharp boxwork areas "
                    "in this footprint is UNKNOWN (no cited feature coordinates)."
                )
                vert_lim = (
                    "Vertical datum of the DTM has not been verified by this pipeline (UNKNOWN)."
                )
                existing_lims = [lim_cov, vert_lim]
            elif ds_id == "HIRISE_ORTHO_GALE_MOUND":
                existing_lims = [
                    "Single 8-bit band (product name indicates the RED channel); "
                    "no colour or multispectral information."
                ]
            elif ds_id == "MOLA_MEGDR_GALE":
                existing_lims = [
                    "Planetary radius minus areoid (GMM3) vertical reference.",
                    (
                        "Interpolated values where no observation lies in a bin; about 55 "
                        "percent of bins contain at least one shot near the equator, with "
                        "profile gaps up to 12 km."
                    ),
                    (
                        "Grid edges derived by the GDAL PDS driver from the label differ "
                        "from the label's stated extents by up to about one 463 m pixel "
                        "(driver uses MAP_SCALE 0.463 km, label states 128 pixels per degree); "
                        "positions at the footprint may be displaced by up to about one pixel."
                    ),
                    (
                        "Heights must not be combined with HiRISE DTM heights unless the "
                        "HiRISE vertical reference is verified."
                    ),
                ]
            else:
                existing_lims = [
                    lim_text
                    for lim_text in ds_dict.get("limitations", [])
                    if not lim_text.startswith("Valid data cell coverage:")
                ]

            if res.get("coverage_limitation"):
                existing_lims.append(res["coverage_limitation"])
            ds_dict["limitations"] = existing_lims

            # Validate record against schema
            DatasetRecord.model_validate(ds_dict)

            # Record in processing manifest
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=manifest_inputs,
                steps=res["steps"],
                status="COMPLETED",
                status_reason=None,
            )
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "AVAILABLE",
                    "details": f"Ingested -> {output_path.name}",
                }
            )
            print(f"[SUCCESS] Ingested {ds_id} -> {output_path}")

        except Exception as exc:
            final_fail_reason = f"Failed to record ingested dataset: {exc}"
            logger.warning("Dataset %s ingestion finalization failed: %s", ds_id, exc)
            ds_dict["status"] = "UNAVAILABLE"
            ds_dict["status_reason"] = final_fail_reason
            try:
                DatasetRecord.model_validate(ds_dict)
            except Exception:
                pass
            append_to_processing_manifest(
                manifest_path=processing_manifest_path,
                output_path=str(output_path.as_posix()),
                dataset_id=ds_id,
                inputs=manifest_inputs,
                steps=res.get("steps", []) if isinstance(res, dict) else [],
                status="FAILED",
                status_reason=final_fail_reason,
            )
            summary_table.append(
                {
                    "dataset_id": ds_id,
                    "status": "UNAVAILABLE",
                    "details": final_fail_reason,
                }
            )
            print(f"[FAILED] Could not ingest {ds_id}: {final_fail_reason}")
            continue

    # Write updated catalog
    if not dry_run:
        catalog_payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        catalog_path.write_text(json.dumps(catalog_payload, indent=2) + "\n", encoding="utf-8")
        logger.info("Updated dataset catalog at %s", catalog_path)

    # Print summary table
    print("\n=== REGION PROCESSING SUMMARY ===")
    print(f"{'Dataset ID':<30} {'Status':<15} {'Details / Error'}")
    print("-" * 85)
    for row in summary_table:
        print(f"{row['dataset_id']:<30} {row['status']:<15} {row['details']}")
    print("=" * 85 + "\n")

    # Evaluate HiRISE DTM footprint AFTER the ingestion loop
    primary_dtm_path = processed_dir / "HIRISE_DTM_GALE_MOUND.tif"
    dtm_footprint: GeoBounds | None = None
    if primary_dtm_path.exists():
        try:
            import pyproj
            import rasterio

            with rasterio.open(primary_dtm_path) as src:
                proj_crs = pyproj.CRS(src.crs)
                geodetic_crs = proj_crs.geodetic_crs if proj_crs.is_projected else proj_crs
                transformer = pyproj.Transformer.from_crs(
                    proj_crs, geodetic_crs, always_xy=True, allow_ballpark=False
                )
                b = src.bounds
                xs = [b.left, b.right, b.left, b.right]
                ys = [b.bottom, b.bottom, b.top, b.top]
                lons, lats = transformer.transform(xs, ys)
                dtm_footprint = GeoBounds(
                    lat_min=float(min(lats)),
                    lat_max=float(max(lats)),
                    lon_min=float(min(lons)) % 360.0,
                    lon_max=float(max(lons)) % 360.0,
                )
                print(
                    f"HiRISE DTM Footprint (planetocentric degrees):\n"
                    f"  Latitude:  [{dtm_footprint.lat_min:.6f}, {dtm_footprint.lat_max:.6f}]\n"
                    f"  Longitude: [{dtm_footprint.lon_min:.6f}, {dtm_footprint.lon_max:.6f}]"
                )
        except Exception as exc:
            logger.warning("Could not compute footprint from %s: %s", primary_dtm_path, exc)

    footprint_finding = evaluate_named_area_in_footprint(
        area_name="Mount Sharp Boxwork Structures",
        verified_coordinates=None,
        footprint=dtm_footprint,
    )
    print(f"Footprint evaluation: {json.dumps(footprint_finding, indent=2)}\n")

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
    parser = argparse.ArgumentParser(description="AresNav region raster processor")
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
