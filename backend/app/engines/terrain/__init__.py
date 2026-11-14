"""Terrain analysis engine modules implementing docs/SCIENCE_AND_SAFETY_SPEC.md section 4."""

from app.engines.terrain.aggregate import aggregate_to_analysis_grid
from app.engines.terrain.confidence import compute_data_confidence
from app.engines.terrain.hillshade import compute_hillshade
from app.engines.terrain.profile import compute_elevation_profile
from app.engines.terrain.roughness import compute_residual_roughness
from app.engines.terrain.sampling import sample_bilinear, sample_nearest
from app.engines.terrain.slope import compute_horn_slope

__all__ = [
    "aggregate_to_analysis_grid",
    "compute_data_confidence",
    "compute_elevation_profile",
    "compute_hillshade",
    "compute_horn_slope",
    "compute_residual_roughness",
    "sample_bilinear",
    "sample_nearest",
]
