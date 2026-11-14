"""Unit tests for Region, Dataset, Layer, and Terrain APIs (T-API-03, T-API-04, T-API-05).

Implements testing requirements from docs/TESTING_STRATEGY.md and WP-08 card:
- Region endpoints: list regions, region detail, unknown region 404 envelope
- Dataset endpoints: list datasets, get dataset (available & unavailable with reason preserved)
- Layer endpoints: list layers, PNG overlay render, GeoJSON features, 404 & 400 errors
- Terrain endpoints: point inspection (valid, nodata/UNKNOWN, outside region), profile
- Schema validation against frozen models
- Assertion that every response preserves limitations and availability status
- Synthetic fixture testing without requiring large real datasets
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pyproj
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.core.errors import ErrorEnvelope
from app.main import app
from app.models.datasets import DatasetRecord, LayerInfo
from app.models.enums import DataClass, DatasetStatus, ValueStatus
from app.models.regions import RegionDetail, RegionSummary
from app.models.terrain import PointInspection, ProfileResponse
from app.services import terrain_service
from app.utils.coordinates import MARS_SPHERE_WKT

client = TestClient(app)


# --- 1. Region Endpoints (T-API-03) ---


def test_list_regions_success() -> None:
    """GET /api/v1/regions returns 200 and validates against RegionSummary schema."""
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Validate schema of every item
    summaries = [RegionSummary.model_validate(item) for item in data]
    gale = next((r for r in summaries if r.region_id == "gale_mount_sharp"), None)
    assert gale is not None
    assert gale.name == "Gale Crater / Mount Sharp"
    assert gale.bounds.lat_min < gale.bounds.lat_max
    assert gale.bounds.lon_min < gale.bounds.lon_max


def test_get_region_detail_success() -> None:
    """GET /api/v1/regions/{id} returns 200 and validates against RegionDetail schema."""
    response = client.get("/api/v1/regions/gale_mount_sharp")
    assert response.status_code == 200
    detail = RegionDetail.model_validate(response.json())

    assert detail.region_id == "gale_mount_sharp"
    assert detail.analysis.primary_dtm_dataset_id == "HIRISE_DTM_GALE_MOUND"
    assert len(detail.layer_ids) >= 9
    assert detail.data_status.datasets_available == 3
    assert detail.data_status.datasets_unavailable == 5
    assert len(detail.science_targets) >= 1
    assert detail.science_targets[0].data_class == DataClass.ASSUMPTION
    assert detail.science_targets[0].evidence[0].source_id == "DEMO_WAYPOINT"


def test_get_region_unknown_404() -> None:
    """GET /api/v1/regions/{unknown} returns 404 in standard ErrorEnvelope."""
    response = client.get("/api/v1/regions/nonexistent_region")
    assert response.status_code == 404
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "REGION_NOT_FOUND"
    assert "nonexistent_region" in env.message
    assert env.request_id.startswith("req_")


# --- 2. Dataset Endpoints (T-API-03) ---


def test_list_datasets_success() -> None:
    """GET /api/v1/datasets returns 200 and validates against DatasetRecord schema."""
    response = client.get("/api/v1/datasets?region_id=gale_mount_sharp")
    assert response.status_code == 200
    records = [DatasetRecord.model_validate(d) for d in response.json()]
    assert len(records) == 8

    # Ensure both available and unavailable are returned
    avail = [d for d in records if d.status == DatasetStatus.AVAILABLE]
    unavail = [d for d in records if d.status == DatasetStatus.UNAVAILABLE]
    assert len(avail) == 3
    assert len(unavail) == 5

    # Every unavailable dataset MUST have a documented status_reason
    for ds in unavail:
        assert ds.status_reason is not None and len(ds.status_reason.strip()) > 0


def test_list_datasets_unknown_region_404() -> None:
    """GET /api/v1/datasets?region_id=unknown returns 404 ErrorEnvelope."""
    response = client.get("/api/v1/datasets?region_id=unknown_region")
    assert response.status_code == 404
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "REGION_NOT_FOUND"


def test_get_dataset_available_success() -> None:
    """GET /api/v1/datasets/{id} returns available dataset with limitations and citation."""
    response = client.get("/api/v1/datasets/HIRISE_DTM_GALE_MOUND")
    assert response.status_code == 200
    ds = DatasetRecord.model_validate(response.json())
    assert ds.dataset_id == "HIRISE_DTM_GALE_MOUND"
    assert ds.status == DatasetStatus.AVAILABLE
    assert len(ds.limitations) >= 1
    assert ds.citation != ""


def test_get_dataset_unavailable_preserves_reason() -> None:
    """GET /api/v1/datasets/{id} for unavailable dataset returns real reason, not empty."""
    response = client.get("/api/v1/datasets/USGS_GALE_MERGED_DEM")
    assert response.status_code == 200
    ds = DatasetRecord.model_validate(response.json())
    assert ds.dataset_id == "USGS_GALE_MERGED_DEM"
    assert ds.status == DatasetStatus.UNAVAILABLE
    assert ds.status_reason == "Not selected for download in scope A (core only)"


def test_get_dataset_unknown_404() -> None:
    """GET /api/v1/datasets/{unknown} returns 404 ErrorEnvelope."""
    response = client.get("/api/v1/datasets/UNKNOWN_DATASET_XYZ")
    assert response.status_code == 404
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "DATASET_NOT_FOUND"


# --- 3. Layer Endpoints (T-API-04) ---


def test_list_layers_success() -> None:
    """GET /api/v1/layers returns 200 and validates against LayerInfo schema."""
    response = client.get("/api/v1/layers?region_id=gale_mount_sharp")
    assert response.status_code == 200
    layers = [LayerInfo.model_validate(item) for item in response.json()]
    assert len(layers) >= 10

    layer_ids = {layer.layer_id for layer in layers}
    expected = {
        "elevation",
        "ortho",
        "mola_elevation",
        "slope",
        "roughness",
        "hazard_grid",
        "hazard_near",
        "hillshade",
        "confidence",
        "science_targets",
    }
    assert expected.issubset(layer_ids)

    # Check legend on slope
    slope_l = next(layer for layer in layers if layer.layer_id == "slope")
    assert slope_l.legend is not None
    assert slope_l.legend.colormap == "magma"
    assert slope_l.legend.units == "deg"

    # Check legend on hazard_grid
    haz_l = next(layer for layer in layers if layer.layer_id == "hazard_grid")
    assert haz_l.legend is not None
    assert haz_l.legend.colormap == "categorical"
    assert len(haz_l.legend.categories) == 4


def test_list_layers_unknown_region_404() -> None:
    """GET /api/v1/layers?region_id=unknown returns 404 ErrorEnvelope."""
    response = client.get("/api/v1/layers?region_id=unknown_region")
    assert response.status_code == 404
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "REGION_NOT_FOUND"


def test_get_layer_features_vector_success() -> None:
    """GET /api/v1/layers/{id}/features returns GeoJSON FeatureCollection for vector layer."""
    response = client.get("/api/v1/layers/science_targets/features?region_id=gale_mount_sharp")
    assert response.status_code == 200
    data = response.json()
    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) >= 1
    assert features[0]["geometry"]["type"] == "Point"
    assert features[0]["properties"]["target_id"] == "TARGET_01"


def test_get_layer_features_raster_error() -> None:
    """GET /api/v1/layers/{raster_id}/features returns 400 INVALID_LAYER_KIND."""
    response = client.get("/api/v1/layers/slope/features?region_id=gale_mount_sharp")
    assert response.status_code == 400
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "INVALID_LAYER_KIND"


def test_get_layer_image_raster_success() -> None:
    """GET /api/v1/layers/{id}/image returns 200 with image/png and valid PNG header."""
    response = client.get("/api/v1/layers/slope/image?region_id=gale_mount_sharp")
    assert response.status_code == 200
    assert response.headers.get("content-type") == "image/png"
    # Check PNG magic bytes
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_get_layer_image_unknown_404() -> None:
    """GET /api/v1/layers/{unknown}/image returns 404 LAYER_NOT_FOUND."""
    response = client.get("/api/v1/layers/unknown_layer/image?region_id=gale_mount_sharp")
    assert response.status_code == 404
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "LAYER_NOT_FOUND"


# --- 4. Terrain Point and Profile Endpoints (T-API-05) ---


def test_terrain_point_success() -> None:
    """GET /api/v1/terrain/point returns 200 and validates against PointInspection."""
    # Point at default base (-4.75, 137.28)
    response = client.get("/api/v1/terrain/point?region_id=gale_mount_sharp&lat=-4.75&lon=137.28")
    assert response.status_code == 200
    insp = PointInspection.model_validate(response.json())

    assert insp.region_id == "gale_mount_sharp"
    assert np.isclose(insp.point.lat, -4.75)
    assert np.isclose(insp.point.lon, 137.28)

    # Elevation value present
    elev_val = next((v for v in insp.values if v.layer_id == "elevation"), None)
    assert elev_val is not None
    assert elev_val.status == ValueStatus.OK
    assert isinstance(elev_val.value, float)
    assert elev_val.units == "m"

    # Context indicators present
    rad = next((c for c in insp.context if c.indicator_id == "RADIATION_CONTEXT"), None)
    assert rad is not None
    assert rad.status == "UNAVAILABLE"
    assert len(rad.limitations) >= 1

    # Overall limitations present
    assert len(insp.limitations) >= 4


def test_terrain_point_nodata_is_unknown() -> None:
    """Point outside DTM raster coverage returns ValueStatus.NO_COVERAGE and None, never 0."""
    # Lat -4.2, Lon 137.2 is inside gale_mount_sharp region bounds but outside HiRISE DTM footprint
    response = client.get("/api/v1/terrain/point?region_id=gale_mount_sharp&lat=-4.2&lon=137.2")
    assert response.status_code == 200
    insp = PointInspection.model_validate(response.json())

    elev_val = next((v for v in insp.values if v.layer_id == "elevation"), None)
    assert elev_val is not None
    assert elev_val.status == ValueStatus.NO_COVERAGE
    assert elev_val.value is None


def test_terrain_point_outside_region_422() -> None:
    """Coordinates outside region bounds return 422 POINT_OUTSIDE_REGION per API_CONTRACTS."""
    response = client.get("/api/v1/terrain/point?region_id=gale_mount_sharp&lat=20.0&lon=50.0")
    assert response.status_code == 422
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "POINT_OUTSIDE_REGION"


def test_terrain_point_invalid_coordinates_422() -> None:
    """Latitude > 90 deg returns 422 VALIDATION_ERROR."""
    response = client.get("/api/v1/terrain/point?region_id=gale_mount_sharp&lat=120.0&lon=137.28")
    assert response.status_code == 422
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "VALIDATION_ERROR"


def test_terrain_profile_success() -> None:
    """POST /api/v1/terrain/profile returns 200 and validates against ProfileResponse."""
    req_body = {
        "region_id": "gale_mount_sharp",
        "points": [
            {"lat": -4.75, "lon": 137.28},
            {"lat": -4.76, "lon": 137.29},
        ],
        "sample_spacing_m": 100.0,
    }
    response = client.post("/api/v1/terrain/profile", json=req_body)
    assert response.status_code == 200
    prof = ProfileResponse.model_validate(response.json())

    assert len(prof.samples) >= 5
    assert prof.total_horizontal_distance_m > 0.0
    assert prof.samples[0].distance_m == 0.0
    assert prof.samples[0].elevation_m is not None
    assert prof.samples[0].slope_deg is not None
    assert len(prof.evidence) >= 1
    assert len(prof.limitations) >= 1


def test_terrain_profile_outside_region_422() -> None:
    """Profile request with vertex outside region returns 422 POINT_OUTSIDE_REGION."""
    req_body = {
        "region_id": "gale_mount_sharp",
        "points": [
            {"lat": -4.75, "lon": 137.28},
            {"lat": 50.0, "lon": 10.0},
        ],
    }
    response = client.post("/api/v1/terrain/profile", json=req_body)
    assert response.status_code == 422
    env = ErrorEnvelope.model_validate(response.json())
    assert env.error_code == "POINT_OUTSIDE_REGION"


# --- 5. Mandatory Omission Assertion & Synthetic Isolation ---


def test_response_omits_limitation_or_status_fails() -> None:
    """Fails if any dataset or inspection response omits limitations or operational status."""
    # 1. Check all catalog datasets
    cat_resp = client.get("/api/v1/datasets?region_id=gale_mount_sharp")
    for ds in cat_resp.json():
        assert "limitations" in ds and len(ds["limitations"]) > 0, (
            f"{ds['dataset_id']} missing limitations"
        )
        assert "status" in ds and ds["status"] in ("AVAILABLE", "PARTIAL", "UNAVAILABLE"), (
            f"{ds['dataset_id']} missing status"
        )

    # 2. Check point inspection limitations
    pt_resp = client.get("/api/v1/terrain/point?region_id=gale_mount_sharp&lat=-4.75&lon=137.28")
    pt_data = pt_resp.json()
    assert "limitations" in pt_data and len(pt_data["limitations"]) >= 1, (
        "Point inspection missing limitations"
    )


def test_layers_non_measured_have_limitations() -> None:
    """Fails if any non-measured/derived layer in GET /api/v1/layers has empty limitations."""
    response = client.get("/api/v1/layers?region_id=gale_mount_sharp")
    assert response.status_code == 200
    layers = [LayerInfo.model_validate(item) for item in response.json()]
    for layer in layers:
        if layer.data_class not in (DataClass.MEASURED, DataClass.DERIVED) or not layer.dataset_ids:
            assert len(layer.limitations) > 0, (
                f"Layer {layer.layer_id} ({layer.data_class}) must have non-empty limitations"
            )


def test_science_targets_provenance_guard() -> None:
    """Fails if science_targets claims a literature source that manifests do not define."""
    response = client.get("/api/v1/regions/gale_mount_sharp")
    assert response.status_code == 200
    detail = RegionDetail.model_validate(response.json())

    # Load defined manifest dataset IDs
    manifest_dir = Path(__file__).resolve().parents[3] / "data" / "manifests"
    defined_ids: set[str] = set()
    cat_file = manifest_dir / "dataset_catalog.json"
    if cat_file.exists():
        cat = json.loads(cat_file.read_text(encoding="utf-8"))
        defined_ids.update(ds["dataset_id"] for ds in cat.get("datasets", []))

    for target in detail.science_targets:
        # Waypoint coordinates are unverified demo assumptions
        assert target.data_class == DataClass.ASSUMPTION, (
            f"Target {target.target_id} must be ASSUMPTION as coordinates lack verified citation"
        )
        for ev in target.evidence:
            if ev.source_type in ("dataset", "reference"):
                assert ev.source_id in defined_ids, (
                    f"Evidence source_id '{ev.source_id}' is not defined in dataset manifests"
                )


def test_synthetic_fixture_service_isolation() -> None:
    """Pure synthetic fixture test: verifies terrain service logic without real rasters."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        proc_dir = tmp_path / "processed"
        proc_dir.mkdir(parents=True)
        reg_dir = tmp_path / "regions"
        reg_dir.mkdir(parents=True)
        man_dir = tmp_path / "manifests"
        man_dir.mkdir(parents=True)

        # Write synthetic region
        region_json = {
            "region_id": "synthetic_region",
            "name": "Synthetic Test Region",
            "description": "Synthetic testing region",
            "science_objective": "Test isolation",
            "bounds": {"lat_min": -1.0, "lat_max": 1.0, "lon_min": 0.0, "lon_max": 2.0},
            "analysis": {
                "primary_dtm_dataset_id": "SYNTH_DTM",
                "analysis_crs": "+proj=eqc +lat_ts=0 +lon_0=0 +units=m",
                "cell_size_m": 10.0,
                "max_grid_cells": 1000,
            },
            "layers": [{"layer_id": "elevation"}],
            "science_targets": [],
        }
        (reg_dir / "synthetic_region.json").write_text(json.dumps(region_json), encoding="utf-8")
        (man_dir / "dataset_catalog.json").write_text(
            json.dumps({"datasets": []}), encoding="utf-8"
        )

        # Create small 10x10 GeoTIFF raster in equirectangular projection
        elev_data = np.full((10, 10), 123.45, dtype=np.float32)
        transform = from_origin(0.0, 100.0, 10.0, 10.0)
        crs = "EPSG:32630"  # Arbitrary projected

        with rasterio.open(
            proc_dir / "HIRISE_DTM_GALE_MOUND.tif",
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(elev_data, 1)

        # Verify point inspection with synthetic data dir
        pt = terrain_service.inspect_point("synthetic_region", 0.0, 1.0, data_dir=tmp_path)
        assert pt.region_id == "synthetic_region"
        assert len(pt.limitations) >= 1


def test_affine_col_row_mapping_regression() -> None:
    """Regression test for Affine inverse transform column/row coordinate unpacking.

    Verifies that ~src.transform @ (x, y) correctly unpacks as (col_f, row_f) and not
    (row_f, col_f), preventing asymmetric coordinate inversion bugs during raster sampling.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        raster_path = tmp_path / "asymmetric_grid.tif"

        # Asymmetric dimensions: height=4 rows, width=8 cols
        height = 4
        width = 8
        # Each cell has a distinct unique value: 1000 * row + col
        data = np.zeros((height, width), dtype=np.float32)
        for r in range(height):
            for c in range(width):
                data[r, c] = 1000.0 * r + c

        # Equirectangular Mars CRS (D-013)
        mars_crs = (
            "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
        )
        # Asymmetric pixel size: dx=10.0m, dy=25.0m; origin at west=100.0, north=500.0
        dx = 10.0
        dy = 25.0
        west = 100.0
        north = 500.0
        transform = from_origin(west, north, dx, dy)

        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=mars_crs,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        # Interior point of known pixel: row=1, col=5 (distinct value: 1005.0)
        # Note: if row and col were swapped, row=5 would be outside raster bounds (height=4)!
        target_row = 1
        target_col = 5
        expected_val = 1000.0 * target_row + target_col  # 1005.0

        # Interior point coordinates in projected space
        # (offset 0.3 to avoid round-half-to-even on edges)
        x_proj = west + (target_col + 0.3) * dx  # 100 + 5.3 * 10 = 153.0
        y_proj = north - (target_row + 0.3) * dy  # 500 - 1.3 * 25 = 467.5

        # 1. Assert direct affine inverse transform unpacking order
        inv_transform = ~transform
        col_f, row_f = inv_transform @ (x_proj, y_proj)
        assert col_f == pytest.approx(target_col + 0.3)
        assert row_f == pytest.approx(target_row + 0.3)

        # Inversion trap check: verify col_f != row_f
        assert col_f != row_f
        assert row_f < height
        assert col_f < width

        # 2. Transform projected (x_proj, y_proj) back to geographical (lon, lat) on Mars sphere
        to_geo = pyproj.Transformer.from_crs(mars_crs, MARS_SPHERE_WKT, always_xy=True)
        target_lon, target_lat = to_geo.transform(x_proj, y_proj)

        # 3. Assert sampling via terrain_service internal sampling helpers
        to_proj = pyproj.Transformer.from_crs(MARS_SPHERE_WKT, mars_crs, always_xy=True)
        with rasterio.open(raster_path) as src:
            # Nearest sampling at pixel interior must return exact cell value 1005.0
            val_nearest = terrain_service._sample_nearest_raster(
                src, to_proj, target_lon, target_lat
            )
            assert val_nearest == expected_val

            # Bilinear sampling at integer corner: row=1, col=5 exactly
            x_corner = west + target_col * dx  # 150.0
            y_corner = north - target_row * dy  # 475.0
            corner_lon, corner_lat = to_geo.transform(x_corner, y_corner)
            val_bilinear = terrain_service._sample_continuous_raster(
                src, to_proj, corner_lon, corner_lat
            )
            assert val_bilinear == pytest.approx(expected_val)


def test_synthetic_raster_bounds_are_cached(tmp_path: Path) -> None:
    """Raster footprints are computed once per file version, not once per request.

    The synthetic raster is a tiny geographic GeoTIFF built in a tmp path; it only
    exercises the cache, not any real Mars data.
    """
    import numpy as np
    import pytest
    import rasterio
    from rasterio.transform import from_origin

    from app.services import layer_service as ls

    path = tmp_path / "synthetic_bounds.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(137.0, -4.0, 0.01, 0.01),
    ) as dst:
        dst.write(np.zeros((4, 4), dtype="float32"), 1)

    ls._compute_raster_bounds.cache_clear()
    first = ls._get_raster_bounds(path)
    second = ls._get_raster_bounds(path)
    info = ls._compute_raster_bounds.cache_info()

    assert info.misses == 1
    assert info.hits == 1
    assert first == second
    assert first is not None
    assert first.lon_min == pytest.approx(137.0)
    assert first.lon_max == pytest.approx(137.04)
    assert first.lat_max == pytest.approx(-4.0)
    assert first.lat_min == pytest.approx(-4.04)
