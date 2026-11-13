# MARSWALK — API Contracts, Shared Models and Data Dictionary

| Field          | Value                                                                        |
|----------------|------------------------------------------------------------------------------|
| Document       | API_CONTRACTS.md                                                             |
| Version        | 1.0                                                                          |
| Owner          | Orchestrator                                                                 |
| Last updated   | 2026-11-11                                                                   |
| Change control | Contract changes require Orchestrator approval, a version bump of this file, and a log entry in DEVELOPMENT_STATUS.md |

This document is the single source of truth for every interface in MARSWALK. The
Pydantic models in `backend/app/models/` implement it exactly. The frontend uses
TypeScript types generated from the backend OpenAPI schema
(`frontend/src/types/api.gen.ts`, produced by `npm run gen:api`). Nobody writes API
types by hand.

---

## 1. General Conventions

| Topic | Rule |
|-------|------|
| Base path | `/api/v1` |
| Format | JSON (UTF-8). Exceptions: layer images (`image/png`), surface images (`image/jpeg` or `image/png`), vector layers (`application/geo+json`). |
| Field names | `snake_case` |
| Timestamps | ISO-8601 with timezone, UTC (`2026-11-14T09:30:00Z`) |
| Identifiers | See `SYSTEM_ARCHITECTURE.md` §6.4. Generated IDs are `<prefix>_<uuid4 hex>`. |
| Coordinates | `lat` planetocentric degrees [-90, 90]; `lon` east-positive degrees [0, 360). Inputs with `lon` in [-180, 0) are normalised by adding 360. Values outside [-180, 360) are rejected. |
| GeoJSON | Coordinate order `[lon, lat]`, Mars internal convention (not WGS84). |
| Units | Metres, seconds, degrees, kelvin. Unit names are always stated in a `units` field where a value could be ambiguous. |
| Nulls | `null` means "not available". It is never replaced by `0`. Every `null` measurement is accompanied by a status explaining why. |
| Statelessness | The backend stores no mission state in P0 (ADR-15). |
| Versioning | Breaking changes require `/api/v2`. Additive optional fields are allowed in v1 with a version bump of this document. |
| Engine version | Computed responses include `engine_version` (backend package version string). |

---

## 2. Enumerations

| Enum | Values |
|------|--------|
| `AssessmentStatus` | `PASS`, `WARNING`, `BLOCKED`, `UNKNOWN` |
| `DataClass` | `MEASURED`, `DERIVED`, `MODEL`, `REFERENCE`, `ASSUMPTION`, `SAMPLE`, `AI_INTERPRETATION` |
| `DatasetStatus` | `AVAILABLE`, `PARTIAL`, `UNAVAILABLE` |
| `DataType` | `ELEVATION`, `OPTICAL`, `THERMAL`, `GEOLOGY`, `MINERALOGY`, `RADIATION`, `SURFACE_IMAGE`, `ICE`, `DERIVED` |
| `LayerKind` | `RASTER`, `VECTOR` |
| `ValueStatus` | `OK`, `NO_COVERAGE`, `UNAVAILABLE` |
| `RouteObjective` | `LOWEST_RISK`, `BALANCED`, `MAX_SCIENCE` |
| `PlanStatus` | `OK`, `NO_FEASIBLE_ROUTE`, `INSUFFICIENT_DATA` |
| `TimelineKind` | `WALK`, `WORK`, `MARGIN`, `RESERVE` |
| `ContextStatus` | `AVAILABLE`, `UNAVAILABLE` |
| `ConfidenceLevel` | `HIGH`, `MEDIUM`, `LOW`, `NONE` |
| `LlmMode` | `DISABLED`, `ENABLED` |
| `AgentRunStatus` | `SUCCESS`, `DEGRADED`, `FAILED`, `SKIPPED` |
| `SafetyCheckId` | `SLOPE_MAX`, `HAZARD_INTERSECTION`, `TERRAIN_DATA_COVERAGE`, `EVA_DURATION`, `RETURN_RESERVE`, `ROUGHNESS`, `DISTANCE_FROM_BASE` |
| `ContextIndicatorId` | `RADIATION_CONTEXT`, `THERMAL_CONTEXT` |

---

## 3. Shared Models

Types: `str`, `int`, `float`, `bool`, `datetime`, `list[T]`, `T | null`. A `?` after a
field name means the field is optional (it may be omitted or `null`).

### 3.1 Geometry

**`GeoPoint`**

| Field | Type | Rules |
|-------|------|-------|
| `lat` | float | [-90, 90], planetocentric |
| `lon` | float | Normalised to [0, 360) |

**`GeoBounds`**

| Field | Type | Rules |
|-------|------|-------|
| `lat_min` | float | < `lat_max` |
| `lat_max` | float | |
| `lon_min` | float | [0, 360) |
| `lon_max` | float | [0, 360). If `lon_min > lon_max`, the box crosses 0°/360°. |

### 3.2 Evidence and Assumptions

**`EvidenceRef`**

| Field | Type | Rules |
|-------|------|-------|
| `source_type` | str | `dataset`, `engine`, `assumption`, `reference` |
| `source_id` | str | A `dataset_id`, engine name (for example `engines.routing`), assumption key, or reference key |
| `detail?` | str | Field, product or method detail |

**`AssumptionRecord`**

| Field | Type | Rules |
|-------|------|-------|
| `key` | str | Matches an `EvaConfig` field or another documented parameter |
| `value` | float \| str \| bool | |
| `units` | str \| null | |
| `data_class` | DataClass | `ASSUMPTION` or `REFERENCE` |
| `basis` | str | Short statement of where the value comes from |
| `citation?` | str | Reference key from `SCIENCE_AND_SAFETY_SPEC.md` §15 |

### 3.3 Datasets and Layers

**`TemporalCoverage`**

| Field | Type | Rules |
|-------|------|-------|
| `start?` | datetime | |
| `end?` | datetime | |
| `description` | str | For example "Mosaic of observations 2002–2020" or "Static" |

**`ProcessingStep`**

| Field | Type | Rules |
|-------|------|-------|
| `step` | str | One of the pipeline stage names in `SYSTEM_ARCHITECTURE.md` §7.2 |
| `tool` | str | Library and version, for example `rasterio 1.4.x` |
| `parameters` | object | Step parameters |
| `completed_at` | datetime | |

**`DatasetRecord`** (also the schema of each entry in `dataset_catalog.json`)

| Field | Type | Rules |
|-------|------|-------|
| `dataset_id` | str | Unique, UPPERCASE snake_case |
| `name` | str | Human-readable |
| `mission` | str | For example `MRO`, `Mars Odyssey`, `MSL` |
| `instrument` | str | For example `HiRISE`, `CTX`, `THEMIS`, `RAD` |
| `source_archive` | str | For example `NASA PDS Imaging Node`, `USGS Astrogeology` |
| `source_url` | str | Landing page or product URL actually used |
| `product_ids` | list[str] | Archive product identifiers |
| `citation` | str | How to cite the product |
| `data_type` | DataType | |
| `data_class` | DataClass | Usually `MEASURED`; derived products use `DERIVED` |
| `units` | str \| null | |
| `source_crs` | str | WKT or PROJ string exactly as read from the source |
| `source_conventions` | str | Latitude type and longitude direction of the source |
| `native_resolution_m` | float \| null | Ground sample distance or post spacing |
| `temporal_coverage` | TemporalCoverage | |
| `coverage_bounds` | GeoBounds \| null | |
| `region_coverage_fraction` | float \| null | 0–1, share of the region covered by valid data |
| `status` | DatasetStatus | |
| `status_reason?` | str | Required when status is not `AVAILABLE` |
| `processing_steps` | list[ProcessingStep] | |
| `processed_path?` | str | Relative to the data directory |
| `limitations` | list[str] | At least one entry |
| `usage_note?` | str | Licence or usage terms if stated by the source |
| `retrieved_at?` | datetime | |

**`Legend`**

| Field | Type | Rules |
|-------|------|-------|
| `colormap` | str | For example `viridis`, `magma`, `gray`, `categorical` |
| `vmin?` | float | Raster layers |
| `vmax?` | float | Raster layers |
| `units?` | str | |
| `categories?` | list[`LegendCategory`] | Categorical layers: `{value, label, color}` |

**`LayerInfo`**

| Field | Type | Rules |
|-------|------|-------|
| `layer_id` | str | lowercase snake_case |
| `name` | str | |
| `kind` | LayerKind | |
| `data_type` | DataType | |
| `status` | DatasetStatus | Layers with `UNAVAILABLE` status cannot be enabled |
| `status_reason?` | str | |
| `dataset_ids` | list[str] | |
| `data_class` | DataClass | |
| `bounds` | GeoBounds \| null | |
| `native_resolution_m` | float \| null | |
| `legend` | Legend \| null | |
| `image_url?` | str | Raster layers: relative URL of the PNG overlay |
| `features_url?` | str | Vector layers: relative URL of the GeoJSON |
| `limitations` | list[str] | |

### 3.4 Regions

**`ScienceTarget`**

| Field | Type | Rules |
|-------|------|-------|
| `target_id` | str | |
| `name` | str | |
| `point` | GeoPoint | |
| `rationale` | str | Why it is scientifically interesting |
| `data_class` | DataClass | `REFERENCE` for literature-sourced targets |
| `evidence` | list[EvidenceRef] | At least one |
| `citation?` | str | |

**`RegionSummary`**

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | |
| `name` | str | |
| `description` | str | |
| `science_objective` | str | |
| `bounds` | GeoBounds | |

**`RegionDetail`** = `RegionSummary` plus:

| Field | Type | Rules |
|-------|------|-------|
| `analysis` | `AnalysisSettings` | `{primary_dtm_dataset_id, analysis_crs, cell_size_m, max_grid_cells}` |
| `default_base?` | GeoPoint | Suggested base or landing point, with `default_base_basis` text |
| `default_base_basis?` | str | Why this point was chosen; `ASSUMPTION` |
| `science_targets` | list[ScienceTarget] | May be empty |
| `layer_ids` | list[str] | Layers configured for this region |
| `data_status` | `{datasets_available: int, datasets_unavailable: int}` | |

### 3.5 Terrain

**`LayerValue`**

| Field | Type | Rules |
|-------|------|-------|
| `layer_id` | str | |
| `value` | float \| str \| null | `str` for categorical layers (for example a geologic unit label) |
| `units` | str \| null | |
| `status` | ValueStatus | |
| `data_class` | DataClass | |
| `dataset_ids` | list[str] | |
| `native_resolution_m` | float \| null | |

**`ContextIndicator`**

| Field | Type | Rules |
|-------|------|-------|
| `indicator_id` | ContextIndicatorId | |
| `status` | ContextStatus | Never a safety status |
| `summary` | str | Plain statement of what the data shows |
| `value?` | float | |
| `units?` | str | |
| `period?` | str | Observation period |
| `data_class` | DataClass | |
| `evidence` | list[EvidenceRef] | |
| `limitations` | list[str] | At least one |

**`PointInspection`**

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | |
| `point` | GeoPoint | Normalised input |
| `values` | list[LayerValue] | One entry per configured layer |
| `data_confidence` | ConfidenceLevel | See `SCIENCE_AND_SAFETY_SPEC.md` §11 |
| `context` | list[ContextIndicator] | |
| `limitations` | list[str] | |

**`ProfilePoint`**

| Field | Type | Rules |
|-------|------|-------|
| `distance_m` | float | Cumulative horizontal distance from the start |
| `point` | GeoPoint | |
| `elevation_m` | float \| null | |
| `slope_deg` | float \| null | Terrain slope at the sample |

### 3.6 EVA, Routes and Safety

**`EvaConfig`** (effective configuration in responses; all nine fields required; defaults and their sources are defined in
`SCIENCE_AND_SAFETY_SPEC.md` §6.2)

| Field | Type | Units | Rules |
|-------|------|-------|-------|
| `base_speed_kmh` | float | km/h | > 0, ≤ 6 |
| `max_slope_deg` | float | degrees | Hard limit, > 0, ≤ 30 |
| `warning_slope_deg` | float | degrees | < `max_slope_deg` |
| `max_eva_hours` | float | hours | > 0, ≤ 10 |
| `return_reserve_fraction` | float | fraction | [0, 0.9] |
| `traverse_time_margin` | float | factor | ≥ 1.0, ≤ 3.0 |
| `default_work_time_min` | float | minutes | ≥ 0 |
| `max_distance_from_base_m` | float | metres | > 0 |
| `roughness_warning_m` | float | metres | > 0 |

**`EvaConfigOverride`** (all fields optional in requests; missing fields take defaults from
`GET /eva/defaults`; same ranges and slope validation as `EvaConfig`)

**`Stop`**

| Field | Type | Rules |
|-------|------|-------|
| `stop_id` | str | |
| `name` | str | |
| `point` | GeoPoint | |
| `work_time_min?` | float | Overrides `default_work_time_min` |
| `target_id?` | str | Links to a `ScienceTarget` |

**`SafetyCheck`**

| Field | Type | Rules |
|-------|------|-------|
| `check_id` | SafetyCheckId | |
| `critical` | bool | As defined in `SCIENCE_AND_SAFETY_SPEC.md` §9 |
| `status` | AssessmentStatus | |
| `value` | float \| null | Measured or computed quantity |
| `threshold` | float \| null | Limit the value was compared against |
| `units` | str \| null | |
| `message` | str | Plain explanation of the result |
| `evidence` | list[EvidenceRef] | |

**`SafetyAssessment`**

| Field | Type | Rules |
|-------|------|-------|
| `overall_status` | AssessmentStatus | Computed only by the aggregation rule |
| `checks` | list[SafetyCheck] | All seven checks, always present |
| `context` | list[ContextIndicator] | |
| `disclaimer` | str | Fixed prototype disclaimer text |

**`RouteLeg`**

| Field | Type | Units |
|-------|------|-------|
| `from_label` | str | |
| `to_label` | str | |
| `path` | list[GeoPoint] | |
| `horizontal_distance_m` | float | m |
| `surface_distance_m` | float | m |
| `ascent_m` | float | m |
| `descent_m` | float | m |
| `walk_time_s` | float | s (before margin) |

**`TimelineEntry`**

| Field | Type | Rules |
|-------|------|-------|
| `kind` | TimelineKind | |
| `label` | str | |
| `start_s` | float | From EVA start |
| `duration_s` | float | |

**`RouteTotals`**

| Field | Type | Units |
|-------|------|-------|
| `horizontal_distance_m` | float | m |
| `surface_distance_m` | float | m |
| `walk_time_s` | float | s, before margin |
| `margin_time_s` | float | s |
| `work_time_s` | float | s |
| `total_time_s` | float | s, walk + margin + work |
| `time_available_s` | float | s, `max_eva_hours` × 3600 |
| `reserve_required_s` | float | s |
| `reserve_remaining_s` | float | s, `time_available_s` − `total_time_s` (may be negative) |

**`StatSummary`** = `{max: float | null, mean: float | null, p95: float | null, units: str}`

**`Route`**

| Field | Type | Rules |
|-------|------|-------|
| `route_id` | str | |
| `objective` | RouteObjective | |
| `identical_to?` | str | `route_id` of an identical route from another profile |
| `legs` | list[RouteLeg] | Outbound legs then the return leg |
| `path` | list[GeoPoint] | Full concatenated path |
| `elevation_profile` | list[ProfilePoint] | |
| `slope_stats` | StatSummary | degrees |
| `roughness_stats` | StatSummary | metres |
| `fraction_above_warning_slope` | float | 0–1 of route length |
| `max_distance_from_base_m` | float | |
| `timeline` | list[TimelineEntry] | |
| `totals` | RouteTotals | |
| `safety` | SafetyAssessment | |
| `primary_coverage_fraction` | float | 0–1 of route length |
| `evidence` | list[EvidenceRef] | |
| `limitations` | list[str] | |

**`GridInfo`** = `{analysis_crs: str, cell_size_m: float, rows: int, cols: int}`

### 3.7 Mission State (owned by the frontend store)

**`MissionState`**

| Field | Type | Rules |
|-------|------|-------|
| `mission_id` | str | `msn_` prefix |
| `created_at` | datetime | |
| `name` | str | |
| `region_id` | str | |
| `objective_text` | str | Operator's science objective |
| `base?` | GeoPoint | |
| `destination?` | GeoPoint | |
| `stops` | list[Stop] | Ordered |
| `eva_config` | EvaConfig | Effective configuration |
| `plan?` | RoutePlanResponse | Last plan result, unmodified |
| `selected_route_id?` | str | Must exist in `plan.routes` |
| `envelope?` | EnvelopeResponse | P1 |
| `agent_analysis?` | AgentAnalysisResponse | P1 |
| `notes?` | str | |

The frontend must never edit values inside `plan`, `envelope` or `agent_analysis`.
It replaces them only with new API responses.

---

## 4. Endpoints

Every endpoint lists its tier. All endpoints exist from WP-02 as stubs, so the
OpenAPI schema and generated frontend types are complete from the start. A stub
returns `501 NOT_IMPLEMENTED` until its work package is merged.

### 4.1 `GET /api/v1/health` — P0

Response `HealthResponse`:

| Field | Type |
|-------|------|
| `status` | str (`ok`) |
| `version` | str |
| `llm_mode` | LlmMode |
| `llm_provider` | str \| null |
| `regions_loaded` | int |
| `datasets_available` | int |
| `datasets_unavailable` | int |

### 4.2 `GET /api/v1/regions` — P0

Response: `list[RegionSummary]`.

### 4.3 `GET /api/v1/regions/{region_id}` — P0

Response: `RegionDetail`. Errors: `REGION_NOT_FOUND`.

### 4.4 `GET /api/v1/datasets?region_id=` — P0

Response: `list[DatasetRecord]` for the region (all datasets, including unavailable
ones). Errors: `REGION_NOT_FOUND`.

### 4.5 `GET /api/v1/datasets/{dataset_id}` — P0

Response: `DatasetRecord`. Errors: `DATASET_NOT_FOUND`.

### 4.6 `GET /api/v1/layers?region_id=` — P0

Response: `list[LayerInfo]`. Errors: `REGION_NOT_FOUND`.

### 4.7 `GET /api/v1/layers/{layer_id}/image?region_id=` — P0

Response: `image/png` overlay covering `LayerInfo.bounds`. Errors: `LAYER_NOT_FOUND`,
`LAYER_UNAVAILABLE`, `REGION_NOT_FOUND`.

### 4.8 `GET /api/v1/layers/{layer_id}/features?region_id=` — P0

Response: GeoJSON `FeatureCollection` clipped to the region. Each feature's
`properties` include `dataset_id` and the source attribute fields documented in the
catalog entry. Errors: as 4.7.

### 4.9 `GET /api/v1/terrain/point?region_id=&lat=&lon=` — P0

Response: `PointInspection`. Errors: `REGION_NOT_FOUND`, `POINT_OUTSIDE_REGION`,
`VALIDATION_ERROR`.

### 4.10 `POST /api/v1/terrain/profile` — P0

Request `ProfileRequest`:

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | |
| `points` | list[GeoPoint] | 2–200 vertices of a polyline |
| `sample_spacing_m?` | float | Default: analysis cell size |

Response `ProfileResponse`:

| Field | Type |
|-------|------|
| `samples` | list[ProfilePoint] |
| `total_horizontal_distance_m` | float |
| `evidence` | list[EvidenceRef] |
| `limitations` | list[str] |

Errors: `REGION_NOT_FOUND`, `POINT_OUTSIDE_REGION`, `VALIDATION_ERROR`.

### 4.11 `GET /api/v1/eva/defaults` — P0

Response `EvaDefaultsResponse`:

| Field | Type |
|-------|------|
| `config` | EvaConfig (all fields filled) |
| `assumptions` | list[AssumptionRecord] (one per `EvaConfig` field) |

### 4.12 `POST /api/v1/routes/plan` — P0

Request `RoutePlanRequest`:

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | |
| `base` | GeoPoint | Start and end of the EVA |
| `destination` | GeoPoint | |
| `stops` | list[Stop] | Ordered, 0–8 |
| `objectives?` | list[RouteObjective] | Default: all three |
| `eva_config?` | EvaConfigOverride | Partial overrides |
| `return_to_base?` | bool | Default `true` |

Response `RoutePlanResponse`:

| Field | Type | Rules |
|-------|------|-------|
| `plan_id` | str | `pln_` prefix |
| `region_id` | str | |
| `plan_status` | PlanStatus | |
| `blocking_reason` | str \| null | Required when `plan_status` is not `OK` |
| `routes` | list[Route] | Empty when no route was found |
| `omitted_objectives` | list[`{objective: RouteObjective, reason: str}`] | For example `MAX_SCIENCE` when no science-interest data exists |
| `eva_config` | EvaConfig | Effective configuration used |
| `assumptions` | list[AssumptionRecord] | |
| `grid` | GridInfo | |
| `computed_at` | datetime | |
| `engine_version` | str | |

Rules:
- `NO_FEASIBLE_ROUTE` and `INSUFFICIENT_DATA` are normal `200` responses, not errors.
- Errors: `REGION_NOT_FOUND`, `POINT_OUTSIDE_REGION`, `GRID_TOO_LARGE`,
  `ROUTE_TIMEOUT`, `VALIDATION_ERROR`.

### 4.13 `POST /api/v1/mission/report` — P0

Request: `{mission_state: MissionState}`.

Response `MissionReport`:

| Field | Type | Rules |
|-------|------|-------|
| `report_id` | str | `rpt_` prefix |
| `generated_at` | datetime | |
| `mission_id` | str | |
| `disclaimer` | str | Fixed prototype disclaimer |
| `sections` | list[`ReportSection`] | `{section_id, title, body_markdown, data_class}` in the fixed order of `SCIENCE_AND_SAFETY_SPEC.md` §14.2 |
| `datasets` | list[DatasetRecord] | All datasets referenced |
| `assumptions` | list[AssumptionRecord] | |
| `limitations` | list[str] | |
| `unresolved_issues` | list[str] | |
| `markdown` | str | Complete report as one Markdown document |
| `engine_version` | str | |

Errors: `INVALID_MISSION_STATE` (for example `selected_route_id` not in the plan),
`VALIDATION_ERROR`.

### 4.14 `POST /api/v1/eva/envelope` — P1

Request `EnvelopeRequest`: `{region_id, base: GeoPoint, eva_config?: EvaConfigOverride}`.

Response `EnvelopeResponse`:

| Field | Type |
|-------|------|
| `envelope_id` | str (`env_` prefix) |
| `bounds` | GeoBounds |
| `image_png_base64` | str |
| `reachable_area_km2` | float |
| `max_reach_m` | float |
| `eva_config` | EvaConfig |
| `assumptions` | list[AssumptionRecord] |
| `limitations` | list[str] |
| `computed_at` | datetime |

Errors: as 4.12.

### 4.15 `GET /api/v1/imagery/surface?region_id=&lat=&lon=&radius_m=` — P1

Response: `list[SurfaceImage]` sorted by distance.

**`SurfaceImage`**

| Field | Type | Rules |
|-------|------|-------|
| `image_id` | str | |
| `dataset_id` | str | |
| `mission` | str | |
| `camera` | str | For example `Navcam`, `Mastcam` |
| `product_id` | str | Archive product identifier |
| `sol?` | int | |
| `acquired_at?` | datetime | |
| `point` | GeoPoint | Rover position at acquisition |
| `position_basis` | str | How the position was determined |
| `distance_m` | float | From the query point |
| `image_url` | str | Relative URL of `GET /imagery/surface/{image_id}/file` |
| `caption` | str | |
| `source_url` | str | |
| `data_class` | DataClass | `MEASURED` |

### 4.16 `GET /api/v1/imagery/surface/{image_id}/file` — P1

Response: image bytes. Errors: `IMAGE_NOT_FOUND`.

### 4.17 `POST /api/v1/sites/evaluate` — P1

Request `SiteEvaluationRequest`:

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | |
| `candidates` | list[`{site_id: str, point: GeoPoint, radius_m: float}`] | 1–20 |
| `weights?` | `SiteWeights` | `{terrain, human_safety, science, resources, accessibility}`; must sum to 1.0 ± 0.001 |
| `eva_config?` | EvaConfigOverride | |

Response: `list[SiteEvaluation]`, ranked, with excluded candidates listed last.

**`SiteEvaluation`**

| Field | Type | Rules |
|-------|------|-------|
| `site_id` | str | |
| `point` | GeoPoint | |
| `excluded` | bool | `true` if any hard constraint is violated |
| `hard_constraint_violations` | list[str] | |
| `criterion_scores` | `{terrain, human_safety, science, resources, accessibility}` each float 0–100 \| null | `null` when not evaluable |
| `weighted_score` | float \| null | `null` when excluded or when fewer than three criteria are evaluable. When some criteria are `null`, weights are renormalised and the missing criteria are listed in `uncertainties` (`SCIENCE_AND_SAFETY_SPEC.md` §10.3). |
| `rank` | int \| null | |
| `evidence` | list[EvidenceRef] | |
| `uncertainties` | list[str] | |
| `limitations` | list[str] | |

### 4.18 `POST /api/v1/agents/analyze` — P1

Request: `{mission_state: MissionState, question?: str}`.

Response `AgentAnalysisResponse`:

| Field | Type |
|-------|------|
| `run_id` | str (`run_` prefix) |
| `llm_mode` | LlmMode |
| `agents` | list[`AgentResult`] |
| `synthesis` | `{summary: str, recommendations: list[str], unresolved_issues: list[str], data_class: DataClass}` |
| `computed_at` | datetime |

**`AgentResult`**

| Field | Type |
|-------|------|
| `agent` | str (`coordinator`, `terrain`, `geology`, `thermal`, `resource`, `safety`, `traverse`, `mission`, `synthesis`) |
| `status` | AgentRunStatus |
| `mode` | str (`deterministic` or `llm`) |
| `summary` | str |
| `findings` | list[`Finding`] — `{statement, data_class, evidence: list[EvidenceRef], confidence: ConfidenceLevel}` |
| `warnings` | list[str] |
| `duration_ms` | int |

Rules: an agent may not output any number that does not appear in its tool inputs.
A finding without evidence is rejected by validation.

---

## 5. Endpoint Summary

| Method | Path | Tier | Service owner |
|--------|------|------|---------------|
| GET | `/api/v1/health` | P0 | Orchestrator |
| GET | `/api/v1/regions` | P0 | A1 Data |
| GET | `/api/v1/regions/{region_id}` | P0 | A1 Data |
| GET | `/api/v1/datasets` | P0 | A1 Data |
| GET | `/api/v1/datasets/{dataset_id}` | P0 | A1 Data |
| GET | `/api/v1/layers` | P0 | A2 Geospatial |
| GET | `/api/v1/layers/{layer_id}/image` | P0 | A2 Geospatial |
| GET | `/api/v1/layers/{layer_id}/features` | P0 | A2 Geospatial |
| GET | `/api/v1/terrain/point` | P0 | A2 Geospatial |
| POST | `/api/v1/terrain/profile` | P0 | A2 Geospatial |
| GET | `/api/v1/eva/defaults` | P0 | A4 Routing |
| POST | `/api/v1/routes/plan` | P0 | A4 Routing |
| POST | `/api/v1/mission/report` | P0 | A4 Routing |
| POST | `/api/v1/eva/envelope` | P1 | A4 Routing |
| GET | `/api/v1/imagery/surface` | P1 | A1 Data |
| GET | `/api/v1/imagery/surface/{image_id}/file` | P1 | A1 Data |
| POST | `/api/v1/sites/evaluate` | P1 | A4 Routing |
| POST | `/api/v1/agents/analyze` | P1 | A3 AI |

---

## 6. Errors

All non-2xx responses use this envelope:

```json
{
  "error_code": "POINT_OUTSIDE_REGION",
  "message": "The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp.",
  "details": {"region_id": "gale_mount_sharp"},
  "request_id": "req_3f2a9c1b..."
}
```

| `error_code` | HTTP | Meaning |
|--------------|------|---------|
| `VALIDATION_ERROR` | 422 | Request body or parameters fail validation |
| `REGION_NOT_FOUND` | 404 | Unknown `region_id` |
| `DATASET_NOT_FOUND` | 404 | Unknown `dataset_id` |
| `LAYER_NOT_FOUND` | 404 | Unknown `layer_id` for the region |
| `IMAGE_NOT_FOUND` | 404 | Unknown surface `image_id` |
| `LAYER_UNAVAILABLE` | 409 | Layer exists but its data is unavailable |
| `POINT_OUTSIDE_REGION` | 422 | A point lies outside the region bounds |
| `INVALID_MISSION_STATE` | 422 | `MissionState` is internally inconsistent |
| `GRID_TOO_LARGE` | 422 | Requested route area exceeds `MARSWALK_MAX_GRID_CELLS` |
| `ROUTE_TIMEOUT` | 504 | Routing exceeded `MARSWALK_ROUTE_TIMEOUT_S` |
| `NOT_IMPLEMENTED` | 501 | Endpoint belongs to an unmerged work package |
| `INTERNAL_ERROR` | 500 | Unexpected failure. Details are logged, not returned. |

FastAPI's default validation response is replaced by this envelope.

---

## 7. Configuration (environment variables)

All settings are read by `backend/app/config.py` (pydantic-settings) from the
environment or a `.env` file at the repository root. `.env.example` lists every
variable.

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARSWALK_ENV` | `development` | `development` or `test` |
| `MARSWALK_LOG_LEVEL` | `INFO` | Python log level |
| `MARSWALK_API_HOST` | `127.0.0.1` | Uvicorn bind host |
| `MARSWALK_API_PORT` | `8000` | Uvicorn port |
| `MARSWALK_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `MARSWALK_DATA_DIR` | `backend/data` | Data directory, relative to the repository root |
| `MARSWALK_DEFAULT_REGION` | `gale_mount_sharp` | Region shown at start-up |
| `MARSWALK_MAX_GRID_CELLS` | `4000000` | Analysis grid cap per route request |
| `MARSWALK_ROUTE_TIMEOUT_S` | `20` | Hard timeout for one route plan |
| `MARSWALK_LLM_PROVIDER` | `none` | `none`, `anthropic` or `openai` |
| `MARSWALK_LLM_MODEL` | empty | Required when the provider is not `none` |
| `ANTHROPIC_API_KEY` | empty | Used only when the provider is `anthropic` |
| `OPENAI_API_KEY` | empty | Used only when the provider is `openai` |
| `MARSWALK_AGENT_NODE_TIMEOUT_S` | `30` | Per-agent-node timeout |
| `LANGFUSE_PUBLIC_KEY` | empty | Optional tracing |
| `LANGFUSE_SECRET_KEY` | empty | Optional tracing |
| `LANGFUSE_HOST` | empty | Optional tracing |
| `VITE_API_BASE_URL` | empty | Frontend only (`frontend/.env.local`). Empty means same origin via the Vite dev proxy. |

---

## 8. Data Dictionary (files under `backend/data/`)

### 8.1 `regions/<region_id>.json`

| Field | Type | Rules |
|-------|------|-------|
| `region_id` | str | Matches the file name |
| `name`, `description`, `science_objective` | str | |
| `bounds` | GeoBounds | |
| `analysis` | AnalysisSettings | `primary_dtm_dataset_id` must exist in the catalog |
| `default_base?`, `default_base_basis?` | GeoPoint, str | |
| `layers` | list[`LayerConfig`] | `{layer_id, name, kind, data_type, dataset_ids, derived_from?, render: Legend}` |
| `science_targets` | list[ScienceTarget] | Each must cite evidence |
| `science_interest?` | `{layer_id: str, method: str}` | Optional raster used by the `MAX_SCIENCE` profile |
| `context_sources` | `{radiation?: dataset_id, thermal?: dataset_id}` | |

### 8.2 `manifests/data_sources.json`

List of planned products. Each entry: `{dataset_id, product_id, url, expected_format,
expected_size_bytes?, purpose, selected_because, verified_url_at}`. `verified_url_at`
records when the URL was checked to resolve. No entry may be added without a
resolving URL.

### 8.3 `manifests/dataset_catalog.json`

`{"catalog_version": "1.0", "generated_at": datetime, "datasets": list[DatasetRecord]}`.

### 8.4 `manifests/source_ledger.json`

List of `{file_path, dataset_id, url, retrieved_at, size_bytes, sha256}` for every raw
file.

### 8.5 `manifests/processing_manifest.json`

List of `{output_path, dataset_id, inputs: list[str], steps: list[ProcessingStep],
status, status_reason?}`.

---

## 9. Change Log

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-11-11 | Initial contract set |
| 1.1 | 2026-11-14 | Split EvaConfig into required response model and optional EvaConfigOverride request model (reason: ensure TypeScript types distinguish required response fields from optional request overrides) |
