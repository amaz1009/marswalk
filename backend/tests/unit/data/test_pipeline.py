"""Unit tests for the data ingestion and processing pipeline (T-DATA-01 to T-DATA-08).

All fixtures are synthetic code-generated samples, clearly labelled SYNTHETIC.
No binary data or real raw rasters are committed.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pyproj
import pytest

from app.data.crs import (
    CRSValidationError,
    convert_source_latitude_if_needed,
    inspect_raster_crs,
)
from app.data.footprint import (
    evaluate_named_area_in_footprint,
    point_in_footprint,
)
from app.data.loaders import (
    load_catalog,
    load_processing_manifest,
    load_region_config,
    validate_region_config,
)
from app.data.pipeline import (
    append_to_processing_manifest,
    compute_coverage_statistics,
    create_processing_step,
    normalize_nodata,
    write_cog_geotiff,
)
from app.models.datasets import DatasetRecord
from app.models.enums import DatasetStatus
from app.models.geometry import GeoBounds
from app.utils.coordinates import (
    MARS_ELLIPSOID_WKT,
    MARS_EQUATORIAL_RADIUS_M,
    MARS_POLAR_RADIUS_M,
    MARS_SPHERE_WKT,
    planetographic_to_planetocentric,
)
from scripts.download_data import (
    compute_file_sha256,
    download_single_dataset,
    load_source_ledger,
    probe_dataset,
)
from scripts.process_region import (
    REQUIRED_SUCCESS_KEYS,
    RasterProcessFailureResult,
    RasterProcessSuccessResult,
    get_dataset_sha256,
    process_single_raster,
    run_pipeline,
)


def test_t_data_01_catalog_records_validation() -> None:
    """T-DATA-01: Every catalog entry validates as DatasetRecord.

    Required provenance fields (mission, instrument, source_archive, source_url,
    product_ids, citation) must be non-empty strings/lists.
    Every record must contain at least one limitation.
    """
    catalog = load_catalog()
    assert len(catalog) >= 3, "Catalog must define at least the core datasets"

    for ds in catalog:
        assert isinstance(ds, DatasetRecord)
        assert ds.dataset_id == ds.dataset_id.upper()
        assert len(ds.name.strip()) > 0
        assert len(ds.mission.strip()) > 0
        assert len(ds.instrument.strip()) > 0
        assert len(ds.source_archive.strip()) > 0
        assert len(ds.source_url.strip()) > 0
        assert len(ds.product_ids) >= 1
        assert len(ds.citation.strip()) > 0
        assert len(ds.limitations) >= 1, f"Dataset {ds.dataset_id} must have limitations"


def test_t_data_02_source_nodata_becomes_nan() -> None:
    """T-DATA-02: Source nodata values become NaN, never 0.

    Synthetic array uses -9999.0 as an arbitrary synthetic sentinel value.
    Valid values include 0.0 (e.g. elevation at datum) and 100.0.
    """
    np = pytest.importorskip("numpy")

    # Synthetic fixture: 1D array with valid elevation, synthetic sentinel, and valid zero
    raw_array = np.array([100.0, -9999.0, 0.0, -9999.0, 50.5], dtype=np.float32)
    normalized = normalize_nodata(raw_array, source_nodata=-9999.0)

    # Sentinel must be converted to IEEE 754 NaN
    assert np.isnan(normalized[1])
    assert np.isnan(normalized[3])

    # Valid values must be preserved exactly (never zeroed out)
    assert normalized[0] == 100.0
    assert normalized[2] == 0.0  # Valid zero stays zero
    assert normalized[4] == 50.5

    # Coverage statistics must count NaNs accurately
    stats = compute_coverage_statistics(normalized)
    assert stats["total_cells"] == 5
    assert stats["nodata_cells"] == 2
    assert stats["valid_cells"] == 3
    assert math.isclose(stats["valid_fraction"], 3 / 5, rel_tol=1e-6)


def test_t_data_03_unreadable_or_invalid_crs_rejected() -> None:
    """T-DATA-03: A raster with no readable or invalid CRS is rejected.

    Must raise CRSValidationError and not be accepted into the pipeline.
    Uses pyproj.CRS parsing to verify observed ellipsoid axes and datum.
    """
    # 1. Empty / None CRS
    with pytest.raises(CRSValidationError, match="No readable CRS"):
        inspect_raster_crs(None)

    with pytest.raises(CRSValidationError, match="No readable CRS"):
        inspect_raster_crs("   ")

    # 2. Non-Mars CRS (e.g. Earth WGS84 and Earth sphere)
    earth_crs = "+proj=longlat +datum=WGS84 +no_defs"
    with pytest.raises(CRSValidationError, match="neither an accepted Mars sphere"):
        inspect_raster_crs(earth_crs)

    earth_sphere = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=6378137 +units=m"
    with pytest.raises(CRSValidationError, match="neither an accepted Mars sphere"):
        inspect_raster_crs(earth_sphere)

    # 3. Valid Mars IAU 2000 sphere equirectangular CRS (R=3396190 m)
    valid_mars_eqc = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +x_0=0 +y_0=0 +R=3396190 +units=m"
    res_sphere_eqc = inspect_raster_crs(valid_mars_eqc)
    assert res_sphere_eqc["is_valid"] is True
    assert res_sphere_eqc["datum_type"] == "SPHERE"
    assert res_sphere_eqc["matched_sphere"] == "MARS_2000_SPHERE"
    assert res_sphere_eqc["latitude_type"] == "PLANETOCENTRIC"
    assert res_sphere_eqc["is_projected"] is True

    # 4. Valid Mars MOLA MEGDR sphere equirectangular CRS (R=3396000 m)
    mola_sphere_eqc = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +x_0=0 +y_0=0 +R=3396000 +units=m"
    res_mola = inspect_raster_crs(mola_sphere_eqc)
    assert res_mola["is_valid"] is True
    assert res_mola["datum_type"] == "SPHERE"
    assert res_mola["matched_sphere"] == "MOLA_MEGDR_SPHERE"
    assert res_mola["latitude_type"] == "PLANETOCENTRIC"
    assert res_mola["is_projected"] is True

    # Derive lon/lat bounds with math from geotransform (no pasted literals)
    # On a simple cylindrical (equirectangular) sphere:
    #   lon_deg = central_meridian + math.degrees(x / R)
    #   lat_deg = math.degrees(y / R)
    r_mola = 3396000.0
    cm_deg = 180.0
    test_x_left = -5334223.0
    test_x_right = -463.0
    test_y_bottom = -2607153.0
    test_y_top = 463.0

    mola_proj = pyproj.CRS(mola_sphere_eqc)
    transformer = pyproj.Transformer.from_crs(
        mola_proj, mola_proj.geodetic_crs, always_xy=True, allow_ballpark=False
    )
    calc_lons, calc_lats = transformer.transform(
        [test_x_left, test_x_right], [test_y_bottom, test_y_top]
    )

    expected_lon_min = cm_deg + math.degrees(test_x_left / r_mola)
    expected_lon_max = cm_deg + math.degrees(test_x_right / r_mola)
    expected_lat_min = math.degrees(test_y_bottom / r_mola)
    expected_lat_max = math.degrees(test_y_top / r_mola)

    assert math.isclose(calc_lons[0], expected_lon_min, rel_tol=1e-9)
    assert math.isclose(calc_lons[1], expected_lon_max, rel_tol=1e-9)
    assert math.isclose(calc_lats[0], expected_lat_min, rel_tol=1e-9)
    assert math.isclose(calc_lats[1], expected_lat_max, rel_tol=1e-9)

    # 5. Non-accepted sphere (e.g. 3396500 m) is rejected
    rejected_sphere = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +x_0=0 +y_0=0 +R=3396500 +units=m"
    with pytest.raises(CRSValidationError, match="neither an accepted Mars sphere"):
        inspect_raster_crs(rejected_sphere)

    # 6. Valid Mars sphere geographic WKT -> PLANETOCENTRIC by construction
    res_sphere_wkt = inspect_raster_crs(MARS_SPHERE_WKT)
    assert res_sphere_wkt["is_valid"] is True
    assert res_sphere_wkt["datum_type"] == "SPHERE"
    assert res_sphere_wkt["latitude_type"] == "PLANETOCENTRIC"
    assert res_sphere_wkt["is_geographic"] is True

    # 5. Mars ellipsoid WKT with no declaration -> raises CRSValidationError
    with pytest.raises(
        CRSValidationError, match="latitude type not declared; cannot be determined from the CRS"
    ):
        inspect_raster_crs(MARS_ELLIPSOID_WKT, declared_latitude_type=None)

    # 6. Mars ellipsoid WKT with declared_latitude_type="PLANETOGRAPHIC"
    res_ellips_graphic = inspect_raster_crs(
        MARS_ELLIPSOID_WKT, declared_latitude_type="PLANETOGRAPHIC"
    )
    assert res_ellips_graphic["is_valid"] is True
    assert res_ellips_graphic["datum_type"] == "ELLIPSOID"
    assert res_ellips_graphic["latitude_type"] == "PLANETOGRAPHIC"
    assert res_ellips_graphic["is_geographic"] is True

    # 7. Mars ellipsoid WKT with invalid declaration string -> raises CRSValidationError
    with pytest.raises(CRSValidationError, match="Invalid declared_latitude_type"):
        inspect_raster_crs(MARS_ELLIPSOID_WKT, declared_latitude_type="UNSUPPORTED_TYPE")

    # 8. convert_source_latitude_if_needed maps planetographic latitude as
    # app.utils.coordinates does.
    # Computed both by coordinates function AND by closed formula:
    #   tan(lat_c) = (b^2 / a^2) * tan(lat_g)
    # using module constants MARS_EQUATORIAL_RADIUS_M and MARS_POLAR_RADIUS_M
    # (no pasted numeric literal).
    test_lat_graphic = 45.0
    converted_lat = convert_source_latitude_if_needed(test_lat_graphic, res_ellips_graphic)

    expected_func = planetographic_to_planetocentric(test_lat_graphic)
    a = MARS_EQUATORIAL_RADIUS_M
    b = MARS_POLAR_RADIUS_M
    phi_g_rad = math.radians(test_lat_graphic)
    phi_c_rad = math.atan(((b / a) ** 2) * math.tan(phi_g_rad))
    expected_formula = math.degrees(phi_c_rad)

    assert math.isclose(converted_lat, expected_func, rel_tol=1e-12)
    assert math.isclose(converted_lat, expected_formula, rel_tol=1e-12)


def test_t_data_04_footprint_evaluation_and_bounding() -> None:
    """T-DATA-04: Spatial containment and boxwork UNKNOWN rule.

    Synthetic test bounding box: arbitrary SYNTHETIC rectangle [-5.0, -4.5] lat,
    [137.0, 137.5] lon with no reference to boxwork or Mount Sharp coordinates.
    """
    # Arbitrary SYNTHETIC rectangle:
    footprint = GeoBounds(lat_min=-5.0, lat_max=-4.5, lon_min=137.0, lon_max=137.5)

    # Point strictly inside
    assert point_in_footprint(lat=-4.8, lon=137.2, footprint=footprint) is True

    # Point strictly outside
    assert point_in_footprint(lat=-5.5, lon=137.2, footprint=footprint) is False
    assert point_in_footprint(lat=-4.8, lon=136.5, footprint=footprint) is False

    # Boxwork structures with unverified coordinates must report status UNKNOWN
    res = evaluate_named_area_in_footprint(
        area_name="Mount Sharp Boxwork Structures",
        verified_coordinates=None,
        footprint=footprint,
    )
    assert res["status"] == "UNKNOWN"
    assert res["is_inside"] is None
    assert "never hard-coded" in res["reason"]


def test_t_data_05_source_ledger_sha256(tmp_path: Path) -> None:
    """T-DATA-05: Source-ledger SHA-256 values match the files.

    Expected SHA-256 is derived dynamically in the test via hashlib.sha256
    from the synthetic payload bytes, not hardcoded as a magic literal.
    """
    synthetic_payload = b"ARESNAV_SYNTHETIC_DATA_PAYLOAD_TEST_T_DATA_05"
    expected_sha256 = hashlib.sha256(synthetic_payload).hexdigest()

    test_file = tmp_path / "synthetic_raw.bin"
    test_file.write_bytes(synthetic_payload)

    computed_sha256 = compute_file_sha256(test_file)
    assert computed_sha256 == expected_sha256


def test_t_data_06_download_handles_unreachable_server() -> None:
    """T-DATA-06: Download script reports unreachable server without crashing.

    Simulates connection failure and validates graceful report.
    """
    mock_client = MagicMock()
    mock_client.head.side_effect = Exception("Connection refused / simulated DNS failure")

    synthetic_entry = {
        "dataset_id": "SYNTHETIC_OFFLINE_DATASET",
        "url": "https://unreachable.pds.nasa.gov/data/sample.img",
        "expected_size_bytes": 1024,
    }

    result = probe_dataset(mock_client, synthetic_entry)
    assert result["status"] == "UNREACHABLE"
    assert "Connection error" in result["message"]
    assert result["dataset_id"] == "SYNTHETIC_OFFLINE_DATASET"


def test_t_data_07_region_config_validation() -> None:
    """T-DATA-07: Region config validation.

    Validates that gale_mount_sharp.json references datasets existing in catalog.
    Also tests that a missing primary DTM triggers a validation error.
    """
    catalog = load_catalog()
    region_data = load_region_config("gale_mount_sharp")

    # Real configuration must have zero errors
    errors = validate_region_config(region_data, catalog)
    assert len(errors) == 0, f"Expected clean region validation, got: {errors}"

    # Mutated configuration with non-existent primary DTM
    bad_region = dict(region_data)
    bad_region["analysis"] = {
        "primary_dtm_dataset_id": "NON_EXISTENT_PRIMARY_DTM",
        "analysis_crs": "+proj=eqc +R=3396190",
        "cell_size_m": 1.0,
        "max_grid_cells": 1000,
    }
    mutated_errors = validate_region_config(bad_region, catalog)
    assert any("NON_EXISTENT_PRIMARY_DTM" in err for err in mutated_errors)


def test_t_data_08_processing_manifest_records_steps(tmp_path: Path) -> None:
    """T-DATA-08: Processing manifest records every pipeline step for every output.

    Uses create_processing_step and append_to_processing_manifest to verify schema.
    """
    manifest_file = tmp_path / "processing_manifest.json"

    steps = [
        create_processing_step(
            step_name="detect_format",
            tool_name="rasterio 1.5.2",
            parameters={"driver": "PDS3"},
        ),
        create_processing_step(
            step_name="validate_crs",
            tool_name="app.data.crs",
            parameters={"datum": "SPHERE"},
        ),
        create_processing_step(
            step_name="nodata_normalization",
            tool_name="numpy 2.5.4",
            parameters={"source_nodata": -9999.0, "target": "NaN"},
        ),
    ]

    append_to_processing_manifest(
        manifest_path=manifest_file,
        output_path="backend/data/processed/TEST_SYNTHETIC.tif",
        dataset_id="TEST_SYNTHETIC",
        inputs=["backend/data/raw/test.img"],
        steps=steps,
        status="COMPLETED",
    )

    manifest_content = load_processing_manifest(manifest_file)
    assert len(manifest_content) == 1
    entry = manifest_content[0]
    assert entry["dataset_id"] == "TEST_SYNTHETIC"
    assert entry["status"] == "COMPLETED"
    assert len(entry["steps"]) == 3
    assert entry["steps"][0]["step"] == "detect_format"
    assert entry["steps"][1]["step"] == "validate_crs"
    assert entry["steps"][2]["step"] == "nodata_normalization"


def test_t_data_09_rasterio_write_cog_roundtrip(tmp_path: Path) -> None:
    """T-DATA-09: Synthetic rasterio Cloud-Optimized GeoTIFF write and readback roundtrip.

    Writes a small float32 array with NaN, a Mars WKT CRS and an affine transform.
    Reads back using rasterio and asserts:
    - NaN preservation
    - CRS round-trip
    - Transform round-trip
    - Layout flags (profile['tiled'] == True, profile['compress'] == 'deflate')
      as reported by rasterio profile.
    """
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    # Synthetic 2x2 raster with valid values and one NaN
    data = np.array([[10.5, np.nan], [20.0, 30.5]], dtype=np.float32)
    transform = from_origin(137.0, -4.0, 1.0, 1.0)
    out_file = tmp_path / "synthetic_cog.tif"

    write_cog_geotiff(
        output_path=out_file,
        data=data,
        transform=transform,
        crs=MARS_SPHERE_WKT,
    )

    with rasterio.open(out_file) as src:
        # Check layout flags as actually reported by rasterio profile
        assert src.profile["tiled"] is True
        assert src.profile["compress"] == "deflate"

        # Check values and NaN preservation
        read_arr = src.read(1)
        assert read_arr[0, 0] == 10.5
        assert np.isnan(read_arr[0, 1])
        assert read_arr[1, 0] == 20.0
        assert read_arr[1, 1] == 30.5

        # Check transform and CRS
        assert src.transform == transform
        assert src.crs is not None
        crs_info = inspect_raster_crs(src.crs.to_wkt())
        assert crs_info["datum_type"] == "SPHERE"


def test_t_data_10_corrupted_raw_file_handled_gracefully(tmp_path: Path) -> None:
    """T-DATA-10: process_single_raster gracefully handles an unreadable file.

    Corrupted non-raster dummy file marks dataset UNAVAILABLE without raising
    an uncaught exception.
    """
    corrupted_file = tmp_path / "corrupted_raw.img"
    corrupted_file.write_bytes(b"INVALID_HEADER_NOT_A_RASTER_DATA_FILE")
    out_file = tmp_path / "out.tif"

    res = process_single_raster(
        raw_file_path=corrupted_file,
        dataset_id="SYNTHETIC_CORRUPTED",
        output_tif_path=out_file,
        region_bounds={},
    )

    assert res["success"] is False
    assert res["status"] == DatasetStatus.UNAVAILABLE
    assert res["status_reason"] is not None
    assert "RasterioIOError" in res["status_reason"] or "not recognized" in res["status_reason"]
    assert len(res["steps"]) >= 1


def test_t_data_11_catalog_update_writes_available_with_computed_coverage(
    tmp_path: Path,
) -> None:
    """T-DATA-11: Catalog update after successful ingest writes AVAILABLE.

    Computes correct coverage GeoBounds from raster transform and bounds,
    appends valid data fraction to limitations, and retrieves SHA-256.
    """
    np = pytest.importorskip("numpy")
    from rasterio.transform import from_origin

    # Create synthetic 10x10 raster: 75 valid cells (10.0), 25 NaN cells
    arr = np.full((10, 10), 10.0, dtype=np.float32)
    arr[0:5, 0:5] = np.nan  # 25 NaNs
    transform = from_origin(137.2, -4.7, 1.01, 1.01)

    raw_file = tmp_path / "synthetic_dtm.tif"
    write_cog_geotiff(
        output_path=raw_file,
        data=arr,
        transform=transform,
        crs=MARS_SPHERE_WKT,
    )

    ledger_path = tmp_path / "source_ledger.json"
    synthetic_sha = compute_file_sha256(raw_file)
    ledger_record = {
        "file_path": "data/raw/synthetic_dtm.tif",
        "dataset_id": "SYNTHETIC_DTM",
        "url": "https://example.com/synthetic_dtm.tif",
        "retrieved_at": "2026-11-14T00:00:00Z",
        "size_bytes": raw_file.stat().st_size,
        "sha256": synthetic_sha,
    }
    ledger_path.write_text(json.dumps([ledger_record], indent=2) + "\n", encoding="utf-8")

    out_cog = tmp_path / "processed_dtm.tif"
    res = process_single_raster(
        raw_file_path=raw_file,
        dataset_id="SYNTHETIC_DTM",
        output_tif_path=out_cog,
        region_bounds={},
    )

    assert res["success"] is True
    assert res["status"] == DatasetStatus.AVAILABLE
    assert res["status_reason"] is None
    assert res["native_resolution_m"] == 1.01

    # Check coverage bounds
    bounds = res["coverage_bounds"]
    assert "lat_min" in bounds and "lat_max" in bounds
    assert "lon_min" in bounds and "lon_max" in bounds
    assert bounds["lat_min"] <= bounds["lat_max"]
    assert bounds["lon_min"] <= bounds["lon_max"]

    # Check dynamic limitation string (75 valid, 25 nodata out of 100)
    expected_lim = (
        "Valid data cell coverage: 75.0% (25 nodata cells out of 100 total in bounding box)."
    )
    assert res["coverage_limitation"] == expected_lim

    # Verify sha lookup
    looked_up_sha = get_dataset_sha256(ledger_path, "SYNTHETIC_DTM", "synthetic_dtm.tif")
    assert looked_up_sha == synthetic_sha

    # Verify model validation of an updated catalog record
    catalog_record_dict = {
        "dataset_id": "SYNTHETIC_DTM",
        "name": "Synthetic DTM for Test",
        "mission": "SYNTHETIC",
        "instrument": "SYNTHETIC",
        "source_archive": "SYNTHETIC ARCHIVE",
        "source_url": "https://example.com/synthetic_dtm.tif",
        "product_ids": ["synthetic_dtm.tif"],
        "citation": "Synthetic Citation 2026",
        "data_type": "ELEVATION",
        "data_class": "MEASURED",
        "units": "m",
        "source_crs": MARS_SPHERE_WKT,
        "source_conventions": "Planetocentric sphere",
        "native_resolution_m": res["native_resolution_m"],
        "temporal_coverage": {"description": "Synthetic"},
        "coverage_bounds": bounds,
        "region_coverage_fraction": res["coverage_fraction"],
        "status": "AVAILABLE",
        "status_reason": None,
        "processing_steps": [
            {
                "step": s.step,
                "tool": s.tool,
                "parameters": s.parameters,
                "completed_at": s.completed_at.isoformat(),
            }
            for s in res["steps"]
        ],
        "limitations": [expected_lim],
        "sha256": looked_up_sha,
    }
    validated = DatasetRecord.model_validate(catalog_record_dict)
    assert validated.status == DatasetStatus.AVAILABLE
    assert validated.native_resolution_m == 1.01


def test_t_data_12_footprint_evaluated_after_ingest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-DATA-12: Footprint evaluated after ingestion.

    Records call order via monkeypatch to assert ingestion completes before
    footprint evaluation.
    Boxwork containment reported UNKNOWN when feature coordinates not cited.
    """
    import scripts.process_region as pr_module
    from scripts.process_region import run_pipeline

    # 1. Verify call order in run_pipeline
    call_events: list[str] = []

    test_data_dir = tmp_path / "data"
    manifests_dir = test_data_dir / "manifests"
    raw_dir = test_data_dir / "raw"
    processed_dir = test_data_dir / "processed"
    regions_dir = test_data_dir / "regions"
    for d in (manifests_dir, raw_dir, processed_dir, regions_dir):
        d.mkdir(parents=True, exist_ok=True)

    dummy_raw = raw_dir / "test_raw.img"
    dummy_raw.write_bytes(b"SYNTHETIC_RAW_DATA")

    data_sources_payload = [
        {
            "dataset_id": "TEST_DTM",
            "product_ids": ["test_raw.img"],
            "url": "https://example.com/test_raw.img",
        }
    ]
    (manifests_dir / "data_sources.json").write_text(
        json.dumps(data_sources_payload, indent=2), encoding="utf-8"
    )

    catalog_payload = {
        "catalog_version": "1.0",
        "generated_at": "2026-11-14T00:00:00Z",
        "datasets": [
            {
                "dataset_id": "TEST_DTM",
                "name": "Test DTM",
                "mission": "MRO",
                "instrument": "HiRISE",
                "source_archive": "NASA PDS",
                "source_url": "https://example.com/test_raw.img",
                "product_ids": ["test_raw.img"],
                "citation": "Test citation",
                "data_type": "ELEVATION",
                "data_class": "MEASURED",
                "units": "m",
                "source_crs": MARS_SPHERE_WKT,
                "source_conventions": "Mars IAU 2000 sphere",
                "native_resolution_m": 1.0,
                "temporal_coverage": {"description": "Test"},
                "coverage_bounds": {
                    "lat_min": -5.0,
                    "lat_max": -4.0,
                    "lon_min": 137.0,
                    "lon_max": 138.0,
                },
                "status": "UNAVAILABLE",
                "status_reason": "Not yet processed",
                "processing_steps": [],
                "limitations": ["Test limitation"],
            }
        ],
    }
    (manifests_dir / "dataset_catalog.json").write_text(
        json.dumps(catalog_payload, indent=2), encoding="utf-8"
    )

    region_payload = {
        "region_id": "test_region",
        "name": "Test Region",
        "bounds": {"lat_min": -5.0, "lat_max": -4.0, "lon_min": 137.0, "lon_max": 138.0},
        "analysis": {
            "primary_dtm_dataset_id": "TEST_DTM",
            "analysis_crs": "+proj=eqc +R=3396190",
            "cell_size_m": 1.0,
            "max_grid_cells": 1000,
        },
        "layers": [],
    }
    (regions_dir / "test_region.json").write_text(
        json.dumps(region_payload, indent=2), encoding="utf-8"
    )

    def mock_process_raster(*args, **kwargs):
        call_events.append("ingest")
        return {
            "success": True,
            "status": DatasetStatus.AVAILABLE,
            "status_reason": None,
            "steps": [],
            "coverage_fraction": 1.0,
            "coverage_bounds": {
                "lat_min": -4.95,
                "lat_max": -4.72,
                "lon_min": 137.24,
                "lon_max": 137.35,
            },
            "native_resolution_m": 1.01,
            "coverage_limitation": (
                "Valid data cell coverage: 100.0% (0 nodata cells out of 100 total in "
                "bounding box)."
            ),
            "processed_path": "data/processed/TEST_DTM.tif",
            "source_conventions": "Mars IAU 2000 sphere",
        }

    orig_evaluate = pr_module.evaluate_named_area_in_footprint

    def mock_evaluate(*args, **kwargs):
        call_events.append("evaluate_footprint")
        return orig_evaluate(*args, **kwargs)

    monkeypatch.setattr(pr_module, "process_single_raster", mock_process_raster)
    monkeypatch.setattr(pr_module, "evaluate_named_area_in_footprint", mock_evaluate)

    exit_code = run_pipeline(region_id="test_region", data_dir=test_data_dir, dry_run=False)
    assert exit_code == 0
    assert call_events == ["ingest", "evaluate_footprint"], (
        f"Ingestion must occur strictly before footprint evaluation, got: {call_events}"
    )

    # 2. Verify boxwork containment UNKNOWN behavior
    dtm_footprint = GeoBounds(
        lat_min=-4.948820,
        lat_max=-4.720525,
        lon_min=137.238928,
        lon_max=137.353903,
    )

    finding = evaluate_named_area_in_footprint(
        area_name="Mount Sharp Boxwork Structures",
        verified_coordinates=None,
        footprint=dtm_footprint,
    )

    assert finding["status"] == "UNKNOWN"
    assert finding["is_inside"] is None
    assert (
        "Boxwork feature coordinates are not verified from a cited data source; "
        "containment cannot be evaluated without verified feature coordinates." in finding["reason"]
    )
    assert "never hard-coded" in finding["reason"]


def test_t_data_13_companion_file_parsing_and_download(tmp_path: Path) -> None:
    """T-DATA-13: Companion file declaration parsed and downloaded alongside primary.

    Recorded in source_ledger with distinct file_path without clobbering primary.
    """
    raw_dir = tmp_path / "raw"
    ledger_path = tmp_path / "source_ledger.json"

    entry = {
        "dataset_id": "SYNTHETIC_MOLA_MEGDR",
        "product_id": "synthetic_megt.img",
        "url": "https://example.com/data/synthetic_megt.img",
        "expected_format": "PDS3_IMG",
        "expected_size_bytes": 100,
        "companion_file": {
            "product_id": "synthetic_megt.lbl",
            "url": "https://example.com/data/synthetic_megt.lbl",
            "expected_format": "PDS3_LBL",
            "expected_size_bytes": 40,
        },
    }

    # 1. Test probe_dataset with companion file
    mock_client = MagicMock()
    mock_head_resp = MagicMock()
    mock_head_resp.is_success = True
    mock_head_resp.status_code = 200
    mock_head_resp.headers = {"Content-Length": "100"}
    mock_client.head.return_value = mock_head_resp

    probe_res = probe_dataset(mock_client, entry)
    assert probe_res["status"] == "OK"
    assert "companion" in probe_res
    assert probe_res["companion"]["product_id"] == "synthetic_megt.lbl"
    assert probe_res["companion"]["status"] == "OK"

    # 2. Test download_single_dataset downloading both primary and companion
    def mock_stream(method, url, **kwargs):
        ctx = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        if "synthetic_megt.img" in url:
            resp.iter_bytes.return_value = [b"A" * 100]
        else:
            resp.iter_bytes.return_value = [b"B" * 40]
        ctx.__enter__.return_value = resp
        ctx.__exit__.return_value = None
        return ctx

    mock_client.stream.side_effect = mock_stream

    dl_res = download_single_dataset(
        client=mock_client,
        entry=entry,
        raw_dir=raw_dir,
        ledger_path=ledger_path,
    )

    assert dl_res["success"] is True
    assert dl_res["companion"] is not None
    assert dl_res["companion"]["success"] is True

    # Both files must exist on disk
    primary_file = raw_dir / "synthetic_megt.img"
    companion_file = raw_dir / "synthetic_megt.lbl"
    assert primary_file.exists()
    assert companion_file.exists()
    assert primary_file.stat().st_size == 100
    assert companion_file.stat().st_size == 40

    # Ledger must contain both entries keyed distinctly by file_path
    ledger_entries = load_source_ledger(ledger_path)
    assert len(ledger_entries) == 2
    paths = {e["file_path"] for e in ledger_entries}
    assert paths == {"data/raw/synthetic_megt.img", "data/raw/synthetic_megt.lbl"}

    # SHA256 matches the file bytes
    for e in ledger_entries:
        if e["file_path"] == "data/raw/synthetic_megt.img":
            assert e["sha256"] == hashlib.sha256(b"A" * 100).hexdigest()
        elif e["file_path"] == "data/raw/synthetic_megt.lbl":
            assert e["sha256"] == hashlib.sha256(b"B" * 40).hexdigest()


def test_t_data_14_companion_label_is_opened_by_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-DATA-14: Ingestion pipeline opens companion label path (.lbl), not .IMG.

    When a dataset has a companion file with expected_format PDS3_LBL, process_region
    opens the companion label file, recording the opened path in the processing manifest.
    """
    import scripts.process_region as pr_module
    from scripts.process_region import run_pipeline

    test_data_dir = tmp_path / "data"
    manifests_dir = test_data_dir / "manifests"
    raw_dir = test_data_dir / "raw"
    processed_dir = test_data_dir / "processed"
    regions_dir = test_data_dir / "regions"
    for d in (manifests_dir, raw_dir, processed_dir, regions_dir):
        d.mkdir(parents=True, exist_ok=True)

    primary_raw = raw_dir / "mola_test.img"
    companion_lbl = raw_dir / "mola_test.lbl"
    primary_raw.write_bytes(b"SYNTHETIC_MOLA_IMG_PAYLOAD")
    companion_lbl.write_bytes(b"SYNTHETIC_MOLA_LBL_HEADER")

    data_sources_payload = [
        {
            "dataset_id": "MOLA_MEGDR_GALE",
            "product_ids": ["mola_test.img"],
            "url": "https://example.com/mola_test.img",
            "companion_file": {
                "product_id": "mola_test.lbl",
                "url": "https://example.com/mola_test.lbl",
                "expected_format": "PDS3_LBL",
                "expected_size_bytes": None,
            },
        }
    ]
    (manifests_dir / "data_sources.json").write_text(
        json.dumps(data_sources_payload, indent=2), encoding="utf-8"
    )

    catalog_payload = {
        "catalog_version": "1.0",
        "generated_at": "2026-11-14T00:00:00Z",
        "datasets": [
            {
                "dataset_id": "MOLA_MEGDR_GALE",
                "name": "MOLA MEGDR Gale",
                "mission": "MGS",
                "instrument": "MOLA",
                "source_archive": "NASA PDS",
                "source_url": "https://example.com/mola_test.img",
                "product_ids": ["mola_test.img"],
                "citation": "MOLA Citation",
                "data_type": "ELEVATION",
                "data_class": "MEASURED",
                "units": "m",
                "source_crs": MARS_SPHERE_WKT,
                "source_conventions": "Mars MOLA MEGDR sphere",
                "native_resolution_m": 463.0,
                "temporal_coverage": {"description": "Test"},
                "coverage_bounds": {
                    "lat_min": -44.0,
                    "lat_max": 0.0,
                    "lon_min": 90.0,
                    "lon_max": 180.0,
                },
                "status": "UNAVAILABLE",
                "status_reason": "Not yet processed",
                "processing_steps": [],
                "limitations": ["Placeholder limitation"],
            }
        ],
    }
    (manifests_dir / "dataset_catalog.json").write_text(
        json.dumps(catalog_payload, indent=2), encoding="utf-8"
    )

    region_payload = {
        "region_id": "test_region",
        "name": "Test Region",
        "bounds": {"lat_min": -44.0, "lat_max": 0.0, "lon_min": 90.0, "lon_max": 180.0},
        "analysis": {
            "primary_dtm_dataset_id": "MOLA_MEGDR_GALE",
            "analysis_crs": "+proj=eqc +R=3396190",
            "cell_size_m": 463.0,
            "max_grid_cells": 1000,
        },
        "layers": [],
    }
    (regions_dir / "test_region.json").write_text(
        json.dumps(region_payload, indent=2), encoding="utf-8"
    )

    opened_files: list[str] = []

    def mock_process_raster(raw_file_path, **kwargs):
        opened_files.append(raw_file_path.name)
        step = create_processing_step(
            step_name="detect_format",
            tool_name="rasterio 1.5.2",
            parameters={
                "source_file": str(raw_file_path.name),
                "opened_path": str(raw_file_path.as_posix()),
            },
        )
        return {
            "success": True,
            "status": DatasetStatus.AVAILABLE,
            "status_reason": None,
            "steps": [step],
            "coverage_fraction": 1.0,
            "coverage_bounds": {
                "lat_min": -43.986709,
                "lat_max": 0.007812,
                "lon_min": 90.003397,
                "lon_max": 179.992188,
            },
            "native_resolution_m": 463.0,
            "coverage_limitation": (
                "Valid data cell coverage: 100.0% (0 nodata cells out of 100 total in "
                "bounding box)."
            ),
            "processed_path": "data/processed/MOLA_MEGDR_GALE.tif",
            "source_conventions": "Mars MOLA MEGDR sphere (R=3396000 m)",
        }

    monkeypatch.setattr(pr_module, "process_single_raster", mock_process_raster)

    exit_code = run_pipeline(region_id="test_region", data_dir=test_data_dir, dry_run=False)
    assert exit_code == 0
    # Must open mola_test.lbl, NOT mola_test.img
    assert opened_files == ["mola_test.lbl"]

    # Manifest records opened path
    manifest_entries = load_processing_manifest(manifests_dir / "processing_manifest.json")
    assert len(manifest_entries) == 1
    detect_step = manifest_entries[0]["steps"][0]
    assert detect_step["parameters"]["source_file"] == "mola_test.lbl"
    assert "mola_test.lbl" in detect_step["parameters"]["opened_path"]


def test_t_data_15_catalog_limitations_audit() -> None:
    """T-DATA-15: Audit catalog limitations for unverified claims.

    Asserts that:
    1. No catalog record limitation contains 'boxwork structures' or 'layered mound'.
    2. The DTM record (HIRISE_DTM_GALE_MOUND) reports boxwork containment as UNKNOWN.
    3. The Ortho record does not claim 'Reduced C-version'.
    4. The MOLA record contains the GDAL PDS driver edge caveat.
    """
    catalog_path = Path("backend/data/manifests/dataset_catalog.json")
    if not catalog_path.exists():
        catalog_path = Path("data/manifests/dataset_catalog.json")
    assert catalog_path.exists(), "dataset_catalog.json must exist"

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    datasets = data.get("datasets", [])
    assert len(datasets) > 0

    dtm_found = False
    for ds in datasets:
        ds_id = ds.get("dataset_id")
        limitations = ds.get("limitations", [])

        # 1. No limitation in any catalog record may assert unverified boxwork or layered mound
        for lim in limitations:
            lim_lower = lim.lower()
            assert "boxwork structures" not in lim_lower, (
                f"Dataset {ds_id} contains unverified 'boxwork structures' in limitation: {lim}"
            )
            assert "layered mound" not in lim_lower, (
                f"Dataset {ds_id} contains unverified 'layered mound' in limitation: {lim}"
            )

        if ds_id == "HIRISE_DTM_GALE_MOUND":
            dtm_found = True
            # DTM limitations must report UNKNOWN for boxwork containment and vertical datum
            assert any("boxwork" in lim and "UNKNOWN" in lim for lim in limitations), (
                f"DTM limitations missing boxwork UNKNOWN statement: {limitations}"
            )
            assert any("Vertical datum" in lim and "UNKNOWN" in lim for lim in limitations), (
                f"DTM limitations missing vertical datum UNKNOWN statement: {limitations}"
            )

        elif ds_id == "HIRISE_ORTHO_GALE_MOUND":
            for lim in limitations:
                assert "reduced c-version" not in lim.lower(), (
                    f"Ortho record contains unverified 'Reduced C-version': {lim}"
                )

        elif ds_id == "MOLA_MEGDR_GALE":
            assert any("GDAL PDS driver" in lim for lim in limitations), (
                f"MOLA limitations missing GDAL PDS driver edge caveat: {limitations}"
            )

    assert dtm_found, "HIRISE_DTM_GALE_MOUND record must exist in catalog"


def test_t_data_16_run_pipeline_monkeypatched_failure_marks_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-DATA-16: run_pipeline with monkeypatched failure result marks dataset UNAVAILABLE.

    Verifies that when process_single_raster returns a failure result, an incomplete result,
    or raises an exception:
    1. run_pipeline does not raise an uncaught exception.
    2. The dataset is marked UNAVAILABLE in the catalog with the real reason.
    3. The processing manifest records status FAILED.
    4. The loop continues, summary prints, and run_pipeline exits 0.
    """
    test_data_dir = tmp_path / "data"
    manifests_dir = test_data_dir / "manifests"
    regions_dir = test_data_dir / "regions"
    raw_dir = test_data_dir / "raw"
    processed_dir = test_data_dir / "processed"
    manifests_dir.mkdir(parents=True)
    regions_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)

    dummy_raw = raw_dir / "dummy_dtm.img"
    dummy_raw.write_bytes(b"DUMMY_RAW_RASTER_DATA")

    data_sources_payload = [
        {
            "dataset_id": "TEST_DTM",
            "source_archive": "SYNTHETIC_ARCHIVE",
            "product_ids": ["dummy_dtm.img"],
            "url": "https://example.com/dummy_dtm.img",
        }
    ]
    (manifests_dir / "data_sources.json").write_text(
        json.dumps(data_sources_payload, indent=2), encoding="utf-8"
    )

    catalog_payload = {
        "catalog_version": "1.0",
        "generated_at": "2026-11-14T00:00:00Z",
        "datasets": [
            {
                "dataset_id": "TEST_DTM",
                "name": "Test DTM for Failure Handling",
                "mission": "SYNTHETIC",
                "instrument": "SYNTHETIC",
                "source_archive": "SYNTHETIC ARCHIVE",
                "source_url": "https://example.com/dummy_dtm.img",
                "product_ids": ["dummy_dtm.img"],
                "citation": "Synthetic Citation 2026",
                "data_type": "ELEVATION",
                "data_class": "MEASURED",
                "units": "m",
                "source_crs": MARS_SPHERE_WKT,
                "source_conventions": "Mars IAU 2000 sphere",
                "native_resolution_m": 1.0,
                "temporal_coverage": {"description": "Test"},
                "coverage_bounds": {
                    "lat_min": -5.0,
                    "lat_max": -4.0,
                    "lon_min": 137.0,
                    "lon_max": 138.0,
                },
                "status": "UNAVAILABLE",
                "status_reason": "Not yet processed",
                "processing_steps": [],
                "limitations": ["Placeholder limitation"],
            }
        ],
    }
    (manifests_dir / "dataset_catalog.json").write_text(
        json.dumps(catalog_payload, indent=2), encoding="utf-8"
    )

    region_payload = {
        "region_id": "test_region",
        "name": "Test Region",
        "bounds": {"lat_min": -5.0, "lat_max": -4.0, "lon_min": 137.0, "lon_max": 138.0},
        "analysis": {
            "primary_dtm_dataset_id": "TEST_DTM",
            "analysis_crs": "+proj=eqc +R=3396190",
            "cell_size_m": 1.0,
            "max_grid_cells": 1000,
        },
        "layers": [],
    }
    (regions_dir / "test_region.json").write_text(
        json.dumps(region_payload, indent=2), encoding="utf-8"
    )

    # Sub-test A: process_single_raster returns failure result
    def mock_failure(*args: Any, **kwargs: Any) -> RasterProcessFailureResult:
        return {
            "success": False,
            "status": DatasetStatus.UNAVAILABLE,
            "status_reason": "Simulated hardware I/O read failure",
            "steps": [],
        }

    monkeypatch.setattr("scripts.process_region.process_single_raster", mock_failure)

    exit_code = run_pipeline(region_id="test_region", data_dir=test_data_dir, dry_run=False)
    assert exit_code == 0, f"run_pipeline must exit 0 on failure result, got {exit_code}"

    # Assert catalog record is marked UNAVAILABLE with real reason
    catalog = json.loads((manifests_dir / "dataset_catalog.json").read_text(encoding="utf-8"))
    rec = catalog["datasets"][0]
    assert rec["status"] == "UNAVAILABLE"
    assert "Simulated hardware I/O read failure" in rec["status_reason"]

    # Assert processing manifest records FAILED
    manifest_entries = load_processing_manifest(manifests_dir / "processing_manifest.json")
    assert len(manifest_entries) == 1
    assert manifest_entries[0]["status"] == "FAILED"
    assert "Simulated hardware I/O read failure" in str(manifest_entries[0]["status_reason"])

    # Sub-test B: incomplete result (missing 'bounds' and other required keys)
    def mock_incomplete(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "status": DatasetStatus.AVAILABLE,
            "status_reason": None,
            "steps": [],
            # Intentionally incomplete
        }

    monkeypatch.setattr("scripts.process_region.process_single_raster", mock_incomplete)

    exit_code_incomplete = run_pipeline(
        region_id="test_region", data_dir=test_data_dir, dry_run=False
    )
    assert exit_code_incomplete == 0, "run_pipeline must exit 0 on incomplete result"
    catalog_incomplete = json.loads(
        (manifests_dir / "dataset_catalog.json").read_text(encoding="utf-8")
    )
    rec_incomplete = catalog_incomplete["datasets"][0]
    assert rec_incomplete["status"] == "UNAVAILABLE"
    assert "missing keys" in rec_incomplete["status_reason"]

    # Sub-test C: process_single_raster raises unexpected exception
    def mock_raises(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Simulated unhandled pipeline crash")

    monkeypatch.setattr("scripts.process_region.process_single_raster", mock_raises)

    exit_code_raises = run_pipeline(region_id="test_region", data_dir=test_data_dir, dry_run=False)
    assert exit_code_raises == 0, "run_pipeline must exit 0 when process_single_raster raises"
    catalog_raises = json.loads(
        (manifests_dir / "dataset_catalog.json").read_text(encoding="utf-8")
    )
    rec_raises = catalog_raises["datasets"][0]
    assert rec_raises["status"] == "UNAVAILABLE"
    assert "Simulated unhandled pipeline crash" in rec_raises["status_reason"]

    # Sub-test D: incomplete result with 'bounds': None
    def mock_none_bounds(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "status": DatasetStatus.AVAILABLE,
            "status_reason": None,
            "steps": [],
            "coverage_fraction": 1.0,
            "coverage_bounds": {"lat_min": 0.0, "lat_max": 1.0, "lon_min": 0.0, "lon_max": 1.0},
            "bounds": None,
            "native_resolution_m": 1.0,
            "coverage_limitation": "Test coverage",
            "processed_path": "test.tif",
            "source_conventions": "Test sphere",
        }

    monkeypatch.setattr("scripts.process_region.process_single_raster", mock_none_bounds)

    exit_code_none_bounds = run_pipeline(
        region_id="test_region", data_dir=test_data_dir, dry_run=False
    )
    assert exit_code_none_bounds == 0, "run_pipeline must exit 0 on None bounds result"
    catalog_none_bounds = json.loads(
        (manifests_dir / "dataset_catalog.json").read_text(encoding="utf-8")
    )
    rec_none_bounds = catalog_none_bounds["datasets"][0]
    assert rec_none_bounds["status"] == "UNAVAILABLE"
    assert "bounds" in rec_none_bounds["status_reason"]


def test_t_data_17_success_result_contains_all_keys_read_by_pipeline(tmp_path: Path) -> None:
    """T-DATA-17: Success result must contain every key run_pipeline reads.

    Asserts that:
    1. The shared shape definition (RasterProcessSuccessResult) defines all keys read
       by run_pipeline.
    2. REQUIRED_SUCCESS_KEYS matches RasterProcessSuccessResult annotations.
    3. process_single_raster on a valid raster returns every key in the shared shape definition.
    4. res['bounds'] is a GeoBounds instance with valid coordinates.
    """
    np = pytest.importorskip("numpy")
    from rasterio.transform import from_origin

    # All keys read from res by run_pipeline during success branch execution
    keys_read_by_pipeline = {
        "success",
        "status",
        "status_reason",
        "steps",
        "coverage_fraction",
        "coverage_bounds",
        "bounds",
        "native_resolution_m",
        "coverage_limitation",
        "processed_path",
        "source_conventions",
    }

    # 1. Assert keys read by pipeline are defined in the shared shape definition
    shape_keys = set(RasterProcessSuccessResult.__annotations__.keys())
    assert keys_read_by_pipeline.issubset(shape_keys), (
        f"Keys read by pipeline missing from RasterProcessSuccessResult: "
        f"{keys_read_by_pipeline - shape_keys}"
    )

    # 2. Assert REQUIRED_SUCCESS_KEYS equals the shared shape definition keys
    assert set(REQUIRED_SUCCESS_KEYS) == shape_keys

    # 3. Process a synthetic raster and assert return value contains all shape keys
    arr = np.full((10, 10), 10.0, dtype=np.float32)
    transform = from_origin(137.2, -4.7, 1.0, 1.0)
    raw_file = tmp_path / "synthetic_success.tif"
    write_cog_geotiff(
        output_path=raw_file,
        data=arr,
        transform=transform,
        crs=MARS_SPHERE_WKT,
    )

    out_cog = tmp_path / "processed_success.tif"
    res = process_single_raster(
        raw_file_path=raw_file,
        dataset_id="SYNTHETIC_SUCCESS",
        output_tif_path=out_cog,
        region_bounds={},
    )

    assert res["success"] is True
    assert res["status"] == DatasetStatus.AVAILABLE
    assert res["status_reason"] is None

    # Assert every key in the shared shape definition is present in the actual success result
    res_keys = set(res.keys())
    for k in keys_read_by_pipeline:
        assert k in res_keys, f"Required pipeline key '{k}' missing from success result"
    assert shape_keys.issubset(res_keys)

    # 4. Explicitly verify 'bounds' is a GeoBounds object with expected attributes
    assert "bounds" in res
    assert isinstance(res["bounds"], GeoBounds)
    assert hasattr(res["bounds"], "lat_min")
    assert hasattr(res["bounds"], "lat_max")
    assert hasattr(res["bounds"], "lon_min")
    assert hasattr(res["bounds"], "lon_max")
    assert res["bounds"].lat_min < res["bounds"].lat_max
    assert res["bounds"].lon_min <= res["bounds"].lon_max
