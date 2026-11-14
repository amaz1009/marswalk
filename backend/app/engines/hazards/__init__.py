"""Hazard grid calculation engine implementing docs/SCIENCE_AND_SAFETY_SPEC.md section 5."""

from app.engines.hazards.grid import HazardGridResult, HazardState, compute_hazard_grid

__all__ = ["HazardGridResult", "HazardState", "compute_hazard_grid"]
