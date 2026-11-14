# AresNav — Science and Safety Specification

| Field          | Value                                                                        |
|----------------|------------------------------------------------------------------------------|
| Document       | SCIENCE_AND_SAFETY_SPEC.md                                                   |
| Version        | 1.0                                                                          |
| Owner          | Orchestrator                                                                 |
| Last updated   | 2026-11-11                                                                   |
| Change control | Changes to formulas, defaults or safety rules require Orchestrator approval and a log entry in DEVELOPMENT_STATUS.md |

This document defines every scientific computation, model parameter and safety rule
in AresNav. Engine code implements it exactly. Where a value is not supported by a
source, it is labelled `ASSUMPTION` and exposed to the operator. References are
listed in §15 and cited by key, for example [HORN1981].

---

## 1. Purpose and Principles

- Numbers come from deterministic code (architecture principle P1).
- Missing data is never treated as a pass (P3).
- Hard constraints are applied before any scoring (P4).
- The human-EVA model is built from human data, never from rover data (P5).
- Lunar and Earth sources are used because no suited human walking data exists for
  Mars. Every such use is labelled, and Mars gravity (3.71 m/s², [MARS-G]) is noted
  as a difference that the model does not resolve.

---

## 2. Coordinates and Geodesy

### 2.1 Internal Convention

| Item | Value |
|------|-------|
| Reference body | Mars, IAU 2000 sphere, R = 3,396,190 m [IAU2000] |
| Latitude | Planetocentric, degrees, [-90, 90] |
| Longitude | East-positive, degrees, [0, 360) |
| Internal geographic CRS (PROJ) | `+proj=longlat +R=3396190 +no_defs` |

On a sphere, planetocentric and planetographic latitude are identical. They differ
on the IAU 2000 Mars ellipsoid (a = 3,396,190 m, b = 3,376,200 m) [IAU2000].

**Amendment A-1 (Accepted Source Spheres, owner-approved):**
An accepted sphere's radius (e.g. MOLA MEGDR R = 3,396,000 m) is used solely to
convert projected metres to lon/lat degrees in the source CRS. Angular coordinates
(lon/lat) are radius-independent on a sphere. No metre values from a non-2000
sphere are mixed with analysis-CRS metres.

### 2.2 Longitude Normalisation

```text
validate: -180 <= lon < 360, else reject (VALIDATION_ERROR)
lon_internal = lon mod 360          # result in [0, 360)
```

West-positive source longitudes convert as `lon_east = (360 - lon_west) mod 360`.

### 2.3 Latitude Conversion (ellipsoid-based sources only)

```text
tan(lat_centric) = (b² / a²) · tan(lat_graphic)
tan(lat_graphic) = (a² / b²) · tan(lat_centric)
```

Mandatory rule: **do not rely on PROJ to perform this conversion.** Between two Mars
CRSs with different datums and no defined transformation, PROJ may apply a
"ballpark" transformation that leaves latitude numbers unchanged. For every dataset:

1. Read its base geographic CRS (sphere or ellipsoid) and its latitude type.
2. If it is ellipsoid-based and planetographic, convert latitudes explicitly with the
   formula above, in `app/utils/coordinates.py`.
3. Record the source convention in `DatasetRecord.source_conventions`.

### 2.4 Distance and Bearing

Great-circle distance (haversine) on the sphere:

```text
Δφ = φ2 − φ1,  Δλ = λ2 − λ1   (radians, planetocentric latitude)
h  = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
d  = 2 · R · asin( min(1, sqrt(h)) )
```

Initial bearing (degrees clockwise from north, [0, 360)):

```text
θ = atan2( sin Δλ · cos φ2,  cos φ1 · sin φ2 − sin φ1 · cos φ2 · cos Δλ )
```

Longitude differences are wrapped into (-180°, 180°] before use.

### 2.5 Projected Analysis CRS

- The analysis CRS is the projected CRS of the primary DTM (typically an
  equirectangular projection in metres, as distributed with HiRISE and CTX DTMs).
- Transformations between internal coordinates and the analysis CRS use
  `pyproj.Transformer` with `always_xy=True`, built after the latitude handling in
  §2.3.
- Grid distances (cell size, step length) are in metres in the analysis CRS.
- Each processed raster must round-trip a test point (internal → analysis →
  internal) within half a cell. This is tested.

### 2.6 Map Display

The frontend draws degrees with Leaflet's plate carrée projection (`L.CRS.EPSG4326`)
as a plain equirectangular display. Leaflet's built-in distance, scale bar and
measurement tools assume Earth and are disabled. All distances shown in the UI come
from the API.

Overlay alignment rules:
- A PNG overlay is placed by its latitude/longitude bounds, so its pixels must be
  linear in latitude and longitude. Rasters in an equirectangular (simple
  cylindrical) projection on the Mars sphere meet this directly; their bounds are
  converted to internal coordinates with §2.5.
- Rasters in any other projection (for example polar stereographic) are warped to
  the internal geographic CRS before rendering. The warp is recorded as a
  processing step and used for display only.
- Regions crossing the 0°/360° meridian are not supported by the P0 display.

---

## 3. Units, Nodata and Data Classes

- Units follow `SYSTEM_ARCHITECTURE.md` §6.2.
- Nodata in any source is converted to `NaN` on ingestion. It is never converted to
  `0`. Source nodata values are recorded in the processing manifest.
- Every value carries a data class (`SYSTEM_ARCHITECTURE.md` §6.3).
- Values derived from `NaN` inputs are `NaN`. Statistics ignore `NaN` but report the
  fraction of `NaN` samples.

---

## 4. Terrain Computations

### 4.1 Sampling

| Layer type | Method |
|------------|--------|
| Continuous rasters (elevation, temperature) | Bilinear interpolation. If any of the 4 contributing cells is `NaN`, the result is `NaN`. |
| Categorical rasters and derived class layers | Nearest neighbour |
| Vector layers (geologic units) | Point-in-polygon on the clipped GeoJSON |

### 4.2 Slope (Horn method) [HORN1981]

For a 3×3 window with cells labelled

```text
a b c
d e f
g h i
```

and cell sizes `Δx`, `Δy` in metres:

```text
dz/dx = ((c + 2f + i) − (a + 2d + g)) / (8 · Δx)
dz/dy = ((g + 2h + i) − (a + 2b + c)) / (8 · Δy)
slope_deg = degrees( atan( sqrt( (dz/dx)² + (dz/dy)² ) ) )
```

- If any of the 9 cells is `NaN`, the slope is `NaN`.
- Edge cells of the raster have `NaN` slope.
- Slope is computed at the native resolution of the DTM in its projected CRS.

**Amendment A-2 (East-West Metre Scale, owner-approved D-013):**
Slope and roughness use ground metres: `dx_ground = dx_projected * cos(latitude of the row)`
for equirectangular sources with standard parallel 0; `dy` unchanged; the analysis-CRS
aggregation (section 4.4) then operates on these slopes.

### 4.3 Roughness (residual RMS) [GROHMANN2011]

Roughness separates small-scale relief from overall slope:

1. For each cell, take the k×k window centred on it at native resolution (default
   k = 3).
2. Fit a plane `z = αx + βy + γ` by least squares to the window's elevations.
3. Roughness is the root-mean-square of the residuals, in metres.
4. If any cell in the window is `NaN`, the roughness is `NaN`.

### 4.4 Aggregation to the Analysis Grid

When the analysis cell size is larger than the native post spacing:

| Quantity | Aggregation | Reason |
|----------|-------------|--------|
| Elevation | Mean of valid native cells | Representative surface |
| Slope | **Maximum** native slope in the cell (mean also stored) | Conservative: averaging hides steep local terrain |
| Roughness | **Maximum** native roughness in the cell | Conservative |
| Validity | Cell is valid only if ≥ 90 % of its native cells are valid | Avoids routing over gaps |

The aggregation is recorded as a processing step.

### 4.5 Elevation Profiles

- Samples are spaced along the polyline at `sample_spacing_m` (default: the analysis
  cell size), using great-circle interpolation between vertices.
- Each sample reports cumulative horizontal distance, elevation (bilinear) and slope
  (nearest analysis cell).

### 4.6 Hillshade (display only)

Standard illumination from azimuth 315°, altitude 45° on the analysis grid. It is a
visual aid with data class `DERIVED` and is never used in calculations.

### 4.7 Resolution Limits

| Product | Typical resolution (use the product's own metadata) | Use in AresNav |
|---------|------------------------------------------------------|-----------------|
| MOLA MEGDR, 128 pixels per degree | about 463 m | Regional context only |
| CTX DTM | about 18–24 m post spacing | Fallback terrain, regional slope |
| CTX image | about 5–6 m per pixel | Optical context |
| HiRISE DTM | about 1–2 m post spacing | Primary terrain for routing |
| HiRISE orthoimage | about 0.25–1 m per pixel | Optical detail |
| THEMIS IR | about 100 m per pixel | Thermal context |
| CRISM targeted observation | about 18 m per pixel | Mineralogy context |

Rule (`ASSUMPTION`): features smaller than about three times the DTM post spacing are
not reliably resolved. With a 1 m HiRISE DTM, rocks smaller than about 3 m may not
appear. In addition:
- DTM-derived roughness is a computational proxy for surface obstacles, not an explicit measurement of individual rocks.
- Rock-abundance data (e.g. derived from thermal inertia or boulder distribution models) is not included in the first version.
- Large rock formations, steep overhangs, and sub-pixel obstacles are not guaranteed to be detected.
Every route lists these limitations.

---

## 5. Hazard Grid

Each analysis cell is in exactly one state:

| State | Condition |
|-------|-----------|
| `IMPASSABLE_NODATA` | Elevation or slope is `NaN`, or the cell fails the validity rule in §4.4 |
| `IMPASSABLE_SLOPE` | Slope > `max_slope_deg` |
| `IMPASSABLE_EXCLUSION` | Inside an exclusion polygon (P2: operator-drawn zones; the state exists from P0 so the grid format does not change) |
| `PASSABLE` | Otherwise |

A passable cell is also flagged `NEAR_HAZARD` if it lies within one cell (8-neighbour)
of an impassable cell. This flag feeds the hazard term of the routing cost (§7.2), so
routes keep away from cliff edges and data gaps.

---

## 6. Human EVA Model

### 6.1 Scope

The P0 model estimates walking time for a suited astronaut on foot, plus work time at
stops, a field-time margin and a return reserve. It does not yet model metabolic
rate, consumables, thermal load or dust (see §6.6 and §12, P2).

### 6.2 Default Parameters

These defaults are served by `GET /api/v1/eva/defaults` with the same basis text. The
operator can change every value.

| Parameter | Default | Units | Class | Basis | Citation |
|-----------|---------|-------|-------|-------|----------|
| `base_speed_kmh` | 2.7 | km/h | REFERENCE | Apollo planners assumed 2.7 km/h average speed for walkbacks longer than one hour. Lunar data; Mars gravity differs. | [JONES-GAITS] |
| `max_slope_deg` | 15 | degrees | REFERENCE | A lunar walking-traverse planning study limits slopes to 15°. Lunar data. | [PENA2023] |
| `warning_slope_deg` | 10 | degrees | REFERENCE | The Apollo 14 climb of a ten-degree slope to Cone Crater was the most difficult Apollo walking traverse. | [JONES1989] |
| `max_eva_hours` | 6.0 | hours | ASSUMPTION | Conservative relative to Apollo surface EVAs of about seven hours | [ALSJ] |
| `return_reserve_fraction` | 0.25 | fraction | ASSUMPTION | Prototype planning margin. No validated Mars value. | — |
| `traverse_time_margin` | 1.25 | factor | ASSUMPTION | A field evaluation of an EVA traverse planner found actual traverse times significantly longer than predicted. The factor value itself is an assumption. | [GILKEY2011] |
| `default_work_time_min` | 20 | minutes | ASSUMPTION | Placeholder science time per stop. Set per stop by the operator. | — |
| `max_distance_from_base_m` | 2000 | metres | REFERENCE | The same lunar study restricts walking traverses to within 2 km of the lander. Lunar data. | [PENA2023] |
| `roughness_warning_m` | 0.30 | metres | ASSUMPTION | Uncalibrated. To be reviewed against the region's roughness distribution in WP-11. Reviewed in WP-11 against the Gale Mount Sharp HiRISE DTM roughness layer (native cells): 0.06% of valid cells exceed 0.30 m and the 99th percentile is 0.114 m, so this check rarely triggers; the value remains an uncalibrated assumption. | — |

### 6.3 Walking Speed vs Slope

The shape of the speed–slope relation follows Tobler's hiking function [TOBLER1993],
scaled so that the speed on flat ground equals `base_speed_kmh` (v₀):

```text
S = Δz / Δd_horizontal                  (signed gradient along the step; uphill > 0)
v(S) = v₀ · exp( −3.5 · ( |S + 0.05| − 0.05 ) )      [km/h]
```

Properties:
- `v(0) = v₀`.
- Maximum speed `v_max = v₀ · e^0.175 ≈ 1.19 · v₀` at a gentle downhill (S = −0.05).
  This matches the Apollo observation that crews walked faster downhill [JONES1989].
- At the 15° hard limit uphill (S ≈ 0.268), `v ≈ 0.39 · v₀`.

`ASSUMPTION` label: Tobler's function describes unsuited walking on Earth. Only its
shape is used. The magnitude comes from Apollo data. Neither is validated for Mars.

### 6.4 Step Time

For a step from cell a to neighbour b:

```text
Δd_h = cell_size_m · (1 for orthogonal, √2 for diagonal)
Δz   = z_b − z_a
Δd_s = sqrt(Δd_h² + Δz²)                 (surface distance)
S    = Δz / Δd_h
t    = Δd_s / ( v(S) / 3.6 )             [seconds]
```

Times are direction-dependent, so the outbound and return walks differ.

### 6.5 EVA Timeline

```text
walk_time   = Σ step times along all legs, including the return leg
margin_time = (traverse_time_margin − 1) · walk_time
work_time   = Σ over stops of (stop.work_time_min or default_work_time_min) · 60
total_time  = walk_time + margin_time + work_time
time_available    = max_eva_hours · 3600
reserve_required  = return_reserve_fraction · time_available
reserve_remaining = time_available − total_time
```

The timeline lists entries in route order: WALK (base → stop 1), WORK (stop 1),
WALK (stop 1 → stop 2), WORK (stop 2), …, WALK (last stop → destination), WORK
(destination, if it has a work time), WALK (return leg), then MARGIN and RESERVE.

### 6.6 Not Modelled in P0

Metabolic rate and consumables (P2, §12), suit thermal load, fatigue (covered only by
the margin factor), dust storms, lighting, communication line of sight, carried-mass
effects beyond those embedded in the reference speed. Each is listed as a limitation
on every route.

---

## 7. Routing

### 7.1 Graph

- Nodes: passable analysis cells.
- Edges: 8-connected neighbours, in the fixed order N, NE, E, SE, S, SW, W, NW.
- Diagonal moves are not allowed if either adjacent orthogonal cell is impassable
  (no corner cutting).
- Search window: the bounding box of all route points plus padding of 25 % of the box
  size (at least 500 m), clipped to the region. If no path is found, the search is
  repeated once on the full region grid if it is within `ARESNAV_MAX_GRID_CELLS`.
  Otherwise the response is `GRID_TOO_LARGE`. Limitation: the analysis window can cut
  off detours around obstacles, so `NO_FEASIBLE_ROUTE` means no route within the
  analysis window, not that no route exists.
- Endpoint snapping (ruling C-03): if an endpoint falls on an impassable analysis cell,
  it is snapped up to 3 analysis cells only if the native cell at the requested point is
  passable (code 0).
- Execution timeout: `ARESNAV_ROUTE_TIMEOUT_S` defaults to 30.0 s (measured on the
  owner machine on the Gale Mount Sharp sample at factor 5: LOWEST_RISK 12.3 s,
  BALANCED 9.1 s, 3-profile call 21.3 s). If exceeded, partial routes are returned with
  unfinished profiles in `omitted_objectives` starting with "Computation limit:".

### 7.2 Step Cost

```text
cost(a→b) = t(a→b) · [ 1 + w_s · (σ_b / max_slope_deg)² + w_r · ρ_b + w_h · η_b ] · (1 − w_sci · ι_b)
```

| Symbol | Meaning | Range |
|--------|---------|-------|
| `t(a→b)` | Step time from §6.4 | > 0 s |
| `σ_b` | Terrain slope of cell b (analysis grid, §4.4) | [0, max_slope_deg] |
| `ρ_b` | Normalised roughness: `min(R_b / roughness_warning_m, 2) / 2` | [0, 1] |
| `η_b` | 1 if cell b is `NEAR_HAZARD`, else 0 | {0, 1} |
| `ι_b` | Science interest of cell b (0 when no science-interest layer exists) | [0, 1] |
| `w_sci` | Science weight | [0, 0.5] |

### 7.3 Objective Profiles (`ASSUMPTION`)

| Profile | w_s | w_r | w_h | w_sci |
|---------|-----|-----|-----|-------|
| `LOWEST_RISK` | 3.0 | 2.0 | 2.0 | 0.0 |
| `BALANCED` | 1.0 | 1.0 | 1.0 | 0.25 |
| `MAX_SCIENCE` | 0.5 | 0.5 | 1.0 | 0.5 |

If the region has no science-interest layer, `MAX_SCIENCE` is omitted with the reason
"no science-interest layer available", and `BALANCED` uses `w_sci = 0`. Stops chosen
by the operator are always visited, whatever the profile.

### 7.4 Heuristic (admissible and consistent)

Every multiplier in §7.2 is at least `(1 − w_sci)`, and `t ≥ Δd_h / v_max`. Therefore:

```text
h(n) = D_octile(n, goal) · (1 − w_sci) / (v_max / 3.6)
D_octile = cell_size_m · ( max(|Δi|, |Δj|) + (√2 − 1) · min(|Δi|, |Δj|) )
```

`h` never overestimates the remaining cost, so A* returns an optimal path for the
given cost function.

### 7.5 Determinism

- Priority-queue key: `(f, h, insertion_counter)`.
- Neighbour order is fixed (§7.1).
- Floating-point costs are computed in `float64`.
- Identical inputs and data give identical paths. This is tested.

### 7.6 Legs and Return

1. Legs are searched in order: base → stop 1 → … → destination.
2. If `return_to_base` is true, the return leg destination → base is a separate
   search with the same profile.
3. If any leg fails, the plan status is `NO_FEASIBLE_ROUTE` and the failing leg is named.

### 7.7 Duplicate Routes

If two profiles produce exactly the same cell sequence for all legs, the later
profile's route has `identical_to` set to the earlier route's ID. Both are returned.
The UI shows them as one route under two objectives.

### 7.8 Route Statistics

- `slope_stats`, `roughness_stats`: over path cells (max, mean, 95th percentile).
- `fraction_above_warning_slope`: share of horizontal route length on cells with
  slope above `warning_slope_deg`.
- `max_distance_from_base_m`: largest great-circle distance (§2.4) from base to any
  path cell centre.
- `primary_coverage_fraction`: share of route length on cells whose terrain comes from
  the primary DTM.

---

## 8. Walk-Back Envelope (P1)

1. Use walk time only (§6.4), no risk weights, and the same impassable rules (§5).
2. Run Dijkstra from the base on the forward graph: `T_out(c)` is the minimum walk
   time from base to cell c.
3. Run Dijkstra from the base on the reversed graph, where each edge c→n takes the
   step time of walking from c to n: `T_back(c)` is the minimum walk time from c back
   to base.
4. Required time for an out-and-back visit with one stop:
   `T_req(c) = traverse_time_margin · (T_out(c) + T_back(c)) + default_work_time_min · 60`.
5. Classify each cell:
   - `WITHIN_BUDGET`: `T_req ≤ (1 − return_reserve_fraction) · time_available`
   - `USES_RESERVE`: `T_req ≤ time_available` but above the previous limit
   - `OUT_OF_REACH`: otherwise, or unreachable
6. Render the classes as a PNG overlay. Report `reachable_area_km2` (cells within
   budget) and `max_reach_m` (largest great-circle distance from base among cells
   within budget).

---

## 9. Safety Checks

### 9.1 Check Rules

Checks are evaluated in this order for every route. All seven are always present.

| Check ID | Critical | Value | Threshold | Rule |
|----------|----------|-------|-----------|------|
| `SLOPE_MAX` | Yes | Max slope on path cells (deg) | `warning_slope_deg`, `max_slope_deg` | UNKNOWN if any path-cell slope is NaN; BLOCKED if value > max; WARNING if value > warning; else PASS |
| `HAZARD_INTERSECTION` | Yes | Number of impassable path cells | 0 | UNKNOWN if the hazard grid is unavailable; BLOCKED if value > 0; else PASS |
| `TERRAIN_DATA_COVERAGE` | Yes | `primary_coverage_fraction` | 1.0 | UNKNOWN if it cannot be computed; WARNING if value < 1.0; WARNING if the primary DTM post spacing is > 2 m; else PASS |
| `EVA_DURATION` | Yes | `total_time_s` | `time_available` | UNKNOWN if the total cannot be computed; BLOCKED if value > threshold; else PASS |
| `RETURN_RESERVE` | Yes | `total_time_s` | `time_available − reserve_required` | UNKNOWN if not computable; BLOCKED if value > threshold; WARNING if value > 0.9 × threshold; else PASS |
| `ROUGHNESS` | No | 95th percentile roughness on path (m) | `roughness_warning_m` | UNKNOWN if roughness is unavailable; WARNING if value > threshold; else PASS |
| `DISTANCE_FROM_BASE` | No | `max_distance_from_base_m` | config `max_distance_from_base_m` | WARNING if value > threshold; else PASS |

Every check message also states the relevant limitation. For example, `SLOPE_MAX`
notes the DTM resolution and that obstacles smaller than about 3× post spacing may
not be resolved.

### 9.2 Aggregation

```text
if any check is BLOCKED                     → BLOCKED
elif any critical check is UNKNOWN          → UNKNOWN  (assessment incomplete)
elif any check is WARNING or UNKNOWN        → WARNING
else                                        → PASS     (prototype criteria only)
```

No score, objective, API parameter or agent output can change a check status or the
overall status.

### 9.3 Context Indicators (not aggregated)

| Indicator | Source | Content | Never claims |
|-----------|--------|---------|--------------|
| `RADIATION_CONTEXT` | MSL RAD surface observations (region `context_sources.radiation`) | Published dose-rate summary, observation period, units | A forecast, a dose for a future crew, or applicability to other sites without modelling |
| `THERMAL_CONTEXT` | THEMIS IR along the route | Range of brightness temperatures and the local time of observation | Air temperature, suit environment, or current conditions |

Status is `AVAILABLE` or `UNAVAILABLE`. When unavailable, the indicator says so and
the report lists the gap.

---

## 10. Site Selection (P1)

### 10.1 Hard Constraints (applied first)

A candidate is excluded if any of these hold:

1. The candidate centre cell is impassable.
2. Less than 50 % of cells within `radius_m` are passable (`ASSUMPTION`).
3. Less than 90 % of the disc has valid primary-DTM data.

Excluded candidates get no weighted score and are listed with their violations.

### 10.2 Criterion Scores (0–100)

| Criterion | Formula | `null` when |
|-----------|---------|-------------|
| `terrain` | `100 · (1 − min(mean_slope / max_slope_deg, 1))` | No valid slope in the disc |
| `human_safety` | `100 · passable_fraction · (1 − fraction_above_warning_slope)` | No valid slope |
| `science` | `100 · mean(ι)` if a science-interest layer exists; else `100 · min(1, targets_in_disc / 3)` if the region has targets | Neither is available |
| `resources` | `100 · mean(resource indicator)` | No resource or ice layer is configured (P2) |
| `accessibility` | `100 · (1 − min(T_one_way / (0.5 · (1 − r) · time_available), 1))`, BALANCED profile from the region default base | No default base, or no route |

### 10.3 Weighting (`ASSUMPTION`, prototype values, not NASA criteria)

| Criterion | Default weight |
|-----------|----------------|
| `terrain` | 0.30 |
| `human_safety` | 0.25 |
| `science` | 0.20 |
| `resources` | 0.15 |
| `accessibility` | 0.10 |

- Weights must sum to 1.0.
- If some criteria are `null`, the remaining weights are renormalised to sum to 1.0,
  and each `null` criterion is listed in `uncertainties`.
- If fewer than three criteria can be evaluated, `weighted_score` is `null`.
- Individual criterion scores are always reported alongside the weighted score.

---

## 11. Data-Confidence Layer

Per analysis cell:

| Level | Condition |
|-------|-----------|
| `HIGH` | Valid primary-DTM slope at ≤ 2 m post spacing, optical coverage, and thermal or geology coverage |
| `MEDIUM` | Valid DTM slope at any resolution and at least one other layer |
| `LOW` | Only regional context data, or DTM without any other layer |
| `NONE` | No valid terrain data |

The layer has data class `DERIVED` and its legend explains each level.

---

## 12. Consumables Model (P2 requirements)

Before implementation, the work package must:

1. Select a published metabolic-rate model for loaded walking on slopes, for example
   the Pandolf load-carriage equation [PANDOLF1977]. EVA traverse planners such as
   SEXTANT optimise traverses on metabolic cost [JOHNSON2010].
2. Document every coefficient and its source in this section.
3. Label the result `MODEL`, state that the equation was derived under Earth gravity,
   and state that it has not been validated for suited walking on Mars.
4. Compare consumption only against operator-configured budgets. Staying below a
   nominal budget is never reported as "safe".

---

## 13. Radiation, Thermal and Space Weather

- MSL RAD measured the radiation environment at the Curiosity site in Gale Crater.
  AresNav presents it as historical, site-level context (§9.3).
- THEMIS brightness temperature is an orbital measurement of the surface at the time
  of observation. It is not air temperature and not current.
- Heliospheric space-weather records (for example NASA DONKI) describe solar events,
  not conditions on the Martian surface. If added, they are labelled accordingly.
- No component may present historical data as live or current Martian conditions.

---

## 14. Wording Rules and Report Structure

### 14.1 Wording Rules (UI, reports, agent output)

| Do not write | Write instead |
|--------------|---------------|
| "safe route", "safe site", "astronaut-safe" | "meets the configured prototype criteria" |
| "guaranteed", "certified", "approved" | (omit) |
| "current conditions", "live data" | "historical observations from <instrument>, <period>" |
| A number without units or source | Number + units + data class + source |

Fixed disclaimer text (used verbatim in `SafetyAssessment.disclaimer` and reports):

> AresNav is a research and planning prototype. Results are computational
> assessments under stated assumptions and are not a certified astronaut safety
> analysis.

### 14.2 Report Sections (fixed order)

| Order | `section_id` | Content |
|-------|--------------|---------|
| 1 | `overview` | Mission name, region, objective, generation time, engine version |
| 2 | `science` | Science objective and targets with evidence |
| 3 | `datasets` | Provenance table of all datasets used |
| 4 | `terrain` | Terrain summary along the selected route |
| 5 | `selected_route` | Metrics of the selected route, or "No route selected" |
| 6 | `eva_timeline` | Timeline table |
| 7 | `safety` | All checks, overall status and context indicators |
| 8 | `alternatives` | Comparison table of all routes |
| 9 | `assumptions` | Every assumption with basis and citation |
| 10 | `limitations` | Limitations and unresolved issues |
| 11 | `ai_interpretation` | Present only when an LLM is configured, labelled `AI_INTERPRETATION` |
| 12 | `disclaimer` | Fixed disclaimer |

---

## 15. References

| Key | Reference |
|-----|-----------|
| [ALSJ] | Jones, E. M. & Glover, K. (eds.). *Apollo Lunar Surface Journal.* NASA History Office. |
| [GILKEY2011] | Gilkey, A., Kobrick, R., Galvan, R., Johnson, A., Hoffman, J., Newman, D., Melo, P. (2011). Evaluation of a Surface Exploration Traverse Analysis and Navigation Tool. *41st International Conference on Environmental Systems.* AIAA. https://dspace.mit.edu/handle/1721.1/81410 |
| [GROHMANN2011] | Grohmann, C. H., Smith, M. J., Riccomini, C. (2011). Multiscale analysis of topographic surface roughness in the Midland Valley, Scotland. *IEEE Transactions on Geoscience and Remote Sensing*, 49(4), 1200–1213. |
| [HORN1981] | Horn, B. K. P. (1981). Hill shading and the reflectance map. *Proceedings of the IEEE*, 69(1), 14–47. |
| [IAU2000] | Seidelmann, P. K. et al. (2002). Report of the IAU/IAG Working Group on Cartographic Coordinates and Rotational Elements of the Planets and Satellites: 2000. *Celestial Mechanics and Dynamical Astronomy*, 82, 83–111. |
| [JOHNSON2010] | Johnson, A., Hoffman, J., Newman, D., Mazarico, E., Zuber, M. (2010). An Integrated Traverse Planner and Analysis Tool for Planetary Exploration. *AIAA SPACE 2010 Conference & Exposition.* https://dspace.mit.edu/handle/1721.1/81322 |
| [JONES1989] | Jones, E. M. (1989). *Working on the Moon: The Apollo Experience.* Los Alamos National Laboratory, LA-UR-89-3858. https://www.osti.gov/servlets/purl/7168757 |
| [JONES-GAITS] | Jones, E. M. "Lunar Gaits." *Apollo 11 Lunar Surface Journal.* NASA. https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11.gaits.html |
| [MARS-G] | Mars mean surface gravity ≈ 3.71 m/s² (NASA Mars Fact Sheet, https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html) |
| [PANDOLF1977] | Pandolf, K. B., Givoni, B., Goldman, R. F. (1977). Predicting energy expenditure with loads while standing or walking very slowly. *Journal of Applied Physiology*, 43(4), 577–581. |
| [PENA2023] | Peña-Asensio, E. et al. (2023). Automated astronaut traverses with minimum metabolic workload: Accessing permanently shadowed regions near the lunar south pole. *Acta Astronautica.* doi:10.1016/j.actaastro.2023.10.010 |
| [TOBLER1993] | Tobler, W. (1993). *Three Presentations on Geographical Analysis and Modeling.* NCGIA Technical Report 93-1. |
