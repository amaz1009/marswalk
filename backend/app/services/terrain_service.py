"""Terrain sampling and cross-section profile service.

Implements business logic for:
- GET /api/v1/terrain/point
- POST /api/v1/terrain/profile
"""

import math
from pathlib import Path
from typing import Any

import pyproj
import rasterio

from app.core.errors import AppException
from app.data.loaders import get_default_data_dir
from app.engines.terrain.profile import interpolate_great_circle_points
from app.engines.terrain.sampling import sample_bilinear
from app.models.enums import (
    ConfidenceLevel,
    ContextIndicatorId,
    ContextStatus,
    DataClass,
    ValueStatus,
)
from app.models.evidence import EvidenceRef
from app.models.geometry import GeoBounds, GeoPoint
from app.models.terrain import (
    ContextIndicator,
    LayerValue,
    PointInspection,
    ProfilePoint,
    ProfileRequest,
    ProfileResponse,
)
from app.services.layer_service import LAYER_DEFINITIONS
from app.services.region_service import get_region_raw
from app.utils.coordinates import MARS_SPHERE_WKT, normalize_longitude, validate_latitude


def _sample_continuous_raster(
    src: rasterio.io.DatasetReader,
    transformer: pyproj.Transformer,
    lon: float,
    lat: float,
) -> float | None:
    """Sample continuous raster at (lon, lat) using windowed 2x2 bilinear read."""
    x, y = transformer.transform(lon, lat)
    col_f, row_f = ~src.transform @ (x, y)

    # Check bounds (needs 2x2 neighborhood)
    if row_f < 0 or row_f > src.height - 2 or col_f < 0 or col_f > src.width - 2:
        return None

    r_int = int(math.floor(row_f))
    c_int = int(math.floor(col_f))

    win = rasterio.windows.Window(c_int, r_int, 2, 2)
    block = src.read(1, window=win)

    val = sample_bilinear(block, row_f - r_int, col_f - c_int)
    if math.isnan(val):
        return None
    return float(val)


def _sample_nearest_raster(
    src: rasterio.io.DatasetReader,
    transformer: pyproj.Transformer,
    lon: float,
    lat: float,
) -> Any | None:
    """Sample categorical raster at (lon, lat) using windowed 1x1 read."""
    x, y = transformer.transform(lon, lat)
    col_f, row_f = ~src.transform @ (x, y)

    r = int(round(row_f))
    c = int(round(col_f))

    if r < 0 or r >= src.height or c < 0 or c >= src.width:
        return None

    win = rasterio.windows.Window(c, r, 1, 1)
    block = src.read(1, window=win)
    return block[0, 0]


def inspect_point(
    region_id: str,
    lat: float,
    lon: float,
    data_dir: Path | None = None,
) -> PointInspection:
    """Inspect terrain, hazard, and contextual layers at a coordinate."""
    validate_latitude(lat)
    norm_lon = normalize_longitude(lon)

    base_dir = data_dir or get_default_data_dir()
    raw_region = get_region_raw(region_id, data_dir=base_dir)
    bounds = GeoBounds(**raw_region["bounds"])

    # Strict region bounds check
    if not (
        bounds.lat_min <= lat <= bounds.lat_max and bounds.lon_min <= norm_lon <= bounds.lon_max
    ):
        raise AppException(
            error_code="POINT_OUTSIDE_REGION",
            message=f"Coordinate ({lat}, {norm_lon}) lies outside region '{region_id}' bounds",
            status_code=422,
            details={"region_id": region_id, "lat": lat, "lon": norm_lon},
        )

    processed_dir = base_dir / "processed"
    layer_values: list[LayerValue] = []
    data_confidence_level = ConfidenceLevel.NONE

    for lid, spec in LAYER_DEFINITIONS.items():
        if spec["kind"] != "RASTER" or not spec["raster_filename"]:
            continue

        raster_file = processed_dir / spec["raster_filename"]
        units = spec["legend"].units if spec["legend"] else None

        if not raster_file.exists():
            layer_values.append(
                LayerValue(
                    layer_id=lid,
                    value=None,
                    units=units,
                    status=ValueStatus.UNAVAILABLE,
                    data_class=spec["data_class"],
                    dataset_ids=spec["dataset_ids"],
                    native_resolution_m=spec["native_resolution_m"],
                )
            )
            continue

        try:
            with rasterio.open(raster_file) as src:
                transformer = pyproj.Transformer.from_crs(MARS_SPHERE_WKT, src.crs, always_xy=True)

                if lid in ("elevation", "mola_elevation", "slope", "roughness"):
                    val = _sample_continuous_raster(src, transformer, norm_lon, lat)
                    if val is None:
                        lv = LayerValue(
                            layer_id=lid,
                            value=None,
                            units=units,
                            status=ValueStatus.NO_COVERAGE,
                            data_class=spec["data_class"],
                            dataset_ids=spec["dataset_ids"],
                            native_resolution_m=spec["native_resolution_m"],
                        )
                    else:
                        lv = LayerValue(
                            layer_id=lid,
                            value=round(val, 4),
                            units=units,
                            status=ValueStatus.OK,
                            data_class=spec["data_class"],
                            dataset_ids=spec["dataset_ids"],
                            native_resolution_m=spec["native_resolution_m"],
                        )
                    layer_values.append(lv)

                elif lid == "hazard_grid":
                    pix = _sample_nearest_raster(src, transformer, norm_lon, lat)
                    if pix is None or pix == 1:
                        # 1 is IMPASSABLE_NODATA
                        val_str = "IMPASSABLE_NODATA" if pix == 1 else None
                        st = ValueStatus.NO_COVERAGE if pix is None else ValueStatus.OK
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=val_str,
                                units=None,
                                status=st,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )
                    else:
                        code_names = {
                            0: "PASSABLE",
                            2: "IMPASSABLE_SLOPE",
                            3: "IMPASSABLE_EXCLUSION",
                        }
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=code_names.get(int(pix), str(pix)),
                                units=None,
                                status=ValueStatus.OK,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )

                elif lid == "hazard_near":
                    pix = _sample_nearest_raster(src, transformer, norm_lon, lat)
                    val_str = "TRUE" if pix == 1 else "FALSE" if pix == 0 else None
                    st = ValueStatus.OK if pix is not None else ValueStatus.NO_COVERAGE
                    layer_values.append(
                        LayerValue(
                            layer_id=lid,
                            value=val_str,
                            units=None,
                            status=st,
                            data_class=spec["data_class"],
                            dataset_ids=spec["dataset_ids"],
                            native_resolution_m=spec["native_resolution_m"],
                        )
                    )

                elif lid == "hillshade":
                    pix = _sample_nearest_raster(src, transformer, norm_lon, lat)
                    if pix is None or pix == 0:
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=None,
                                units=None,
                                status=ValueStatus.NO_COVERAGE,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )
                    else:
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=float(pix),
                                units=None,
                                status=ValueStatus.OK,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )

                elif lid == "confidence":
                    pix = _sample_nearest_raster(src, transformer, norm_lon, lat)
                    conf_map = {0: "NONE", 1: "LOW", 2: "MEDIUM", 3: "HIGH"}
                    if pix is not None and int(pix) in conf_map:
                        conf_name = conf_map[int(pix)]
                        data_confidence_level = ConfidenceLevel(conf_name)
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=conf_name,
                                units=None,
                                status=ValueStatus.OK,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )
                    else:
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=None,
                                units=None,
                                status=ValueStatus.NO_COVERAGE,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )

                elif lid == "ortho":
                    pix = _sample_nearest_raster(src, transformer, norm_lon, lat)
                    if pix is None or pix == 0:
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=None,
                                units=None,
                                status=ValueStatus.NO_COVERAGE,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )
                    else:
                        layer_values.append(
                            LayerValue(
                                layer_id=lid,
                                value=float(pix),
                                units=None,
                                status=ValueStatus.OK,
                                data_class=spec["data_class"],
                                dataset_ids=spec["dataset_ids"],
                                native_resolution_m=spec["native_resolution_m"],
                            )
                        )

        except Exception:
            layer_values.append(
                LayerValue(
                    layer_id=lid,
                    value=None,
                    units=units,
                    status=ValueStatus.UNAVAILABLE,
                    data_class=spec["data_class"],
                    dataset_ids=spec["dataset_ids"],
                    native_resolution_m=spec["native_resolution_m"],
                )
            )

    # Environmental Context Indicators
    context_indicators = [
        ContextIndicator(
            indicator_id=ContextIndicatorId.RADIATION_CONTEXT,
            status=ContextStatus.UNAVAILABLE,
            summary="Surface radiation measurements unverified; pending network access in WP-18",
            value=None,
            units="uGy/d",
            period=None,
            data_class=DataClass.MEASURED,
            evidence=[
                EvidenceRef(
                    source_type="dataset",
                    source_id="MSL_RAD_SURFACE_RDR",
                    detail="MSL Curiosity RAD",
                )
            ],
            limitations=["Specific sol tables unverified in scope A; deferred to WP-18"],
        ),
        ContextIndicator(
            indicator_id=ContextIndicatorId.THERMAL_CONTEXT,
            status=ContextStatus.UNAVAILABLE,
            summary=(
                "THEMIS daytime thermal infrared not selected for download in scope A (core only)"
            ),
            value=None,
            units="K",
            period=None,
            data_class=DataClass.MEASURED,
            evidence=[
                EvidenceRef(
                    source_type="dataset",
                    source_id="THEMIS_DAY_IR_GLOBAL",
                    detail="THEMIS IR",
                )
            ],
            limitations=["Regional thermal context not downloaded in Scope A"],
        ),
    ]

    limitations = [
        "Features smaller than about 3x DTM post spacing (~3 m) are not reliably resolved",
        "Vertical datum of HiRISE DTM is UNVERIFIED; do not mix directly with MOLA elevations",
        "Decision D-013: slope and roughness incorporate ground-scale cos(latitude) correction",
        (
            "Roughness is a computational proxy for surface relief, "
            "not an explicit measurement of individual rocks"
        ),
    ]

    return PointInspection(
        region_id=region_id,
        point=GeoPoint(lat=lat, lon=norm_lon),
        values=layer_values,
        data_confidence=data_confidence_level,
        context=context_indicators,
        limitations=limitations,
    )


def compute_profile(
    request: ProfileRequest,
    data_dir: Path | None = None,
) -> ProfileResponse:
    """Compute cross-section profile along an ordered polyline path."""
    base_dir = data_dir or get_default_data_dir()
    raw_region = get_region_raw(request.region_id, data_dir=base_dir)
    bounds = GeoBounds(**raw_region["bounds"])

    # Validate all points are inside region
    for idx, pt in enumerate(request.points):
        validate_latitude(pt.lat)
        norm_lon = normalize_longitude(pt.lon)
        if not (
            bounds.lat_min <= pt.lat <= bounds.lat_max
            and bounds.lon_min <= norm_lon <= bounds.lon_max
        ):
            raise AppException(
                error_code="POINT_OUTSIDE_REGION",
                message=(
                    f"Profile point index {idx} ({pt.lat}, {norm_lon}) "
                    f"lies outside region '{request.region_id}' bounds"
                ),
                status_code=422,
                details={
                    "region_id": request.region_id,
                    "index": idx,
                    "point": {"lat": pt.lat, "lon": norm_lon},
                },
            )

    spacing_m = request.sample_spacing_m or float(
        raw_region.get("analysis", {}).get("cell_size_m", 1.0)
    )

    # Interpolate along polyline legs
    all_samples: list[tuple[GeoPoint, float]] = []
    cumulative_dist = 0.0

    for i in range(len(request.points) - 1):
        p_start = request.points[i]
        p_end = request.points[i + 1]
        leg_pts = interpolate_great_circle_points(p_start, p_end, sample_spacing_m=spacing_m)

        for pt, d_leg in leg_pts:
            if all_samples and d_leg == 0.0:
                # Avoid duplicate point at segment joints
                continue
            all_samples.append((pt, cumulative_dist + d_leg))

        if leg_pts:
            cumulative_dist += leg_pts[-1][1]

    # Sample elevation and slope for each point
    dtm_file = base_dir / "processed" / "HIRISE_DTM_GALE_MOUND.tif"
    slope_file = base_dir / "processed" / "HIRISE_SLOPE_GALE_MOUND.tif"

    profile_points: list[ProfilePoint] = []

    if dtm_file.exists() and slope_file.exists():
        with rasterio.open(dtm_file) as dtm_src, rasterio.open(slope_file) as slope_src:
            dtm_trans = pyproj.Transformer.from_crs(MARS_SPHERE_WKT, dtm_src.crs, always_xy=True)
            slope_trans = pyproj.Transformer.from_crs(
                MARS_SPHERE_WKT, slope_src.crs, always_xy=True
            )

            for pt, dist in all_samples:
                elev = _sample_continuous_raster(dtm_src, dtm_trans, pt.lon, pt.lat)
                slope = _sample_continuous_raster(slope_src, slope_trans, pt.lon, pt.lat)
                profile_points.append(
                    ProfilePoint(
                        distance_m=round(dist, 2),
                        point=pt,
                        elevation_m=round(elev, 2) if elev is not None else None,
                        slope_deg=round(slope, 2) if slope is not None else None,
                    )
                )
    else:
        # Fallback if rasters absent
        for pt, dist in all_samples:
            profile_points.append(
                ProfilePoint(
                    distance_m=round(dist, 2),
                    point=pt,
                    elevation_m=None,
                    slope_deg=None,
                )
            )

    total_dist = profile_points[-1].distance_m if profile_points else 0.0

    evidence = [
        EvidenceRef(
            source_type="dataset",
            source_id="HIRISE_DTM_GALE_MOUND",
            detail="HiRISE stereo DTM elevation and Horn slope",
        )
    ]
    limitations = [
        "Profile samples interpolated along great-circle segments at nominal spacing",
        "Features smaller than ~3 m not resolved in DTM",
        "Decision D-013: slope incorporates ground-scale cos(latitude) correction",
    ]

    return ProfileResponse(
        samples=profile_points,
        total_horizontal_distance_m=round(total_dist, 2),
        evidence=evidence,
        limitations=limitations,
    )
