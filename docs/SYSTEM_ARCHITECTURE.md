# MARSWALK — System Architecture

| Field          | Value                                                                       |
|----------------|-----------------------------------------------------------------------------|
| Document       | SYSTEM_ARCHITECTURE.md                                                      |
| Version        | 1.1                                                                         |
| Owner          | Orchestrator                                                                |
| Last updated   | 2026-11-11                                                                  |
| Change control | Changes require Orchestrator approval and an entry in DEVELOPMENT_STATUS.md |

> **Scope disclaimer.** MARSWALK is a research and planning prototype built for the
> NASA Space Apps Challenge 2026. It is not a certified astronaut safety system.
> No output, screen, or report may describe a site or route as "astronaut-safe".
> All outputs are computational assessments under stated assumptions.

**Related documents:** `API_CONTRACTS.md` (interfaces), `SCIENCE_AND_SAFETY_SPEC.md`
(methods and rules), `TESTING_STRATEGY.md`, `IMPLEMENTATION_PLAN.md` (work packages),
`DEVELOPMENT_STATUS.md` (live progress), `GIT_WORKFLOW.md`.

---

## 1. Purpose and Scope

### 1.1 Problem

The NASA Space Apps 2026 challenge "Interplanetary Survival Guide: Martian Map" asks
for a map, tool, or interface that a Mars astronaut could use during a surface
excursion. It should layer data from multiple NASA missions for a specific location
or route at the hyper-local scale of a single EVA. Existing tools (JPL Mars Trek,
USGS geologic maps) do not target this scale. Astronaut safety is the first
priority, and the route should account for spacesuit mobility and avoid significant
obstacles.

### 1.2 What MARSWALK Is

A human-EVA planning system for one Martian region at a time. It answers three
questions separately and never merges them into one opaque score:

1. **Site suitability**: where should the crew operate and do science?
2. **Traverse suitability**: can suited astronauts on foot move between the chosen
   points within the configured constraints?
3. **Mission feasibility**: does the full EVA (out, work, back, reserve) fit the
   time budget (and, in a later version, the consumables budget)?

### 1.3 What MARSWALK Is Not

- Not a rover path planner. Rover data is scientific evidence only.
- Not a live-conditions feed. Historical observations are labelled as historical.
- Not a global map viewer. Global layers provide context only.
- Not a chatbot. AI explains results produced by deterministic engines.

### 1.4 Demonstration Region (provisional)

**Gale Crater, lower Mount Sharp, boxwork-bearing terrain.** It matches the
challenge's own example science objective. It has high-resolution HiRISE and CTX
coverage, and in-situ radiation measurements from MSL RAD.

The region is configuration, not code (ADR-01). It is confirmed after the official
challenge resource list is published (2026-11-13). Exact bounds are fixed in the
region configuration once data products are selected (work package WP-05).

---

## 2. Design Principles (non-negotiable)

| ID | Principle                       | Consequence in the system                                                                                    |
|----|---------------------------------|--------------------------------------------------------------------------------------------------------------|
| P1 | Deterministic numbers           | Elevation, slope, distance, cost, time and consumables come only from tested engine code. LLMs never compute them. |
| P2 | Evidence on everything          | Every value carries its source `dataset_id`(s), its data class (§6.3) and its limitations.                   |
| P3 | Missing data is not safety      | Absent or out-of-coverage data yields `UNKNOWN`, never `PASS`, never zero.                                   |
| P4 | Hard constraints before scoring | A `BLOCKED` result cannot be offset by any weighted score.                                                   |
| P5 | Humans, not rovers              | The traverse model uses human-EVA parameters with cited sources. Rover mobility figures are never used.      |
| P6 | Explicit coordinates            | Each dataset's source CRS is recorded and converted to one internal convention (§6.1).                       |
| P7 | Works without an LLM            | Map, analysis, routing, safety and reports run with no LLM configured. This is the default demo mode.        |
| P8 | Map-centric                     | Every analysis produces something visible on the map.                                                        |
| P9 | Working over decorative         | No control ships unless it is connected to real functionality.                                               |

---

## 3. Architecture Decision Record

| ID     | Decision | Rationale | Alternatives rejected |
|--------|----------|-----------|-----------------------|
| ADR-01 | Region-agnostic design. A region is a JSON config (bounds, analysis CRS, dataset and layer list). | Changing region is a data change, not a code change. | Hard-coding one site. |
| ADR-02 | Primary terrain is a local high-resolution DTM (HiRISE about 1 m post spacing, CTX DTM fallback). MOLA is regional context only. | The challenge asks to avoid obstacles. MOLA gridded data (about 463 m per pixel) cannot resolve them. | MOLA-only routing. |
| ADR-03 | Raster storage is GeoTIFF/COG on the filesystem plus JSON catalogs. No PostGIS in P0. | Removes setup risk. A single region does not need a spatial database. | PostGIS from day one. |
| ADR-04 | 2D map is Leaflet showing degrees in a simple-cylindrical display. 3D (CesiumJS) is P2. | Simple custom-CRS and image-overlay support. Reliable. | MapLibre (Earth-centric defaults), mandatory Cesium. |
| ADR-05 | Routing is deterministic A* on an 8-connected analysis grid, custom implementation (NumPy + heapq). | Full control of cost function, tie-breaking and reproducibility. Fast at our grid sizes. | NetworkX (slow on large grids), LLM-generated routes. |
| ADR-06 | Agents are a LangGraph graph over a registered tool layer. The LLM provider is pluggable (Anthropic default, OpenAI supported). | Structured, testable orchestration. Provider independence. | Free-form agent loops. |
| ADR-07 | The no-LLM deterministic mode is the default. LLM narrative is an optional add-on enabled by environment variables. | Satisfies P7. No API key is available today. The demo cannot fail because of an external API. | LLM-dependent core features. |
| ADR-08 | Shared contracts are Pydantic v2 models in `backend/app/models/`. Frontend types are generated from the OpenAPI schema. | One source of truth. No frontend/backend drift. | Hand-written duplicate TypeScript types. |
| ADR-09 | Raster layers are rendered server-side to PNG overlays with documented colormaps and legends. | Scientific colour control. Small payloads. Simple frontend. | Shipping raw rasters to the browser. |
| ADR-10 | Frontend state is a single mission store (Zustand). | The route on the map is the same object the safety panel and report use. | Prop drilling, multiple sources of truth. |
| ADR-11 | Data download runs on the developer's machine via manifest-driven scripts. | Reproducible acquisition with recorded URLs and checksums. | Manual, unrecorded downloads. |
| ADR-12 | Two user views over one mission state: Mission Control (desktop) and Field View (tablet/HUD). | Fits the challenge's suggested crew formats without duplicating logic. | Separate apps. |
| ADR-13 | Windows 10/11 is the primary development platform. Python packages install from PyPI wheels (rasterio bundles GDAL). Code never imports `osgeo.gdal`. Scripts are PowerShell. Paths use `pathlib`. | The build machine runs Windows. Standalone GDAL bindings are the main Windows install risk. | Conda-only setup, Linux-only scripts. |
| ADR-14 | The demo is a local run plus a recorded video. No hosting. One command starts backend and frontend. Demo data is prepared before recording. | Removes server sizing and data-hosting work. Fits a solo ~39-hour build. | Public hosted deployment. |
| ADR-15 | The backend is stateless in P0. The frontend mission store owns `MissionState` and sends it in full to report and agent endpoints. | No database, no session handling, simple reproducibility. | Server-side mission storage. |
| ADR-16 | Dependency policy: only the libraries listed in `IMPLEMENTATION_PLAN.md` §3. No xarray, NetworkX, PostGIS or direct GDAL bindings in P0. New dependencies need Orchestrator approval. | Fewer install failures and smaller surface for bugs. | Adding libraries ad hoc. |

---

## 4. System Overview

```text
┌──────────────────────────── FRONTEND (React + TS + Vite) ────────────────────────────┐
│  Mission Control view          Field View (tablet / HUD)                             │
│  Leaflet map · Layer panel · Inspector · Traverse planner · Safety · Report          │
│                  └────────── Mission store (Zustand) ──────────┘                     │
└───────────────────────────────────────┬──────────────────────────────────────────────┘
                                        │ REST /api/v1 (JSON, PNG overlays, GeoJSON)
┌───────────────────────────────────────▼──────────────────────────────────────────────┐
│  API LAYER (FastAPI)  request validation · error envelope · OpenAPI                   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  SERVICES  regions · layers · terrain · routes · eva · report · imagery · agents     │
├───────────────────────────────┬──────────────────────────────────────────────────────┤
│  ENGINES (pure Python, no LLM)│  AGENTS (LangGraph, optional LLM)                    │
│  terrain · hazards · routing  │  coordinator → parallel science agents →             │
│  eva · safety · site_selection│  safety → traverse → mission → synthesis             │
│  report                       │  (call services only via the tool registry)          │
├───────────────────────────────┴──────────────────────────────────────────────────────┤
│  DATA LAYER  region configs · dataset catalog · raster/vector loaders · analysis grid │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  STORAGE  data/raw (originals) · data/processed (COG) · data/manifests (JSON)         │
└───────────────────────────────────────┬──────────────────────────────────────────────┘
                                        │ backend/scripts/ (run on developer machine)
                     NASA PDS · HiRISE · CTX · THEMIS · USGS · CRISM · MSL RAD
```

The backend never contacts NASA servers at runtime. All scientific data is
downloaded and processed ahead of time.

---

## 5. Backend Components

### 5.1 Module Responsibilities

| Module | Responsibility | Owner area |
|--------|----------------|------------|
| `app/main.py`, `app/config.py` | App factory, settings from environment, router registration | Orchestrator |
| `app/models/` | Shared Pydantic contracts (see `API_CONTRACTS.md`) | Orchestrator |
| `app/core/` | Error types, error envelope, logging setup | Orchestrator |
| `app/data/` | Region configs, dataset catalog, raster and vector I/O, analysis-grid builder, processing pipeline | A1 Data |
| `app/utils/coordinates.py`, `app/utils/geodesy.py` | Coordinate normalisation and conversion, great-circle distance and bearing on the Mars sphere | A2 Geospatial |
| `app/engines/terrain/` | Sampling, slope, roughness, elevation profiles, hillshade, data-confidence layer | A2 Geospatial |
| `app/engines/hazards/` | Traversability (hazard) grid from terrain and exclusion zones | A2 Geospatial |
| `app/engines/routing/` | Cost surfaces, A*, multi-leg routing, route alternatives | A4 Routing |
| `app/engines/eva/` | Human walking-time model, timeline, walk-back envelope, consumables (P2) | A4 Routing |
| `app/engines/safety/` | Safety checks, context indicators, status aggregation | A4 Routing |
| `app/engines/site_selection/` | Hard-constraint filter plus transparent weighted scoring (P1) | A4 Routing |
| `app/engines/report/` | Deterministic mission report assembly | A4 Routing |
| `app/services/` | Orchestrate engines per use case. Owner matches the engine owner. | A2 / A4 |
| `app/api/routes/` | HTTP endpoints. Owner matches the service owner. | A2 / A4 / A3 |
| `app/agents/` | LangGraph graph, agent nodes, tool registry, LLM adapters, deterministic implementations | A3 AI |
| `backend/scripts/` | Download manifests, download and processing scripts | A1 Data |
| `scripts/` (repo root) | Windows setup and dev-start PowerShell scripts | Orchestrator |
| `backend/tests/`, `frontend/tests/` | Unit tests sit with their module owner. Integration and end-to-end tests belong to QA. | Owner / A6 QA |

### 5.2 Dependency Rules

Allowed import direction (arrows point to permitted dependencies):

```text
api → services → engines → (utils, models, data)
agents → services            (through the tool registry only)
data → (utils, models)
```

- Engines never import `api`, `services` or `agents`.
- Agents never import engines directly. They call registered tools.
- Only `app/data/` reads files under the data directory.
- Only `app/agents/llm/` may import an LLM SDK.

---

## 6. Conventions

### 6.1 Coordinates

| Aspect | Internal convention |
|--------|---------------------|
| Body and datum | Mars, IAU 2000 sphere, R = 3,396,190 m |
| Latitude | Planetocentric, degrees, range [-90, 90] |
| Longitude | East-positive, degrees, range [0, 360) |
| API | All coordinates in requests and responses use the internal convention. Inputs in [-180, 180) are accepted and normalised. |
| Display | The frontend may convert for display only. Leaflet is used for drawing, never for distance calculations. |
| Distances | Great-circle on the sphere for geographic points; metres in the projected analysis CRS for grid operations |
| Slope and roughness | Computed only on rasters in a projected CRS with metre units |

Rules:
- Every loader records the dataset's source CRS (WKT or PROJ string) in the catalog.
- Planetographic latitudes (and west-positive longitudes) are converted on ingestion.
  The original convention is recorded.
- A dataset whose CRS cannot be determined has status `UNAVAILABLE` and is never used.
- Full formulas are in `SCIENCE_AND_SAFETY_SPEC.md` §2.

### 6.2 Units

| Quantity | Unit |
|----------|------|
| Elevation | metres, relative to the stated datum of the source product |
| Distance | metres in engines and APIs; km allowed in UI display only |
| Slope | degrees |
| Time | seconds in engines and APIs; hours and minutes in UI display only |
| Temperature | kelvin (brightness temperature labelled as such) |
| Radiation dose rate | as published by the source (for example µGy/day), units always shown |

### 6.3 Data Classes

Every value presented to the user carries exactly one class:

| Class | Meaning | Example |
|-------|---------|---------|
| `MEASURED` | Direct instrument observation from a source product | THEMIS brightness temperature |
| `DERIVED` | Deterministic computation from measured data | Slope from a DTM |
| `MODEL` | Output of a physical or engineering model | EVA duration estimate |
| `REFERENCE` | Value or location taken from cited literature or mission documentation | A published science-target location |
| `ASSUMPTION` | Configured parameter, with a cited basis where one exists | Maximum allowed slope |
| `SAMPLE` | Synthetic data for tests or fallback, always visibly labelled | Test-fixture DEM |
| `AI_INTERPRETATION` | LLM explanation of evidence | Synthesis narrative |

### 6.4 Identifiers

| Entity | Format | Example |
|--------|--------|---------|
| Region | lowercase snake_case | `gale_mount_sharp` |
| Dataset | UPPERCASE snake_case, instrument first | `HIRISE_DTM_<product>` |
| Layer | lowercase snake_case | `slope_deg` |
| Mission, plan, route, report | prefix + UUID4 hex | `msn_3f2a…`, `rte_9c1b…` |
| Safety check | UPPERCASE snake_case | `SLOPE_MAX` |

---

## 7. Data Architecture

### 7.1 Storage Layout

```text
backend/data/
├── regions/          <region_id>.json — bounds, analysis CRS, datasets, layers, targets
├── raw/              original downloads, never modified (not committed to Git)
├── processed/        clipped, validated Cloud Optimized GeoTIFFs and GeoJSON (not committed)
├── renders/          cached PNG overlays (regenerable, not committed)
├── surface_images/   curated rover images for previews, P1 (not committed)
└── manifests/        committed to Git
    ├── data_sources.json         planned products, URLs, expected sizes (input to download)
    ├── dataset_catalog.json      one entry per dataset (schema in API_CONTRACTS.md §8)
    ├── source_ledger.json        URL, retrieval time, size and SHA-256 per raw file
    └── processing_manifest.json  ordered processing steps per processed file
```

### 7.2 Processing Pipeline

```text
select product → download (checksum) → detect format → extract metadata → validate CRS
→ clip to region → nodata normalisation (NaN, never 0) → unit normalisation
→ write COG / GeoJSON → coverage statistics → catalog entry
```

Each step is recorded in `processing_manifest.json`. A failed step marks the dataset
`UNAVAILABLE` with the reason. It never produces a partial silent output.

### 7.3 Analysis Grid

- Routing and hazard analysis run on a projected grid derived from the primary DTM.
- The cell size is configured per region. The grid size is capped (default 4 million
  cells, `MARSWALK_MAX_GRID_CELLS`). Resampling is recorded as a processing step.
- When the analysis cell is larger than the native DTM post spacing, slope is
  aggregated conservatively (maximum native slope in the cell). See
  `SCIENCE_AND_SAFETY_SPEC.md` §4.4.
- Each cell exposes elevation, slope, roughness, hazard state, data coverage and
  source resolution.

### 7.4 Layer Rendering

- Raster layers are rendered server-side to PNG with a documented colormap, value
  range, units and legend. Overlay pixels must be linear in latitude and longitude;
  rasters in other projections are warped for display (`SCIENCE_AND_SAFETY_SPEC.md` §2.6).
- Vector layers (for example geologic units) are served as GeoJSON clipped to the region.
- Each layer description includes geographic bounds, `dataset_id`(s), data class,
  native resolution and limitations.
- Unavailable layers are listed with their status and reason, and cannot be enabled.

---

## 8. Key Request Flows

### 8.1 Point Inspection

1. The user clicks the map. The frontend sends the point in the internal convention.
2. The terrain service samples every available layer at that point.
3. The response holds one value per layer, each with data class, units, source and
   coverage. An out-of-coverage layer returns `null` with status `NO_COVERAGE`, and
   the derived safety meaning is `UNKNOWN`.

### 8.2 Route Planning

1. Request: base (start), destination, ordered science stops, objectives, `EvaConfig`.
2. Validate that all points are inside the region and on valid primary-DTM cells.
3. Load the analysis grid and build the hazard grid. Cells that break hard limits
   become impassable.
4. For each objective profile (lowest risk, balanced, maximum science), build a cost
   surface and run A* leg by leg (base → stops → destination → base).
5. Compute the return leg as its own search, because uphill and downhill costs differ.
6. Detect duplicates. If two profiles give the same path, keep one route and mark the
   other as identical. Never invent variety.
7. For each route, compute distance, elevation profile, slope and roughness
   statistics, hazard intersections and the EVA timeline (walk, work, margin, reserve).
8. Run safety checks and aggregate the status (§9).
9. If no path exists, return `NO_FEASIBLE_ROUTE` with the blocking reason.

A* is deterministic. Ties break on (f, h, insertion order), so identical inputs always
give identical routes.

### 8.3 Mission Report

Assembled deterministically from `MissionState`. It contains the objective, region,
datasets used (with provenance), selected and alternative routes, metrics, EVA
timeline, safety checks, context indicators, assumptions, limitations, unresolved
items, and the prototype disclaimer. It is returned as structured JSON and as
Markdown. When an LLM is configured, an `AI_INTERPRETATION` narrative section is
added. It cannot change any value or status.

### 8.4 Agent Analysis (P1)

```text
coordinator → [terrain ‖ geology ‖ thermal ‖ resource] → validate
→ safety → traverse → mission → synthesis → final validation → response
```

Each node calls registered tools and writes only its own state field. With no LLM
configured, every node runs its deterministic implementation. Failures and timeouts
degrade to deterministic output and are recorded in `unresolved_issues`.

---

## 9. Safety Architecture

### 9.1 Statuses

| Status | Meaning |
|--------|---------|
| `PASS` | Available data meets the configured prototype criterion |
| `WARNING` | Within hard limits but near a threshold, or the check is non-critical and could not be evaluated |
| `BLOCKED` | A hard configured constraint is violated |
| `UNKNOWN` | The condition cannot be evaluated (missing, out-of-coverage or insufficient data) |

### 9.2 Safety Checks (aggregated)

| Check ID | Critical | Basis |
|----------|----------|-------|
| `SLOPE_MAX` | Yes | Maximum terrain slope along the route vs warning and hard limits |
| `HAZARD_INTERSECTION` | Yes | Verifies the final path crosses no impassable cell (defence in depth) |
| `TERRAIN_DATA_COVERAGE` | Yes | Whether the whole route lies on primary-resolution DTM coverage |
| `EVA_DURATION` | Yes | Total timeline vs `max_eva_hours` |
| `RETURN_RESERVE` | Yes | Total timeline vs the time available after the required reserve |
| `ROUGHNESS` | No | Roughness exposure along the route vs the configured threshold |
| `DISTANCE_FROM_BASE` | No | Furthest route point from base vs the configured walk-back distance |

### 9.3 Context Indicators (not aggregated)

`RADIATION_CONTEXT` and `THERMAL_CONTEXT` present historical observations (MSL RAD,
THEMIS) with their data class and limitations. They are never `PASS`, because
historical orbital or site-level data cannot certify conditions for a future crew.
They are shown beside the safety checks and listed in the report. When data is
missing they are `UNAVAILABLE`.

### 9.4 Aggregation Rule

```text
if any check is BLOCKED                     → BLOCKED
elif any critical check is UNKNOWN          → UNKNOWN  (assessment incomplete)
elif any check is WARNING or UNKNOWN        → WARNING
else                                        → PASS     (prototype criteria only)
```

### 9.5 Enforcement

- Checks run only in `engines/safety/`. Their results are final.
- No API parameter, score or agent output can change a check status.
- The UI never presents a `BLOCKED` route as recommended.
- Exact rules for each check are in `SCIENCE_AND_SAFETY_SPEC.md` §9.

---

## 10. AI Architecture (P1)

| Element | Design |
|---------|--------|
| Orchestration | LangGraph `StateGraph` over a typed agent state derived from `MissionState` |
| Tools | Registry of service functions with Pydantic input and output schemas. Agents can call only these. |
| Default mode | Deterministic. Each agent has a template implementation built from engine outputs. |
| LLM mode | Enabled when `MARSWALK_LLM_PROVIDER` is `anthropic` or `openai` and the matching key is set |
| Output validation | Every agent output is parsed into its Pydantic model. Invalid output → one retry → deterministic fallback. |
| Timeouts | Per-node timeout (`MARSWALK_AGENT_NODE_TIMEOUT_S`). On timeout: deterministic fallback plus an `unresolved_issues` entry. |
| Guardrails | Agents receive engine results as read-only evidence. Synthesis may explain but not change values or statuses. Every finding references a dataset or engine output. |
| Contradictions | If agents disagree, the safety-engine status stands and the disagreement is reported. |
| Observability | Structured logs per node. Langfuse tracing optional via environment variables. |

---

## 11. Frontend Architecture

### 11.1 Views

**Mission Control (desktop, P0)**
- Centre: Leaflet map.
- Left panel: region, layers (legend, units, source, coverage, data class).
- Right panel: point inspector with evidence chain, safety checks, context indicators.
- Bottom drawer: elevation profile, route comparison, EVA timeline.
- Top bar: mission name, coordinate search, LLM mode and data status indicators.

**Field View (tablet / HUD, P1)**
- High-contrast, glanceable view of the selected route.
- Next waypoint, distance and bearing, elapsed time vs walk-back limit.
- Slope ahead, next science stop, rover-eye preview image.
- Reads the same mission store. No independent logic.

### 11.2 Frontend Rules

- All data comes from the API. `SAMPLE` data shows a visible badge.
- TypeScript API types are generated from the backend OpenAPI schema.
- One mission store holds region, layers, selected point, plan, selected route,
  envelope and report.
- Controls without a working backend capability are not rendered.
- Distances and times are always taken from API responses, never computed by Leaflet.

---

## 12. Differentiators

| Feature | Why it stands out | Tier |
|---------|-------------------|------|
| Evidence chain | Click any number to see its dataset, instrument, resolution, processing and data class | P0 |
| Human-EVA traverse model | Walking-time model with cited human-EVA sources, explicitly not rover-based | P0 |
| Three-route comparison with safety status | Risk and science trade-off made visible and explainable | P0 |
| Data-confidence layer | Map of where the analysis is well supported and where it is uncertain | P0 |
| EVA walk-back envelope | Area reachable from base with a return inside the EVA budget | P1 |
| Rover-eye preview | Curiosity surface images near science stops show what the crew will see | P1 |
| Field View (tablet / HUD) | Crew-facing view matching the challenge's suggested formats | P1 |
| Explainable agent briefing | Multi-agent analysis that cites evidence, with deterministic default mode | P1 |
| 3D terrain view | Visual immersion | P2 |

---

## 13. Ownership Matrix

This is a solo build. The six areas below are **module boundaries and the build
order**, not separate people. An agent working on one area changes only that area's
files. Cross-area changes go through the Orchestrator role and are logged.

| Area | Owner | Key paths |
|------|-------|-----------|
| Architecture, contracts, config, docs, root scripts | Orchestrator | `docs/`, `scripts/`, `backend/app/models/`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/core/`, `backend/pyproject.toml` |
| NASA data acquisition and processing | A1 Data | `backend/app/data/`, `backend/scripts/`, `backend/data/` |
| Geospatial computation | A2 Geospatial | `backend/app/utils/`, `backend/app/engines/terrain/`, `backend/app/engines/hazards/` |
| AI and agents | A3 AI | `backend/app/agents/`, `backend/app/api/routes/agents.py` |
| Routing, EVA, safety, sites, report | A4 Routing | `backend/app/engines/{routing,eva,safety,site_selection,report}/` |
| Frontend | A5 Frontend | `frontend/` |
| Integration and validation | A6 QA | `backend/tests/integration/`, `backend/tests/e2e/`, `frontend/tests/e2e/`, `docs/validation/` |

---

## 14. Non-Functional Requirements

| Area | Target (prototype engineering targets, not guarantees) |
|------|---------------------------------------------------------|
| Point inspection | < 300 ms on cached processed data |
| Route planning | < 5 s per request on the configured analysis grid (hard timeout `MARSWALK_ROUTE_TIMEOUT_S`) |
| Layer overlay | < 1 s when cached |
| Reproducibility | Identical inputs give identical routes, metrics and statuses |
| Reliability | Core features run with no LLM and no network access to NASA servers |
| Configuration | All settings via environment variables. `.env.example` documents each one. |
| Secrets | Never committed. API keys read from the environment only. |
| Errors | One error envelope (see `API_CONTRACTS.md` §6). No stack traces in responses. |
| Logging | Structured logs with a request ID. LLM prompts logged only when tracing is enabled. |
| Platform | Windows 10/11 primary; also runs on macOS and Linux. Python 3.11 or 3.12. Node 20 or newer. |
| Startup | One PowerShell command starts backend and frontend (`scripts/dev.ps1`) |

---

## 15. Scope Tiers

| Tier | Includes |
|------|----------|
| P0 | Region config, catalog with provenance, at least three real layers (topography/slope, optical, thermal or geology), point inspection with evidence chain, data-confidence layer, A* human routing with hard constraints, three route profiles, elevation profile, EVA timeline, safety checks, context indicators, mission report |
| P1 (in this order) | Walk-back envelope, rover-eye previews, Field View, LangGraph agents (deterministic default), CRISM mineralogy and MSL RAD context data, site-selection ranking |
| P2 | 3D terrain view, rover-assisted and two-crew EVA modes, SWIM ice layer, tiled high-resolution overlays, operator-drawn exclusion zones, consumables model |

---

## 16. Open Items

| ID | Item | Resolution point | Status |
|----|------|------------------|--------|
| O-1 | Confirm region and data products against the official challenge resources | 2026-11-13, WP-05 | RESOLVED (2026-11-13) |
| O-2 | Select specific HiRISE and CTX DTM products covering the boxwork area | WP-05 | OPEN (Proposal pending owner review) |
| O-3 | Human-EVA defaults are cited in `SCIENCE_AND_SAFETY_SPEC.md` §6. Revisit if better Mars-specific sources are found. | WP-11 | OPEN (Proposal pending owner review) |
| O-4 | Confirm the event rule on writing code before 2026-11-14 | Owner, before WP-01 | OPEN (Proposal pending owner review) |
| O-5 | Confirm an MSL RAD product suitable for site-level context display | WP-18 | OPEN (Proposal pending owner review) |
| O-6 | Verify that the chosen PDS formats open with the GDAL bundled in rasterio wheels on Windows | WP-06 | OPEN (Proposal pending owner review) |

### 16.1 Item Details and Proposed Resolutions (Owner Review Pending)

> [!NOTE]
> The resolutions below are **PROPOSALS** drafted for owner consideration. None are marked resolved; existing architectural decisions remain unchanged until the owner explicitly accepts or rejects each proposal.

#### O-2: Select specific HiRISE and CTX DTM products covering the boxwork area
- **Current Wording:** Select specific HiRISE and CTX DTM products covering the boxwork area (Resolution point: WP-05).
- **PROPOSED Resolution:** Adopt shortlisted and verified HiRISE DTM `DTEEC_001488_1750_001752_1750_U02.IMG` (1 m post spacing, 360.4 MB) and its co-registered orthorectified image `PSP_001752_1750_RED_C_01_ORTHO.JP2` (33.3 MB) for primary terrain and routing, and use the already-verified `USGS_GALE_MERGED_DEM` (product `MSL_Gale_DEM_Mosaic_1m_v3.tif`, optional, 3.87 GB) for regional context. Defer new CTX stereo DTM generation.
- **Reason:** HiRISE provides the necessary 1 m resolution for slope and roughness hazard routing over Mount Sharp boxwork structures, while the verified USGS merged mosaic provides regional Gale Crater coverage; generating custom CTX stereo products during a condensed hackathon introduces unnecessary photogrammetry pipeline risk.

#### O-3: Human-EVA defaults are cited in `SCIENCE_AND_SAFETY_SPEC.md` §6. Revisit if better Mars-specific sources are found.
- **Current Wording:** Human-EVA defaults are cited in `SCIENCE_AND_SAFETY_SPEC.md` §6. Revisit if better Mars-specific sources are found. (Resolution point: WP-11).
- **PROPOSED Resolution:** Retain the default parameters specified in `SCIENCE_AND_SAFETY_SPEC.md` §6.2: `base_speed_kmh` = 2.7 (REFERENCE), `max_slope_deg` = 15 (REFERENCE), `warning_slope_deg` = 10 (REFERENCE), `max_eva_hours` = 6.0 (ASSUMPTION), `roughness_warning_m` = 0.30 (ASSUMPTION), `return_reserve_fraction` = 0.25 (ASSUMPTION), `traverse_time_margin` = 1.25 (ASSUMPTION), `default_work_time_min` = 20 (ASSUMPTION), and `max_distance_from_base_m` = 2000 (REFERENCE). Keep the REFERENCE and ASSUMPTION classification labels; do not treat them as fixed mission rules. The model is Apollo-anchored (REFERENCE) and should be revisited if better Mars-specific sources are found.
- **Reason:** Reflects verified parameter names and classes from `SCIENCE_AND_SAFETY_SPEC.md` §6.2, maintaining transparency on what is reference-derived versus assumed without making unverified claims.

#### O-4: Confirm the event rule on writing code before 2026-11-14
- **Current Wording:** Confirm the event rule on writing code before 2026-11-14 (Resolution point: Owner, before WP-01).
- **PROPOSED Resolution:** The owner confirms the official event rules and schedule times on the event dashboard (risk R-01) before setting `CODE_START_AUTHORISED` to `YES`. Because `develop` is a protected branch, the owner either commits this change directly if authorized or follows `docs/GIT_WORKFLOW.md` (creating a dedicated docs branch such as `wp/WP-00-code-authorisation`, pushing it, and merging into `develop`). Until `CODE_START_AUTHORISED` is set to `YES`, no code work packages may start.
- **Reason:** Ensures verified alignment with event rules before commencing code packages, following proper git workflow for protected branch updates.

#### O-5: Confirm an MSL RAD product suitable for site-level context display
- **Current Wording:** Confirm an MSL RAD product suitable for site-level context display (Resolution point: WP-18).
- **PROPOSED Resolution:** In WP-06, evaluate the MSL RAD collection URL recorded in `DATA_SOURCES.md` (`https://pds-ppi.igpp.ucla.edu/collection/MSL-M-RAD-3-RDR-V1.0`) to inspect available surface RDR tables at Curiosity's Gale Crater traverse stops; specific product IDs and measurement units remain `UNVERIFIED` until WP-06. If table ingestion or coordinate alignment proves infeasible, fall back to marking radiation context as `UNAVAILABLE` with an explicit reason per the WP-18 fallback policy.
- **Reason:** Satisfies the challenge's third data kind guidance as measured point/time-series context without synthesizing data or fabricating an unphysical surface-wide radiation raster.

#### O-6: Verify that the chosen PDS formats open with the GDAL bundled in rasterio wheels on Windows
- **Current Wording:** Verify that the chosen PDS formats open with the GDAL bundled in rasterio wheels on Windows (Resolution point: WP-06).
- **PROPOSED Resolution:** Implement WP-06 Step 1 as an immediate fail-fast smoke test that uses `rasterio.open()` to read a small sub-window from the downloaded HiRISE PDS3 `.IMG` file on Windows. If the rasterio GDAL PDS driver encounters compatibility errors on Windows, the fallback is the verified `USGS_GALE_MERGED_DEM` GeoTIFF (`MSL_Gale_DEM_Mosaic_1m_v3.tif`, 3.87 GB), which uses the standard GTiff driver. In addition, WP-06 may test reading a small window straight from the USGS URL via HTTP range requests before deciding whether to download all 3.87 GB (only if the file really is Cloud-Optimized; marked as untested).
- **Reason:** Validates raster I/O on Windows before investing effort into downstream pipeline transforms, with an already-verified GeoTIFF fallback available.
