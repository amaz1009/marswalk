"""Generate terrain and hazard layers for region from processed DTM.

Implements WP-07 pipeline for Gale Crater / Mount Sharp:
- Horn slope with per-row ground spacing (spec section 4.2, Amendment A-2, D-013)
- Residual RMS roughness (spec section 4.3)
- Conservative analysis grid aggregation (spec section 4.4)
- Hillshade (spec section 4.6)
- Hazard grid and NEAR_HAZARD flags (spec section 5)
- Data-confidence layer (spec section 11)
- Writes outputs to backend/data/processed/ as COGs and prints layer statistics.
"""

import argparse
import logging
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict

import numpy as np
import rasterio

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engines.hazards.grid import HazardState, compute_hazard_grid  # noqa: E402
from app.engines.terrain.aggregate import aggregate_to_analysis_grid  # noqa: E402
from app.engines.terrain.confidence import (  # noqa: E402
    ConfidenceCode,
    compute_data_confidence,
)
from app.engines.terrain.hillshade import compute_hillshade  # noqa: E402
from app.engines.terrain.roughness import compute_residual_roughness  # noqa: E402
from app.engines.terrain.slope import (  # noqa: E402
    compute_horn_slope,
    compute_row_ground_scales,
    verify_equirectangular_mars_crs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("generate_terrain_layers")


def print_continuous_stats(
    name: str,
    arr: np.ndarray,
    thresholds: list[float] | None = None,
    units: str = "",
) -> Dict[str, float]:
    """Compute and print distribution statistics for a continuous float layer."""
    total = arr.size
    valid_mask = ~np.isnan(arr)
    valid_count = int(np.sum(valid_mask))
    valid_fraction = float(valid_count / total) if total > 0 else 0.0
    frac_unknown = 1.0 - valid_fraction

    print(f"=== {name} Statistics ===")
    print(f"  Total cells:        {total:,}")
    print(f"  Valid cells:        {valid_count:,} ({valid_fraction * 100.0:.2f}%)")
    print(f"  Fraction UNKNOWN:   {frac_unknown * 100.0:.2f}%")

    if valid_count == 0:
        print("  All cells are UNKNOWN / NODATA.\n")
        return {"total": total, "valid_count": 0, "valid_fraction": 0.0}

    valid_vals = arr[valid_mask]
    val_min = float(np.min(valid_vals))
    val_max = float(np.max(valid_vals))
    val_mean = float(np.mean(valid_vals))

    p = np.percentile(valid_vals, [50, 75, 90, 95, 99])
    print(f"  Min valid:          {val_min:.4f} {units}".rstrip())
    print(f"  Max valid:          {val_max:.4f} {units}".rstrip())
    print(f"  Mean valid:         {val_mean:.4f} {units}".rstrip())
    print(
        f"  Percentiles (50/75/90/95/99): {p[0]:.4f}, {p[1]:.4f}, "
        f"{p[2]:.4f}, {p[3]:.4f}, {p[4]:.4f} {units}".rstrip()
    )

    # 1/4 decimated percentiles (matching owner inspection stride)
    dec_sample = arr[::4, ::4]
    dec_valid = dec_sample[~np.isnan(dec_sample)]
    if dec_valid.size > 0:
        p_dec = np.percentile(dec_valid, [50, 75, 90, 95, 99])
        print(
            f"  1/4 Decimated (50/75/90/95/99): {p_dec[0]:.4f}, {p_dec[1]:.4f}, "
            f"{p_dec[2]:.4f}, {p_dec[3]:.4f}, {p_dec[4]:.4f} {units}".rstrip()
        )

    if thresholds:
        for t in thresholds:
            frac_above = float(np.sum(valid_vals > t) / valid_count)
            print(f"  Fraction > {t:g} {units}:   {frac_above * 100.0:.2f}% ({frac_above:.4f})")

    print()
    return {
        "total": float(total),
        "valid_count": float(valid_count),
        "valid_fraction": valid_fraction,
        "frac_unknown": frac_unknown,
        "min": val_min,
        "max": val_max,
        "mean": val_mean,
        "p50": float(p[0]),
        "p75": float(p[1]),
        "p90": float(p[2]),
        "p95": float(p[3]),
        "p99": float(p[4]),
    }


def print_hazard_stats(states: np.ndarray) -> None:
    """Print value counts and percentages for categorical HazardState layer."""
    total = states.size
    print("=== Hazard States Statistics ===")
    print(f"  Total cells:        {total:,}")
    print(
        "  Encoding: 0: PASSABLE, 1: IMPASSABLE_NODATA, "
        "2: IMPASSABLE_SLOPE, 3: IMPASSABLE_EXCLUSION"
    )
    for state in HazardState:
        count = int(np.sum(states == state.value))
        frac = count / total
        print(f"    Code {state.value} ({state.name:<18}): {count:,} ({frac * 100.0:.2f}%)")
    print()


def print_near_hazard_stats(near_hazard: np.ndarray) -> None:
    """Print value counts and percentages for binary NEAR_HAZARD flag."""
    total = near_hazard.size
    count_false = int(np.sum(near_hazard == 0))
    count_true = int(np.sum(near_hazard == 1))
    print("=== NEAR_HAZARD Flag Statistics ===")
    print(f"  Total cells:        {total:,}")
    print(
        "  Encoding: 0: False (Not adjacent to hazard), "
        "1: True (Within 1 cell 8-neighbour of impassable cell)"
    )
    print(f"    Code 0 (False):               {count_false:,} ({count_false / total * 100.0:.2f}%)")
    print(f"    Code 1 (True):                {count_true:,} ({count_true / total * 100.0:.2f}%)")
    print()


def print_hillshade_stats(hillshade: np.ndarray) -> None:
    """Print statistics for hillshade (0=NODATA, 1-255=shaded relief)."""
    total = hillshade.size
    nodata_count = int(np.sum(hillshade == 0))
    valid_count = total - nodata_count
    print("=== Hillshade (0-255) Statistics ===")
    print(f"  Total cells:        {total:,}")
    print(
        "  Encoding: 0: NODATA (unilluminated / edge / missing DTM), "
        "1-255: Valid shaded relief (1=shadow, 255=peak)"
    )
    nodata_pct = nodata_count / total * 100.0
    valid_pct = valid_count / total * 100.0
    print(f"    Code 0 (NODATA):              {nodata_count:,} ({nodata_pct:.2f}%)")
    print(f"    Valid shaded (1-255):         {valid_count:,} ({valid_pct:.2f}%)")
    if valid_count > 0:
        valid_vals = hillshade[hillshade > 0]
        p = np.percentile(valid_vals, [50, 75, 90, 95, 99])
        print(f"    Min valid:                    {int(np.min(valid_vals))}")
        print(f"    Max valid:                    {int(np.max(valid_vals))}")
        print(f"    Mean valid:                   {float(np.mean(valid_vals)):.2f}")
        print(
            f"    Percentiles (50/75/90/95/99): {int(p[0])}, {int(p[1])}, "
            f"{int(p[2])}, {int(p[3])}, {int(p[4])}"
        )
    print()


def print_confidence_stats(confidence: np.ndarray) -> None:
    """Print value counts and percentages for categorical ConfidenceCode layer."""
    total = confidence.size
    print("=== Data Confidence Levels Statistics ===")
    print(f"  Total cells:        {total:,}")
    print(
        "  Encoding: 0: NONE (No valid terrain), 1: LOW (Regional context / DTM only), "
        "2: MEDIUM (DTM + optical), 3: HIGH (DTM <= 2m + optical + context)"
    )
    for code in ConfidenceCode:
        count = int(np.sum(confidence == code.value))
        frac = count / total
        print(f"    Code {code.value} ({code.name:<6}): {count:,} ({frac * 100.0:.2f}%)")
    print()


def write_cog(
    output_path: Path,
    data: np.ndarray,
    transform: rasterio.Affine,
    crs: rasterio.crs.CRS,
    nodata: float | int | None = None,
) -> None:
    """Write array to GeoTIFF COG with tiling and deflate compression."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = data.shape
    dtype = data.dtype

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
    }
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data, 1)

    logger.info(f"Wrote {output_path.name} ({output_path.stat().st_size:,} bytes)")


def run_terrain_engine(data_dir: Path) -> int:
    """Run terrain and hazard calculations on processed DTM."""
    processed_dir = data_dir / "processed"
    dtm_path = processed_dir / "HIRISE_DTM_GALE_MOUND.tif"
    ortho_path = processed_dir / "HIRISE_ORTHO_GALE_MOUND.tif"
    mola_path = processed_dir / "MOLA_MEGDR_GALE.tif"

    if not dtm_path.exists():
        logger.error(f"DTM GeoTIFF not found: {dtm_path}")
        return 1

    tracemalloc.start()
    t_start = time.perf_counter()

    logger.info(f"Opening DTM: {dtm_path}")
    with rasterio.open(dtm_path) as src:
        verify_equirectangular_mars_crs(src.crs)
        elev = src.read(1)
        transform = src.transform
        crs = src.crs

    height, width = elev.shape
    logger.info(f"DTM Shape: {height} rows x {width} cols ({elev.size:,} cells)")

    # 1. Per-row ground spacing (Amendment A-2, Owner Decision D-013)
    logger.info("Computing per-row ground spacing dx_ground = dx_proj * cos(phi_row)...")
    dx_ground, dy = compute_row_ground_scales(transform.a, transform.e, transform.f, height)
    cos_factor = np.mean(dx_ground) / abs(transform.a)
    logger.info(
        f"Ground scale: dy = {dy:.6f} m; "
        f"dx_ground range: [{np.min(dx_ground):.6f}, {np.max(dx_ground):.6f}] m "
        f"(mean {np.mean(dx_ground):.6f} m, cos(phi) factor ~ {cos_factor:.6f})"
    )

    # 2. Native Horn slope
    logger.info("Computing native Horn slope (spec section 4.2 + Amendment A-2)...")
    slope = compute_horn_slope(elev, dx_ground, dy, chunk_size=2000)
    slope_path = processed_dir / "HIRISE_SLOPE_GALE_MOUND.tif"
    write_cog(slope_path, slope, transform, crs, nodata=np.nan)
    print_continuous_stats(
        "Native Horn Slope (degrees)", slope, thresholds=[10.0, 15.0, 30.0], units="deg"
    )

    # 3. Native residual RMS roughness
    logger.info("Computing native residual RMS roughness (spec section 4.3 + Amendment A-2)...")
    roughness = compute_residual_roughness(elev, dx_ground, dy, k=3, chunk_size=2000)
    rough_path = processed_dir / "HIRISE_ROUGHNESS_GALE_MOUND.tif"
    write_cog(rough_path, roughness, transform, crs, nodata=np.nan)
    print_continuous_stats(
        "Native Residual Roughness (metres)",
        roughness,
        thresholds=[0.30, 0.50, 1.00],
        units="m",
    )

    # 4. Conservative aggregation to analysis grid (section 4.4)
    # HiRISE DTM is ~1m; analysis grid is 1m (block_size=1)
    logger.info("Aggregating to analysis grid resolution (spec section 4.4)...")
    agg = aggregate_to_analysis_grid(elev, slope, roughness, block_size=1)

    # 5. Hazard grid calculation (section 5)
    logger.info("Computing hazard grid and NEAR_HAZARD flags (spec section 5, max_slope=15 deg)...")
    hazard_res = compute_hazard_grid(
        agg["elevation"],
        agg["slope_max"],
        max_slope_deg=15.0,
        valid_mask=agg["is_valid"],
    )

    hazard_path = processed_dir / "HAZARD_GRID_GALE_MOUND.tif"
    write_cog(hazard_path, hazard_res.states, transform, crs, nodata=None)
    print_hazard_stats(hazard_res.states)

    near_hazard_uint8 = hazard_res.near_hazard.astype(np.uint8)
    near_hazard_path = processed_dir / "HAZARD_NEAR_GALE_MOUND.tif"
    write_cog(near_hazard_path, near_hazard_uint8, transform, crs, nodata=None)
    print_near_hazard_stats(near_hazard_uint8)

    # 6. Hillshade (section 4.6)
    logger.info("Computing hillshade for display (spec section 4.6, az=315 deg, alt=45 deg)...")
    mean_dx = float(np.mean(dx_ground))
    hillshade = compute_hillshade(agg["elevation"], mean_dx, dy, chunk_size=2000)
    hillshade_path = processed_dir / "HILLSHADE_GALE_MOUND.tif"
    write_cog(hillshade_path, hillshade, transform, crs, nodata=0)
    print_hillshade_stats(hillshade)

    # 7. Data confidence (section 11)
    logger.info("Computing data-confidence layer (spec section 11)...")
    has_valid_dtm = ~np.isnan(agg["slope_max"])
    has_ortho = None
    if ortho_path.exists():
        with rasterio.open(ortho_path) as o_src:
            ortho_arr = o_src.read(1)
            has_ortho = ortho_arr > 0

    has_mola = np.ones(elev.shape, dtype=bool) if mola_path.exists() else None

    confidence = compute_data_confidence(
        has_valid_dtm_slope=has_valid_dtm,
        dtm_post_spacing_m=float(abs(transform.a)),
        has_optical_coverage=has_ortho,
        has_context_coverage=None,  # THEMIS / Geology unavailable in scope A
        has_regional_context=has_mola,
    )
    conf_path = processed_dir / "CONFIDENCE_GALE_MOUND.tif"
    write_cog(conf_path, confidence, transform, crs, nodata=None)
    print_confidence_stats(confidence)

    t_end = time.perf_counter()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    logger.info(f"Total processing time: {t_end - t_start:.2f} seconds")
    logger.info(f"Peak memory traced: {peak_mem / (1024 * 1024):.2f} MB")
    print("=== SUMMARY ===")
    print(f"Processing elapsed: {t_end - t_start:.2f} s")
    print(f"Peak memory traced: {peak_mem / (1024 * 1024):.2f} MB")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate terrain and hazard layers.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=BACKEND_DIR / "data",
        help="Path to backend data directory",
    )
    args = parser.parse_args()
    return run_terrain_engine(args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
