"""Unit tests for the data ingestion and processing pipeline (T-DATA-01 to T-DATA-08).

All fixtures are synthetic code-generated samples, clearly labelled SYNTHETIC.
No binary data or real raw rasters are committed.
"""

import hashlib
import math
from pathlib import Path
from unittest.mock import MagicMock

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
from app.models.geometry import GeoBounds
from app.utils.coordinates import (
    MARS_ELLIPSOID_WKT,
    MARS_EQUATORIAL_RADIUS_M,
    MARS_POLAR_RADIUS_M,
    MARS_SPHERE_WKT,
    planetographic_to_planetocentric,
)
from scripts.download_data import compute_file_sha256, probe_dataset


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

    # 2. Non-Mars CRS (e.g. Earth WGS84)
    earth_crs = "+proj=longlat +datum=WGS84 +no_defs"
    with pytest.raises(CRSValidationError, match="does not match Mars radius"):
        inspect_raster_crs(earth_crs)

    # 3. Valid Mars sphere equirectangular CRS -> PLANETOCENTRIC by construction
    valid_mars_eqc = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +x_0=0 +y_0=0 +R=3396190 +units=m"
    res_sphere_eqc = inspect_raster_crs(valid_mars_eqc)
    assert res_sphere_eqc["is_valid"] is True
    assert res_sphere_eqc["datum_type"] == "SPHERE"
    assert res_sphere_eqc["latitude_type"] == "PLANETOCENTRIC"
    assert res_sphere_eqc["is_projected"] is True

    # 4. Valid Mars sphere geographic WKT -> PLANETOCENTRIC by construction
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
    synthetic_payload = b"MARSWALK_SYNTHETIC_DATA_PAYLOAD_TEST_T_DATA_05"
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
