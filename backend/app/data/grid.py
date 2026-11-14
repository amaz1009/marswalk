"""Analysis grid loader and builder.

Implements docs/SYSTEM_ARCHITECTURE.md section 7.3 and docs/SCIENCE_AND_SAFETY_SPEC.md section 2.5:
- Analysis grid represents the common projected coordinate space for routing and hazard checks.
- Encapsulates elevation, slope, roughness, hazard state, near-hazard flags, and confidence.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import rasterio

from app.engines.hazards.grid import compute_hazard_grid
from app.engines.terrain.aggregate import aggregate_to_analysis_grid
from app.engines.terrain.confidence import compute_data_confidence
from app.engines.terrain.hillshade import compute_hillshade
from app.engines.terrain.roughness import compute_residual_roughness
from app.engines.terrain.slope import (
    compute_horn_slope,
    compute_row_ground_scales,
    verify_equirectangular_mars_crs,
)
from app.models.geometry import GeoBounds


@dataclass
class AnalysisGrid:
    """In-memory analysis grid for terrain and hazard evaluation."""

    region_id: str
    elevation: np.ndarray
    slope: np.ndarray
    roughness: np.ndarray
    hazard_states: np.ndarray
    near_hazard: np.ndarray
    confidence: np.ndarray
    hillshade: np.ndarray
    transform: rasterio.Affine
    crs: Any
    cell_size_m: float
    bounds: GeoBounds
    valid_fraction: float


def build_analysis_grid_from_rasters(
    region_id: str,
    elevation_path: Path,
    ortho_path: Optional[Path] = None,
    mola_path: Optional[Path] = None,
    max_slope_deg: float = 15.0,
) -> AnalysisGrid:
    """Build analysis grid from processed COG GeoTIFF files.

    Performs:
    1. Runtime CRS validation (D-013).
    2. Per-row ground spacing derivation (Amendment A-2).
    3. Horn slope and residual roughness computation at native post spacing.
    4. Conservative aggregation to analysis grid resolution.
    5. Hazard grid and NEAR_HAZARD flags.
    6. Hillshade and data-confidence layers.

    Args:
        region_id: Identifier of the region.
        elevation_path: Path to primary DTM GeoTIFF.
        ortho_path: Optional path to optical orthoimage.
        mola_path: Optional path to regional MOLA context.
        max_slope_deg: Maximum allowable slope before impassable classification.

    Returns:
        Populated AnalysisGrid instance.
    """
    with rasterio.open(elevation_path) as src:
        verify_equirectangular_mars_crs(src.crs)
        elev = src.read(1)
        transform = src.transform
        crs = src.crs

        # Ground spacing per row (Amendment A-2, D-013)
        dx_ground, dy = compute_row_ground_scales(
            transform.a, transform.e, transform.f, elev.shape[0]
        )

        b = src.bounds
        bounds = GeoBounds(
            lat_min=float(b.bottom),
            lat_max=float(b.top),
            lon_min=float(b.left),
            lon_max=float(b.right),
        )

    # 1. Native Horn slope with per-row ground spacing
    slope = compute_horn_slope(elev, dx_ground, dy)

    # 2. Native residual roughness
    roughness = compute_residual_roughness(elev, dx_ground, dy)

    # 3. Aggregation (1:1 native for primary HiRISE 1m DTM)
    agg = aggregate_to_analysis_grid(elev, slope, roughness, block_size=1)

    # 4. Hazard grid computation
    hazard_res = compute_hazard_grid(
        agg["elevation"],
        agg["slope_max"],
        max_slope_deg=max_slope_deg,
        valid_mask=agg["is_valid"],
    )

    # 5. Hillshade for display
    mean_dx = float(np.mean(dx_ground))
    hillshade = compute_hillshade(agg["elevation"], mean_dx, dy)

    # 6. Data confidence
    has_valid_slope = ~np.isnan(agg["slope_max"])
    has_ortho = None
    if ortho_path and ortho_path.exists():
        with rasterio.open(ortho_path) as o_src:
            ortho_data = o_src.read(1)
            has_ortho = ortho_data > 0

    confidence = compute_data_confidence(
        has_valid_dtm_slope=has_valid_slope,
        dtm_post_spacing_m=float(transform.a),
        has_optical_coverage=has_ortho,
        has_regional_context=np.ones(elev.shape, dtype=bool) if mola_path else None,
    )

    valid_cells = np.sum(agg["is_valid"])
    total_cells = elev.size
    valid_fraction = float(valid_cells / total_cells)

    return AnalysisGrid(
        region_id=region_id,
        elevation=agg["elevation"],
        slope=agg["slope_max"],
        roughness=agg["roughness_max"],
        hazard_states=hazard_res.states,
        near_hazard=hazard_res.near_hazard,
        confidence=confidence,
        hillshade=hillshade,
        transform=transform,
        crs=crs,
        cell_size_m=float(abs(transform.a)),
        bounds=bounds,
        valid_fraction=valid_fraction,
    )
