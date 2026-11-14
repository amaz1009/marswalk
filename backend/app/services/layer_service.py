"""Layer service for map visualization, raster PNG rendering, and GeoJSON features.

Implements business logic for:
- GET /api/v1/layers
- GET /api/v1/layers/{layer_id}/image
- GET /api/v1/layers/{layer_id}/features
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile

from app.core.errors import AppException
from app.data.footprint import compute_raster_footprint
from app.data.loaders import get_default_data_dir
from app.models.datasets import LayerInfo, Legend, LegendCategory
from app.models.enums import DataClass, DatasetStatus, DataType, LayerKind
from app.models.geometry import GeoBounds
from app.services.region_service import get_region_raw, validate_identifier
from app.utils.coordinates import MARS_SPHERE_WKT

# Pre-defined layer definitions and rendering styles
LAYER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "elevation": {
        "name": "Surface Elevation",
        "kind": LayerKind.RASTER,
        "data_type": DataType.ELEVATION,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HIRISE_DTM_GALE_MOUND.tif",
        "native_resolution_m": 1.011747,
        "legend": Legend(colormap="terrain", vmin=-4500.0, vmax=-2900.0, units="m"),
        "limitations": [
            "Vertical datum is UNVERIFIED; do not mix directly with MOLA elevations",
            "Stereo-derived DEM contains interpolation artifacts in low-contrast dust areas",
        ],
    },
    "ortho": {
        "name": "HiRISE Optical Basemap",
        "kind": LayerKind.RASTER,
        "data_type": DataType.OPTICAL,
        "data_class": DataClass.MEASURED,
        "dataset_ids": ["HIRISE_ORTHO_GALE_MOUND"],
        "raster_filename": "HIRISE_ORTHO_GALE_MOUND.tif",
        "native_resolution_m": 1.011747,
        "legend": Legend(colormap="gray", units=None),
        "limitations": [
            "Single-band RED channel; no multispectral infrared or true color",
        ],
    },
    "mola_elevation": {
        "name": "Regional MOLA Elevation",
        "kind": LayerKind.RASTER,
        "data_type": DataType.ELEVATION,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["MOLA_MEGDR_GALE"],
        "raster_filename": "MOLA_MEGDR_GALE.tif",
        "native_resolution_m": 463.0,
        "legend": Legend(colormap="terrain", vmin=-5000.0, vmax=0.0, units="m"),
        "limitations": [
            "Coarse regional resolution (128 pixels/degree ~ 463 m); regional context only",
            "Grid georeference may have offset of up to one pixel (~463 m)",
        ],
    },
    "slope": {
        "name": "Terrain Slope",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HIRISE_SLOPE_GALE_MOUND.tif",
        "native_resolution_m": 1.011747,
        "legend": Legend(colormap="magma", vmin=0.0, vmax=45.0, units="deg"),
        "limitations": [
            "Derived from 1m HiRISE DTM; ground-scale includes cos(latitude) per Decision D-013",
            "Features smaller than 3x post spacing (~3 m) not reliably resolved",
        ],
    },
    "roughness": {
        "name": "Residual RMS Roughness",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HIRISE_ROUGHNESS_GALE_MOUND.tif",
        "native_resolution_m": 1.011747,
        "legend": Legend(colormap="plasma", vmin=0.0, vmax=0.30, units="m"),
        "limitations": [
            "Residual RMS roughness over 3x3 window in ground metres",
            "Computational proxy for surface obstacles, not an explicit measurement of rocks",
        ],
    },
    "hazard_grid": {
        "name": "Hazard Classification Grid",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HAZARD_GRID_GALE_MOUND.tif",
        "native_resolution_m": 1.0,
        "legend": Legend(
            colormap="categorical",
            categories=[
                LegendCategory(value=0, label="PASSABLE", color="#2ecc71"),
                LegendCategory(value=1, label="IMPASSABLE_NODATA", color="#95a5a6"),
                LegendCategory(value=2, label="IMPASSABLE_SLOPE", color="#e74c3c"),
                LegendCategory(value=3, label="IMPASSABLE_EXCLUSION", color="#8e44ad"),
            ],
        ),
        "limitations": [
            "Impassable slope threshold default is 15.0 degrees per Pena (2023)",
            "Exclusion zones are P2 operator-defined; P0 grid evaluates nodata and slope only",
        ],
    },
    "hazard_near": {
        "name": "NEAR_HAZARD Buffer Flag",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HAZARD_NEAR_GALE_MOUND.tif",
        "native_resolution_m": 1.0,
        "legend": Legend(
            colormap="categorical",
            categories=[
                LegendCategory(value=0, label="CLEAR", color="#00000000"),
                LegendCategory(value=1, label="NEAR_HAZARD", color="#f39c12"),
            ],
        ),
        "limitations": [
            "Flagged when a passable cell is within 1 cell (8-neighbour) of an impassable cell",
        ],
    },
    "hillshade": {
        "name": "Shaded Relief",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
        "raster_filename": "HILLSHADE_GALE_MOUND.tif",
        "native_resolution_m": 1.0,
        "legend": Legend(colormap="gray", units=None),
        "limitations": [
            "Display visual aid illuminated from azimuth 315 deg, altitude 45 deg",
            "Value 0 strictly reserved for nodata",
        ],
    },
    "confidence": {
        "name": "Data Confidence Level",
        "kind": LayerKind.RASTER,
        "data_type": DataType.DERIVED,
        "data_class": DataClass.DERIVED,
        "dataset_ids": [
            "HIRISE_DTM_GALE_MOUND",
            "HIRISE_ORTHO_GALE_MOUND",
        ],
        "raster_filename": "CONFIDENCE_GALE_MOUND.tif",
        "native_resolution_m": 1.0,
        "legend": Legend(
            colormap="categorical",
            categories=[
                LegendCategory(value=0, label="NONE", color="#e74c3c"),
                LegendCategory(value=1, label="LOW", color="#f1c40f"),
                LegendCategory(value=2, label="MEDIUM", color="#3498db"),
                LegendCategory(value=3, label="HIGH", color="#2ecc71"),
            ],
        ),
        "limitations": [
            "Tops out at MEDIUM in Scope A because geology and THEMIS context are unavailable",
        ],
    },
    "science_targets": {
        "name": "Designated Science Targets",
        "kind": LayerKind.VECTOR,
        "data_type": DataType.GEOLOGY,
        "data_class": DataClass.ASSUMPTION,
        "dataset_ids": [],
        "raster_filename": None,
        "native_resolution_m": None,
        "legend": None,
        "limitations": [
            "Demonstration waypoint location is not supported by any cited source",
            (
                "Geological unit classifications and boxwork status are unverified assumptions; "
                "geology datasets are UNAVAILABLE in Scope A"
            ),
        ],
    },
}


def _get_raster_bounds(raster_path: Path) -> GeoBounds | None:
    """Extract the bounding box of a raster, cached per file version.

    Opening the raster and building a pyproj Transformer on every request cost about
    0.7 s for the nine layers. The footprint only changes when the file changes, so the
    cache key includes the file size and modification time.
    """
    try:
        stat = raster_path.stat()
    except OSError:
        return None
    return _compute_raster_bounds(str(raster_path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=64)
def _compute_raster_bounds(path_str: str, mtime_ns: int, size: int) -> GeoBounds | None:
    """Uncached footprint computation; mtime_ns and size only key the cache."""
    raster_path = Path(path_str)
    try:
        import pyproj

        with rasterio.open(raster_path) as src:
            if src.crs.is_geographic:
                return GeoBounds(
                    lat_min=float(src.bounds.bottom),
                    lat_max=float(src.bounds.top),
                    lon_min=float(src.bounds.left),
                    lon_max=float(src.bounds.right),
                )
            transformer = pyproj.Transformer.from_crs(src.crs, MARS_SPHERE_WKT, always_xy=True)
            return compute_raster_footprint(
                src.bounds.left,
                src.bounds.right,
                src.bounds.bottom,
                src.bounds.top,
                is_projected=True,
                transform_to_latlon=transformer.transform,
            )
    except Exception:
        return None


def list_layers(region_id: str | None = None, data_dir: Path | None = None) -> list[LayerInfo]:
    """List all available map layers for a region."""
    base_dir = data_dir or get_default_data_dir()
    effective_region = region_id or "gale_mount_sharp"
    validate_identifier(effective_region, name="region_id")
    raw_region = get_region_raw(effective_region, data_dir=base_dir)

    processed_dir = base_dir / "processed"
    layers_out: list[LayerInfo] = []

    for lid, spec in LAYER_DEFINITIONS.items():
        is_raster = spec["kind"] == LayerKind.RASTER
        raster_file = processed_dir / spec["raster_filename"] if spec["raster_filename"] else None

        if is_raster:
            if raster_file and raster_file.exists():
                status = DatasetStatus.AVAILABLE
                status_reason = None
                bounds = _get_raster_bounds(raster_file)
            else:
                status = DatasetStatus.UNAVAILABLE
                status_reason = f"Processed raster '{spec['raster_filename']}' not found on disk"
                bounds = GeoBounds(**raw_region["bounds"])
            image_url = f"/api/v1/layers/{lid}/image?region_id={effective_region}"
            features_url = None
        else:
            status = DatasetStatus.AVAILABLE
            status_reason = None
            bounds = GeoBounds(**raw_region["bounds"])
            image_url = None
            features_url = f"/api/v1/layers/{lid}/features?region_id={effective_region}"

        layer = LayerInfo(
            layer_id=lid,
            name=spec["name"],
            kind=spec["kind"],
            data_type=spec["data_type"],
            status=status,
            status_reason=status_reason,
            dataset_ids=spec["dataset_ids"],
            data_class=spec["data_class"],
            bounds=bounds,
            native_resolution_m=spec["native_resolution_m"],
            legend=spec["legend"],
            image_url=image_url,
            features_url=features_url,
            limitations=spec["limitations"],
        )
        layers_out.append(layer)

    return layers_out


def get_layer_info(
    layer_id: str, region_id: str | None = None, data_dir: Path | None = None
) -> LayerInfo:
    """Retrieve metadata manifest for a specific layer."""
    validate_identifier(layer_id, name="layer_id")
    layers = list_layers(region_id=region_id, data_dir=data_dir)
    for layer in layers:
        if layer.layer_id == layer_id:
            return layer

    raise AppException(
        error_code="LAYER_NOT_FOUND",
        message=f"Layer '{layer_id}' not found",
        status_code=404,
        details={"layer_id": layer_id},
    )


def _apply_palette(
    values: np.ndarray,
    vmin: float,
    vmax: float,
    palette: list[tuple[float, tuple[int, int, int]]],
) -> np.ndarray:
    """Interpolate RGB color values from a continuous color palette."""
    norm = np.clip((values - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0)
    h, w = values.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for idx in range(len(palette) - 1):
        t0, c0 = palette[idx]
        t1, c1 = palette[idx + 1]
        mask = (
            (norm >= t0) & (norm <= t1) if idx == len(palette) - 2 else (norm >= t0) & (norm < t1)
        )
        if not np.any(mask):
            continue
        frac = (norm[mask] - t0) / (t1 - t0)
        for ch in range(3):
            rgb[mask, ch] = np.clip(c0[ch] + frac * (c1[ch] - c0[ch]), 0, 255).astype(np.uint8)
    return rgb


def render_layer_png(
    layer_id: str,
    region_id: str | None = None,
    data_dir: Path | None = None,
    target_width: int = 1024,
) -> bytes:
    """Render a raster layer as a downsampled transparent PNG image overlay.

    Checks disk cache in data/renders/ first. Uses windowed/decimated rasterio
    reads to keep memory usage bounded (< 15 MB) for large source rasters.
    """
    layer = get_layer_info(layer_id, region_id=region_id, data_dir=data_dir)
    if layer.kind != LayerKind.RASTER:
        raise AppException(
            error_code="INVALID_LAYER_KIND",
            message=f"Layer '{layer_id}' is a vector layer; use the /features endpoint",
            status_code=400,
            details={"layer_id": layer_id},
        )

    base_dir = data_dir or get_default_data_dir()
    effective_region = region_id or "gale_mount_sharp"
    spec = LAYER_DEFINITIONS[layer_id]
    raster_filename = spec["raster_filename"]
    raster_path = base_dir / "processed" / raster_filename

    if not raster_path.exists():
        raise AppException(
            error_code="LAYER_UNAVAILABLE",
            message=f"Layer '{layer_id}' data raster is unavailable on disk",
            status_code=400,
            details={"layer_id": layer_id, "file": raster_filename},
        )

    renders_dir = base_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    cache_path = renders_dir / f"{effective_region}_{layer_id}.png"

    # Serve from cache if valid and up-to-date
    if cache_path.exists() and cache_path.stat().st_mtime >= raster_path.stat().st_mtime:
        return cache_path.read_bytes()

    with rasterio.open(raster_path) as src:
        scale = min(1.0, target_width / src.width)
        out_w = int(src.width * scale)
        out_h = int(src.height * scale)

        is_categorical = layer_id in ("hazard_grid", "hazard_near", "confidence", "hillshade")
        resample_method = Resampling.nearest if is_categorical else Resampling.bilinear

        data = src.read(1, out_shape=(out_h, out_w), resampling=resample_method)

        rgba = np.zeros((out_h, out_w, 4), dtype=np.uint8)

        if layer_id == "elevation" or layer_id == "mola_elevation":
            valid = ~np.isnan(data)
            vmin, vmax = (spec["legend"].vmin or -4500.0), (spec["legend"].vmax or -2900.0)
            terrain_palette = [
                (0.0, (46, 117, 182)),
                (0.3, (94, 186, 125)),
                (0.6, (230, 204, 140)),
                (0.85, (170, 100, 50)),
                (1.0, (250, 250, 250)),
            ]
            rgb = _apply_palette(data, vmin, vmax, terrain_palette)
            rgba[valid, :3] = rgb[valid]
            rgba[valid, 3] = 220

        elif layer_id == "ortho":
            valid = data > 0
            rgba[valid, 0] = data[valid]
            rgba[valid, 1] = data[valid]
            rgba[valid, 2] = data[valid]
            rgba[valid, 3] = 255

        elif layer_id == "slope":
            valid = ~np.isnan(data)
            magma_palette = [
                (0.0, (0, 0, 4)),
                (0.25, (81, 18, 124)),
                (0.5, (182, 54, 121)),
                (0.75, (251, 136, 97)),
                (1.0, (252, 253, 191)),
            ]
            rgb = _apply_palette(data, 0.0, 45.0, magma_palette)
            rgba[valid, :3] = rgb[valid]
            rgba[valid, 3] = 220

        elif layer_id == "roughness":
            valid = ~np.isnan(data)
            plasma_palette = [
                (0.0, (13, 8, 135)),
                (0.25, (126, 3, 168)),
                (0.5, (204, 71, 120)),
                (0.75, (248, 149, 64)),
                (1.0, (240, 249, 33)),
            ]
            rgb = _apply_palette(data, 0.0, 0.30, plasma_palette)
            rgba[valid, :3] = rgb[valid]
            rgba[valid, 3] = 220

        elif layer_id == "hazard_grid":
            # 0: PASSABLE (green), 1: IMPASSABLE_NODATA (gray),
            # 2: IMPASSABLE_SLOPE (red), 3: IMPASSABLE_EXCLUSION (purple)
            m0 = data == 0
            rgba[m0] = [46, 204, 113, 180]
            m1 = data == 1
            rgba[m1] = [149, 165, 166, 180]
            m2 = data == 2
            rgba[m2] = [231, 76, 60, 210]
            m3 = data == 3
            rgba[m3] = [142, 68, 173, 210]

        elif layer_id == "hazard_near":
            # 0: Clear (transparent), 1: Near hazard (orange)
            m1 = data == 1
            rgba[m1] = [243, 156, 18, 220]

        elif layer_id == "hillshade":
            # 0: Nodata (transparent), 1..255: shaded relief
            valid = data > 0
            rgba[valid, 0] = data[valid]
            rgba[valid, 1] = data[valid]
            rgba[valid, 2] = data[valid]
            rgba[valid, 3] = 255

        elif layer_id == "confidence":
            # 0: NONE (red), 1: LOW (yellow), 2: MEDIUM (blue), 3: HIGH (green)
            m0 = data == 0
            rgba[m0] = [231, 76, 60, 180]
            m1 = data == 1
            rgba[m1] = [241, 196, 15, 180]
            m2 = data == 2
            rgba[m2] = [52, 152, 219, 180]
            m3 = data == 3
            rgba[m3] = [46, 204, 113, 180]

        # Write to PNG via rasterio MemoryFile
        with MemoryFile() as memfile:
            with memfile.open(
                driver="PNG",
                height=out_h,
                width=out_w,
                count=4,
                dtype="uint8",
            ) as dst:
                for b_idx in range(4):
                    dst.write(rgba[:, :, b_idx], b_idx + 1)
            png_bytes = memfile.read()

    # Cache output
    cache_path.write_bytes(png_bytes)
    return png_bytes


def get_layer_features(
    layer_id: str, region_id: str | None = None, data_dir: Path | None = None
) -> dict[str, Any]:
    """Retrieve GeoJSON FeatureCollection for a vector layer."""
    layer = get_layer_info(layer_id, region_id=region_id, data_dir=data_dir)
    if layer.kind != LayerKind.VECTOR:
        raise AppException(
            error_code="INVALID_LAYER_KIND",
            message=f"Layer '{layer_id}' is a raster layer; use the /image endpoint",
            status_code=400,
            details={"layer_id": layer_id},
        )

    base_dir = data_dir or get_default_data_dir()
    effective_region = region_id or "gale_mount_sharp"
    raw_region = get_region_raw(effective_region, data_dir=base_dir)

    features: list[dict[str, Any]] = []
    if layer_id == "science_targets":
        for target in raw_region.get("science_targets", []):
            pt = target.get("point", {})
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(pt.get("lon", 0.0)), float(pt.get("lat", 0.0))],
                    },
                    "properties": {
                        "target_id": target.get("target_id"),
                        "name": target.get("name"),
                        "rationale": target.get("rationale"),
                        "data_class": target.get("data_class"),
                        "dataset_ids": ["HIRISE_DTM_GALE_MOUND"],
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "features": features,
    }
