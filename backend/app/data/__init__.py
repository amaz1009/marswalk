"""Data pipeline package for MARSWALK.

Provides loaders, CRS verification, raster processing stages, and footprint calculations.
"""

from app.data.crs import (
    CRSValidationError,
    convert_internal_to_source_latitude_if_needed,
    convert_source_latitude_if_needed,
    inspect_raster_crs,
)
from app.data.footprint import (
    compute_raster_footprint,
    evaluate_named_area_in_footprint,
    point_in_footprint,
)
from app.data.loaders import (
    get_dataset_record,
    load_catalog,
    load_data_sources,
    load_processing_manifest,
    load_region_config,
    load_source_ledger,
    validate_region_config,
)
from app.data.pipeline import (
    append_to_processing_manifest,
    compute_coverage_statistics,
    create_processing_step,
    normalize_nodata,
    write_cog_geotiff,
)

__all__ = [
    "CRSValidationError",
    "append_to_processing_manifest",
    "compute_coverage_statistics",
    "compute_raster_footprint",
    "convert_internal_to_source_latitude_if_needed",
    "convert_source_latitude_if_needed",
    "create_processing_step",
    "evaluate_named_area_in_footprint",
    "get_dataset_record",
    "inspect_raster_crs",
    "load_catalog",
    "load_data_sources",
    "load_processing_manifest",
    "load_region_config",
    "load_source_ledger",
    "normalize_nodata",
    "point_in_footprint",
    "validate_region_config",
    "write_cog_geotiff",
]
