# AresNav — Development Status

This is the single live record of progress. Every agent session reads it first and
updates it after every completed step. If this file and memory disagree, this file wins.

---

## 1. Owner Settings

Only the owner changes these values.

```text
CODE_START_AUTHORISED: YES        # YES once the owner confirms the event allows code before/at this time
REVIEW_MODE: milestone           # milestone = agent merges WPs into develop; owner approves develop → main
                                 # per-wp    = agent opens a PR for every WP into develop and waits
DOWNLOAD_APPROVED: YES            # YES once the owner approves the data download size (WP-06 step 2)
```

---

## 2. Current Checkpoint

Update this block after every step. It is what an interrupted session resumes from.

```text
ACTIVE_WP: WP-13
BRANCH: wp/WP-13-mission-report
STEP: small fix round complete (awaits owner commit and gate)
LAST_COMPLETED: WP-13 WARNING wording update and real catalog test assertion
NEXT_ACTION: owner commit of WP-13 backend
BLOCKERS: none
WAITING_FOR_OWNER: no
UPDATED: 2026-11-14T22:30+05:30
```

---

## 3. Status Values

| Status | Meaning |
|--------|---------|
| `PENDING` | Not started |
| `IN_PROGRESS` | Work has started on the WP branch |
| `BLOCKED` | Cannot continue. The reason is in the Blockers section. |
| `IMPLEMENTED` | Code written. Tests not yet all executed and passing. |
| `VERIFIED` | All WP tests and the full suite executed and passing |
| `MERGED` | Merged into `develop` |
| `RELEASED` | Included in `main` through an owner-approved merge |
| `SKIPPED` | Deliberately not done (reason recorded), for example after the cut line |

---

## 4. Work Packages

| ID | Title | Tier | Status | Branch | Tests (passed/failed/skipped) | Notes |
|----|-------|------|--------|--------|-------------------------------|-------|
| WP-00 | Repository bootstrap | — | MERGED | wp/WP-00-bootstrap | — | Owner task completed; rulesets owner-confirmed |
| WP-05 | Data source selection | P0 | MERGED | wp/WP-05-data-sources | — | Shortlist, resources (WP-05b), details (WP-05c), event re-baseline (WP-05d), and demo/thin-slices (WP-05e) merged |
| WP-01 | Backend skeleton | P0 | MERGED | wp/WP-01-backend-skeleton | 5 passed, 0 failed, 0 skipped | Health, error envelope, config implemented |
| WP-02 | Shared models and OpenAPI export | P0 | MERGED | wp/WP-02-shared-models | 18 passed, 0 failed, 0 skipped | All contracts and stubs implemented; openapi.json generated |
| WP-03 | Coordinates and geodesy | P0 | MERGED | wp/WP-03-coordinates | 28 passed, 0 failed in the full backend suite (owner-run, not agent-run) | Mars coordinate conversions, IAU 2000 geodesy, and projection transformer |
| WP-04 | Frontend skeleton and dev scripts | P0 | MERGED | wp/WP-04-frontend-skeleton | owner-run: typecheck exit 0, build exit 0, vitest 14 passed (3 files), scripts/test.ps1 exit 0 (backend pytest 28 passed) | (1) owner exception: backend/pyproject.toml package discovery fix; (2) package.json versions from memory, npm audit 6 dev vulnerabilities accepted; (3) owner-committed due to sandbox .git lock |
| WP-06 | Data download and processing pipeline | P0 | MERGED | wp/WP-06-data-pipeline | owner-run on branch tip fe1a125: full backend suite 45 passed, 0 failed; ruff check clean; ruff format --check clean | (1) Amendment A-1 added to SCIENCE_AND_SAFETY_SPEC section 2.1 (named accepted spheres: Mars 2000 sphere 3396190 m and MOLA product sphere 3396000 m; owner-approved); (2) DTM footprint computed lat -4.948820..-4.720525, lon 137.238928..137.353903; boxwork containment UNKNOWN by design (no cited feature coordinates); (3) 24.6 percent of DTM cells are nodata (NaN) - later routing and safety must treat them as UNKNOWN; (4) DTM vertical datum is UNVERIFIED; MOLA and DTM heights agree roughly (median -3887 m vs -3974 m) but must not be mixed until verified; (5) MOLA grid georeference may be displaced by up to about one 463 m pixel (driver uses 0.463 km MAP_SCALE); (6) sha256 is a catalog-file extension not in the frozen DatasetRecord; (7) docs/openapi.json shows a cosmetic line-ending status in owner working copy only (byte-identical blob to HEAD), nothing committed; (8) MSL RAD sol product IDs and units remain UNVERIFIED (WP-18); (9) teamwork invoked in Fix Round 6 to resolve KeyError regression on real data |
| WP-07 | Terrain and hazard engines | P0 | MERGED | wp/WP-07-terrain-engine | owner-run on branch tip 8ce2026: full backend suite 56 passed, 0 failed (engines: 11 tests); ruff check and format --check clean | (1) Decision D-013 (owner): east-west ground spacing = projected spacing * cos(row latitude), north-south unchanged, no resampling; spec Amendment A-2 in section 4.2. (2) The first WP-07 version computed roughness in float32 with catastrophic cancellation (67 percent of cells came out as exactly 0 on a real 512 x 512 window); fixed by centring and float64; the earlier "verified" wording in the first WP-07 report was wrong because the agent could not run pytest. (3) Only 0.06 percent of valid cells exceed roughness_warning_m = 0.30 m, so that default (open item O-3, an ASSUMPTION) will almost never fire on this DTM; roughness from a 3 x 3, 1 m window is a weak proxy for rocks; decide in WP-11, do not change the default now. (4) 24.78 percent of cells are no data and map to IMPASSABLE_NODATA (code 1); impassable by slope above 15 degrees is 18.42 percent; passable 56.80 percent; NEAR_HAZARD 3.74 percent (hazard encoding 0 passable, 1 nodata, 2 slope, 3 exclusion; confidence 0 none, 1 low, 2 medium, 3 high). (5) Confidence tops out at MEDIUM because geology and THEMIS are UNAVAILABLE in scope A. (6) The analysis grid is 1:1 with the native DTM (cell_size_m 1.0); the block-aggregation path is only tested on synthetic data. (7) Peak memory about 4.3 GB and about 94 s for the full layer generation on the owner's machine (agent-measured). |
| WP-08 | Region, dataset, layer and terrain APIs | P0 | MERGED | wp/WP-08-layer-api | owner-run on branch tip 051d324: full backend suite 81 passed, 0 failed (23 API tests in test_layer_api.py plus 2 provenance guard tests); ruff check clean; ruff format --check clean (72 files); frozen contract diff (docs/openapi.json, backend/app/models) empty | (1) Endpoints implemented: regions list and detail, datasets list and detail, layers list, layer image (PNG) and features (GeoJSON), terrain point and profile; health counts derived from the dataset catalog. (2) POINT_OUTSIDE_REGION returns 422 per API_CONTRACTS section 6 (point and profile). Nodata or no coverage inside the region returns 200 with NO_COVERAGE/UNKNOWN, never 0 or PASS. (3) Latent WP-06 defect found and fixed: the region file evidence block did not validate against the frozen EvidenceRef. (4) The science target in gale_mount_sharp.json is a demonstration waypoint labelled ASSUMPTION (TARGET_01, DEMO_WAYPOINT); its coordinates (-4.780, 137.300) came from WP-06 as an interior demo point and are not supported by any cited source. An earlier invented literature identifier was removed. (5) Layer provenance: confidence lists only HIRISE_DTM_GALE_MOUND and HIRISE_ORTHO_GALE_MOUND (the datasets confidence.py reads); the slope layer is named Terrain Slope (the engine implements Horn 1981 with D-013 ground spacing). (6) Memory: terrain sampling uses windowed reads. Agent-measured tracemalloc peaks (Python heap only, native GDAL memory not included): point inspection 51 KB, full-layer PNG render 3.28 MB. Earlier "15 MB" and "20 KB" figures were unmeasured and retracted. (7) Known limitations and follow-ups: the Legend model has no nodata_value field (hillshade value 0 = nodata is documented in limitations); gale_mount_sharp.json description and science_objective still contain unsupported "boxwork" wording and DEMO_SCENARIO.md line 55 says "Boxwork ridge target" (both for the docs sweep); DTM vertical datum remains UNVERIFIED. |
| WP-09 | Frontend map, layers and inspector | P0 | PENDING | wp/WP-09-frontend-map | — | Milestone M1 |
| WP-10 | Routing engine | P0 | MERGED | wp/WP-10-routing-engine | full backend suite 103 passed, 0 failed (21 routing + 11 terrain + 26 API); ruff clean; benchmarks: 500x500 3.17s/58MB, 1000x1000 13.53s/77MB, 2000x2000 58.40s/151MB | Human walking speed model (Tobler shape [TOBLER1993] scaled to base speed), multi-objective step cost, deterministic A* (octile heuristic, corner cutting prohibition, tie-breaking), search window (25% padding / 500 m min, fallback to full grid, GRID_TOO_LARGE cap), duplicate route detection (identical_to), route statistics, strict CRS transformer and transform validation (both or neither), grid-only synthetic mode; pure ASCII |
| WP-11 | EVA model, safety checks and route API | P0 | MERGED | wp/WP-11-route-service | owner-run on branch tip b27e414: pytest 172 passed, 0 failed, 14 warnings (pyproj PROJ UserWarning only), 121 s; ruff clean; ruff format clean (99 files); frozen contract diff empty; sweeps clean | (1) Grid: fixed 5x aggregation factor (ASSUMPTION, C-01), any-blocked hazard reduction, block-max slope/roughness, block-mean elevation, padding 25% / 500 m min (ASSUMPTION); (2) Snapping (C-03): native-passable only, up to 3 analysis cells, reported in route.limitations, base distance from requested base; (3) Timeout (C-04): ARESNAV_ROUTE_TIMEOUT_S default 30.0 s enforced, partial results with omitted_objectives 'Computation limit:'; sample ~21 s; (4) MAX_SCIENCE omitted in scope A ('no science-interest layer available'); (5) Return leg (C-06): reversed path with directional speed, never 2x outbound; (6) Sample destination (-4.78/137.30) ~2138 m from base yields WARNING; (7) Limitations: absent lon_0 indistinguishable from 0 in pyproj; parallel profiles deferred; (8) Backlog: Affine * in profile.py / test_terrain.py, WP-08 test skips, boxwork wording |
| WP-12 | Frontend traverse planner and safety panel | P0 | PENDING | wp/WP-12-frontend-traverse | — | Milestone M2 |
| WP-13 | Mission report | P0 | IMPLEMENTED | wp/WP-13-mission-report | 31 passed, 0 failed (report unit tests); 125 passed, 0 failed, 12 warnings (full engines suite); owner-run gate pending | Pure deterministic report builder; 12 sections in spec 14.2 order; Section 11 present only with agent_analysis; 9 assumptions synchronized with EVA defaults + override tracking + exact literal assertions; disclaimer verbatim; prohibited-wording parameterized audit; datasets routing layers text; 404/422 errors; full markdown export; genuine synthetic and real Gale e2e tests |
| WP-14 | Walk-back envelope | P1 | PENDING | wp/WP-14-walkback-envelope | — | |
| WP-15 | Rover-eye surface images | P1 | PENDING | wp/WP-15-surface-images | — | |
| WP-16 | Field View | P1 | PENDING | wp/WP-16-field-view | — | |
| WP-17 | Agent system (deterministic default) | P1 | PENDING | wp/WP-17-agents | — | Cut-line candidate |
| WP-18 | MSL RAD and CRISM context data | P1 | PENDING | wp/WP-18-context-data | — | RAD part must-have (cut-line exempt); CRISM part cut-line candidate |
| WP-19 | Site selection | P1 | PENDING | wp/WP-19-site-selection | — | Cut-line candidate |
| WP-20 | QA, integration and test report | P0 | PENDING | wp/WP-20-qa-integration | — | |
| WP-21 | Demo scenario and final documentation | P0 | PENDING | wp/WP-21-demo-docs | — | Milestone M5 |

---

## 5. Milestones

| Milestone | Status | Tag | Approved by owner on |
|-----------|--------|-----|----------------------|
| M0 Docs and data selection | PENDING | v0.0.1 | — |
| M1 Real data on the map | PENDING | v0.1.0 | — |
| M2 End-to-end route | PENDING | v0.2.0 | — |
| M3 P0 complete | PENDING | v0.3.0 | — |
| M4 P1 features | PENDING | v0.4.0 | — |
| M5 Submission | PENDING | v1.0.0 | — |

---

## 6. Open Items

| ID | Item | Status | Resolution |
|----|------|--------|------------|
| O-1 | Confirm region and data products against official challenge resources (2026-11-13) | RESOLVED | Resources review completed 2026-11-13; region confirmed as Gale / Mount Sharp (DATA_SOURCES.md §7) |
| O-2 | Select HiRISE and CTX DTM products for the boxwork area | OPEN | |
| O-3 | Review `roughness_warning_m` and other EVA defaults against region data | OPEN | |
| O-4 | Confirm the event rule on writing code before 2026-11-14 | OPEN | Owner |
| O-5 | Confirm an MSL RAD product for site-level context | OPEN | PDS PPI Node collection URL verified in data_sources.json; sol tables unverified, deferred to WP-18 |
| O-6 | Verify chosen PDS formats open with rasterio's bundled GDAL on Windows | RESOLVED | HiRISE DTM (driver PDS), HiRISE ortho (driver JP2OpenJPEG), and MOLA (driver PDS on label) verified in WP-06 |

---

## 7. Decisions Log

Architecture decisions ADR-01 to ADR-16 are in `SYSTEM_ARCHITECTURE.md` §3. Record
new decisions here.

| ID | Date | Decision | Reason | Affected files |
|----|------|----------|--------|----------------|
| D-001 | 2026-11-11 | Provisional region: Gale Crater / Mount Sharp boxwork | Matches the challenge example; MSL RAD site data; HiRISE coverage | SYSTEM_ARCHITECTURE.md §1.4 |
| D-002 | 2026-11-11 | Solo build; no LLM key; local demo with video; Windows | Owner answers | SYSTEM_ARCHITECTURE.md ADR-07, ADR-13, ADR-14, §13 |
| D-003 | 2026-11-11 | Consumables model and exclusion zones moved to P2 | Fit the solo ~39-hour scope | SYSTEM_ARCHITECTURE.md §15, SCIENCE_AND_SAFETY_SPEC.md §5, §12 |
| D-004 | 2026-11-13 | Region confirmed: Gale Crater / Mount Sharp | Space Apps Resources review confirmed region alignment with NASA-listed USGS mapping; Mars Trek added as candidate | DATA_SOURCES.md §7 |
| D-005 | 2026-11-13 | MSL RAD promoted to required P1 (must-have, cut-line-exempt) | Challenge Details tab suggests at least three data kinds (radiation specified); measured point/time-series context at Curiosity site in Gale; exempt from hour-28 time skip | DATA_SOURCES.md §4, IMPLEMENTATION_PLAN.md §5 |
| D-006 | 2026-11-13 | Re-baseline schedule to ~39 h window and two-stream execution | Real event runs ~39 h (09:00 IST Sat to 23:59 IST Sun); M1 h15, M2 h23, M3 h26, cut line h28, M4 h32, M5 h36; Stream A (backend) and Stream B (frontend worktree) | IMPLEMENTATION_PLAN.md §4 |
| D-007 | 2026-11-13 | Working execution policy Default; switch to Request Review for merges and downloads | The working execution policy is Default; the owner switches the session to Request Review for merges and for the WP-06 data downloads; Turbo is prohibited | IMPLEMENTATION_PLAN.md §4.1 |
| D-013 | 2026-11-14 | East-west metre scale in equirectangular rasters | Ground spacing: dy = |transform.e|, dx_ground = |transform.a| * cos(phi_row) with phi_row = y_row / R computed per row; Amendment A-2 added to spec §4.2 | SCIENCE_AND_SAFETY_SPEC.md §4.2, app/engines/terrain/ |

---

## 8. Blockers and Known Issues

| Date | WP | Issue | Impact | Status |
|------|----|-------|--------|--------|
| — | — | none | — | — |

Live risk tracking (R-01 through R-10) is documented in [docs/RISK_REGISTER.md](RISK_REGISTER.md).

---

## 9. Work Log (append-only, newest last)

Format: `timestamp | WP | step | action | tests (command → passed/failed/skipped) | commit`

```text
2026-11-11T22:50+05:30 | — | — | Documentation package v1 created (architecture v1.1, contracts, spec, testing, plan, status, git workflow) | cross-document consistency script executed → 0 issues; no code tests (documents only) | 535d2ff
2026-11-12T15:05+05:30 | WP-00 | 4 of 4 | Repository bootstrap verified and documented | git remote/branch inspection → verified; rulesets owner-confirmed; no code tests | e36ad30
2026-11-12T15:33+05:30 | WP-00 | 4 of 4 | Merged wp/WP-00-bootstrap into develop (status MERGED) | merge --no-ff verified; no code tests | 15785ea
2026-11-12T17:55+05:30 | WP-05 | 6 of 6 | Provisional data source shortlist and manifest documented | curl header checks (7/7 products HTTP 200/302 verified) → 0 issues; no code tests | afba586
2026-11-12T18:35+05:30 | WP-05 | 6 of 6 | Merged wp/WP-05-data-sources into develop (status MERGED) | merge --no-ff verified; no code tests | be0e368
2026-11-13T16:15+05:30 | WP-05 | review | Space Apps Resources review (2026-11-13) completed; region confirmed as Gale / Mount Sharp | docs consistency check → 0 issues; no code tests (documents only) | d838ece
2026-11-13T16:31+05:30 | WP-05 | review | Merged wp/WP-05b-resources-review into develop (status MERGED) | merge --no-ff verified; no code tests | 368fa4c
2026-11-13T16:45+05:30 | WP-05 | review | Challenge Details tab review completed; MSL RAD promoted to required P1; limitations and fallbacks documented | git/manual inspection → 0 issues; no code tests | 6847e3e
2026-11-13T18:20+05:30 | WP-05 | review | MSL RAD exempted from hour-32 cut line; fallback aligned to infeasibility only | git/manual inspection → 0 issues; no code tests | 1c88e4f
2026-11-13T18:35+05:30 | WP-05 | review | Merged wp/WP-05c-details-review into develop (status MERGED) | merge --no-ff verified; no code tests | a7ca5b4
2026-11-13T19:30+05:30 | WP-05 | rebaseline | Event re-baselined to ~39 h (cut line h28); two-stream execution and RISK_REGISTER.md added; D-006 & D-007 recorded | git/manual inspection → 0 issues; no code tests | 26b71cf
2026-11-13T19:45+05:30 | WP-05 | rebaseline | Clarified execution policy (Default working policy; switch to Request Review for merges/downloads; Turbo prohibited) in docs | git/manual inspection → 0 issues; no code tests | a686def
2026-11-13T19:50+05:30 | WP-05 | rebaseline | Merged wp/WP-05d-event-rebaseline into develop (status MERGED) | merge --no-ff verified; no code tests | ab44268
2026-11-13T20:10+05:30 | WP-05 | demo-and-thin-slices | Risk register updated (R-01/03); thin-slice fallbacks defined; DEMO_SCENARIO.md created; O-2–O-6 proposals drafted | git/manual inspection → 0 issues; no code tests | 2131dc9
2026-11-13T20:16:30+05:30 | WP-05 | demo-and-thin-slices | Refined O-2–O-6 proposals (verified datasets/parameters only) and cleaned DEMO_SCENARIO.md | git/manual inspection → 0 issues; no code tests | 424c3aa
2026-11-13T21:56:30+05:30 | WP-05 | demo-and-thin-slices | Merged wp/WP-05e-demo-and-thin-slices into develop (status MERGED) | merge --no-ff verified; no code tests | [WP-05]
2026-11-14T00:00+05:30 | WP-01 | 5 of 5 | Backend skeleton, config, logging, error envelope, and health endpoint implemented; uvicorn probed | pytest tests/ → 5 passed, 0 failed, 0 skipped | [WP-01]
2026-11-14T00:15+05:30 | WP-01 | 5 of 5 | Merged wp/WP-01-backend-skeleton into develop (status MERGED) | merge --no-ff verified; no code tests | ff6ca03
2026-11-14T00:35+05:30 | WP-02 | 4 of 4 | Shared models, OpenAPI export, stub routers, and test suite implemented | pytest → 15 passed, 0 failed, 0 skipped | [WP-02]
2026-11-14T01:50+05:30 | WP-02 | 4 of 4 | Pre-merge fix: removed defaults from response models, added EvaConfigOverride, updated contract, openapi.json, and tests | ruff check backend scripts → passed; ruff format --check → 12 files passed; export_openapi.py idempotent | [WP-02]
2026-11-14T02:05+05:30 | WP-02 | 4 of 4 | At commit 2cea0eb, ruff check run from backend/ reported E402 in scripts/export_openapi.py; fixed by restoring noqa in this commit; earlier ruff check passed came from run outside backend/ and was wrong; pytest 18 passed was owner-run, not agent-run | cd backend; ruff check . ..\scripts → passed; ruff format --check ..\scripts\export_openapi.py → passed; export_openapi.py idempotent | [WP-02]
2026-11-14T02:08+05:30 | WP-02 | 4 of 4 | Merged wp/WP-02-shared-models into develop (status MERGED) | merge --no-ff verified; no code tests | 0369071
2026-11-14T02:12+05:30 | WP-03 | 0 of 4 | Step 0: reformatted WP-01 config.py and errors.py with ruff format | ruff format app/config.py app/core/errors.py → 2 files formatted | 59b2e6c
2026-11-14T02:18+05:30 | WP-03 | 4 of 4 | Coordinates, normalisation, IAU 2000 geodesy, and equirectangular transformer implemented | cd backend; ruff check . ..\scripts → passed; ruff format --check → 5 files passed; pytest owner-run pending | [WP-03]
2026-11-14T02:28+05:30 | WP-03 | 4 of 4 | Pre-merge fix: added pyproj to pyproject.toml, updated transformer to pyproj.Transformer (WKT-only), corrected 45° test constant | cd backend; ruff check . ..\scripts → passed; ruff format --check → 2 files passed; pytest owner-run pending | [WP-03]
2026-11-14T02:35+05:30 | WP-03 | 4 of 4 | At commit e81eef2 owner-run pytest gave 27 passed, 1 failed (T-COORD-08, non-existent pyproj attribute); fixed in this commit; pyproj pinned to 3.8.0; pytest for this commit owner-run pending | cd backend; ruff check . ..\scripts → passed; ruff format --check → 2 files passed | [WP-03]
2026-11-14T02:40+05:30 | WP-03 | 4 of 4 | Merged wp/WP-03-coordinates into develop (status MERGED) | merge --no-ff verified; owner-run full backend suite on c195f4c: 28 passed, 0 failed | 4113489
2026-11-14T03:30+05:30 | WP-04 | 6 of 6 | Merged wp/WP-04-frontend-skeleton into develop (status MERGED); frontend skeleton, apiClient, store, Mars map shell, dev scripts, and unit tests | owner-run: typecheck exit 0, build exit 0, vitest 14 passed (3 files), scripts\test.ps1 exit 0 (backend pytest 28 passed); dev proxy /api/v1/health returned ok / DISABLED via port 5173 | c49b3ff
2026-11-14T08:30+05:30 | WP-06 | 5 of 5 | WP-06 Fix Round 5 completed: limitations text audit and unverified claim cleanup; owner-run facts recorded: exact download sizes 360402944 / 33256997 / 129761280 bytes, MOLA label 4820 bytes; SHA-256 in source_ledger.json; GDAL PDS driver for DTM, sphere radius 3396190, nodata -3.4028226550889045e+38, 24.6% NaN (75.4% valid), elevation range -4485.57..-2977.08 m; DTM footprint lat [-4.948820, -4.720525], lon [137.238928, 137.353903], boxwork containment UNKNOWN; MOLA opened via label (driver PDS), radius 3396000 via named-sphere registry (Amendment A-1), georeference caveat, MOLA vs DTM median cross-check (-3887 m vs -3974 m); UNAVAILABLE reasons documented in catalog and data_sources; R-02 satisfied; O-5 pointer fixed; sha256 extension; openapi.json cosmetic status verified (byte-identical blob); T-DATA-15 synthetic test added | owner-run backend suite: 42 passed, 0 failed, ruff clean | [WP-06]
2026-11-14T08:55+05:30 | WP-06 | 5 of 5 | Correction: previous WP-06 Round 5 log line overstated the state (pipeline crashed on real data after Round 5; the 42 passed figure predates T-DATA-15; corrected owner-run results will be recorded at merge); fixed process_single_raster bounds return and caller error handling with explicit result shapes; added synthetic regression tests T-DATA-16 and T-DATA-17 | cd backend; pytest tests/unit/data/test_pipeline.py -> 17 passed, 0 failed; ruff clean; full backend suite pending owner-run after Fix Round 6 | [WP-06]
2026-11-14T10:15+05:30 | WP-06 | 5 of 5 | Merged wp/WP-06-data-pipeline into develop (status MERGED); data download and processing pipeline complete; owner-run results on branch tip fe1a125: full backend suite 45 passed, 0 failed; ruff check from backend\ clean; ruff format --check clean; scripts\process_region.py exit 0 with HIRISE_DTM_GALE_MOUND, HIRISE_ORTHO_GALE_MOUND, and MOLA_MEGDR_GALE AVAILABLE and the other five datasets UNAVAILABLE with reasons (supersedes earlier 42 passed figure); download of the three scope-A core files verified by size (360402944 / 33256997 / 129761280 bytes) plus the MOLA label (4820 bytes); SHA-256 values in backend/data/manifests/source_ledger.json; notes (1)-(9) recorded | merge --no-ff verified; owner-run full backend suite on fe1a125: 45 passed, 0 failed | e6c097c
2026-11-14T10:30+05:30 | WP-07 | 1 of 5 | Owner decision D-013 recorded (Option 2: per-row dx_ground = dx_projected * cos(phi_row)); Amendment A-2 added to spec section 4.2; starting implementation of terrain and hazard engines | no code tests yet | [WP-07]
2026-11-14T11:15+05:30 | WP-07 | 2 of 5 | Correction: previous report stated synthetic tests verified engines, but owner-run test suite reported 2 failures (test_d_013 geometry expectation evaluated at row edges instead of row centres, and test_t_terr_03 float32 catastrophic cancellation on tilted planes); resolved by deriving expected ratio from row-centre latitudes and reformulating residual roughness in float64 with local elevation centering and direct residuals; added regression test for realistic Mars elevation offsets (-4000 m); updated layer statistics to report value counts for categorical layers and full/decimated distributions for continuous layers | owner-run backend suite: 53 passed, 2 failed on initial run; fixes verified locally; owner-run pending | [WP-07]
2026-11-14T11:20+05:30 | WP-07 | 5 of 5 | Merged wp/WP-07-terrain-engine into develop (status MERGED); terrain and hazard engines complete; owner-run results on branch tip 8ce2026: full backend suite 56 passed, 0 failed (engines: 11 tests); ruff check and format --check clean; real-data layer statistics from owner read of generated rasters (1/4 decimated, valid cells only): slope percentiles 50/75/90/95/99 = 8.456, 14.7815, 25.416, 32.0, 43.9089 deg, fraction above 10/15/30 deg = 0.4147/0.2449/0.0633; roughness percentiles = 0.0093, 0.0152, 0.0262, 0.0412, 0.1144 m, fraction above 0.05/0.10/0.30 m = 0.0384/0.0132/0.0006; notes (1)-(7) recorded | merge --no-ff verified; owner-run full backend suite on 8ce2026: 56 passed, 0 failed | ba9396e
2026-11-14T12:20+05:30 | WP-08 | 5 of 5 | Region, dataset, layer, and terrain APIs implemented; windowed bilinear and nearest raster sampling; categorical PNG colormapping; exact health counts; col/row affine regression test; pure ASCII verified | cd backend; pytest tests/unit/api/ tests/unit/test_health.py tests/unit/test_models.py tests/unit/engines/ -> 52 passed, 0 failed; ruff check and format clean | [WP-08]
2026-11-14T12:35+05:30 | WP-08 | 5 of 5 | WP-08 fix round: resolved latent WP-06 defect in gale_mount_sharp.json where legacy evidence dict failed validation against frozen EvidenceRef; relabeled unverified demo waypoint from REFERENCE to ASSUMPTION (DEMO_WAYPOINT); removed invented literature claim; updated POINT_OUTSIDE_REGION status code from 400 to 422 per API_CONTRACTS.md section 6; derived health catalog counts dynamically from catalog; added provenance and limitations guard tests | pytest pending owner run; ruff clean; pure ASCII | [WP-08]
2026-11-14T12:45+05:30 | WP-08 | 5 of 5 | Merged wp/WP-08-layer-api into develop (status MERGED); region, dataset, layer and terrain APIs complete; owner-run results on branch tip 051d324: full backend suite 81 passed, 0 failed (23 API tests in test_layer_api.py plus 2 provenance guard tests); ruff check clean; ruff format --check clean (72 files); frozen contract diff empty; notes (1)-(7) recorded | merge --no-ff verified; owner-run full backend suite on 051d324: 81 passed, 0 failed | 42ee9ae
2026-11-14T14:15+05:30 | WP-10 | 5 of 5 | Routing engine and human walking speed model implemented (speed.py, cost.py, astar.py, planner.py); test suite test_routing.py implemented covering T-EVA-01..02 and T-ROUTE-01..12; 100% pure ASCII verified; ruff check clean; ruff format --check clean | cd backend; pytest tests/unit/engines/test_routing.py -> 14 passed, 0 failed; pytest tests/unit/engines/ -> 25 passed, 0 failed; benchmarks: 500x500 (3.1722s, 58.07 MiB), 1000x1000 (13.5270s, 77.40 MiB), 2000x2000 (58.3984s, 151.43 MiB) | [WP-10]
2026-11-14T14:28+05:30 | WP-10 | 5 of 5 | WP-10 fix round: corrected speed model docstring and comments to Tobler hiking function shape [TOBLER1993] per spec section 6.3; removed silent NaN substitution in cost.py; added non-finite guard in planner.py forcing missing elevation/slope/roughness/science to IMPASSABLE_NODATA without caller array mutation; added unit tests test_nan_roughness_on_passable_cell_routed_around, test_nan_roughness_on_route_point_returns_insufficient_data, and test_nan_slope_and_elevation_guard; documented GRID_TOO_LARGE 1 m resolution limitation; verified 0 non-finite cells on 3,197,624 passable cells of real Gale Crater rasters; 100% pure ASCII; ruff check clean, ruff format clean | cd backend; pytest tests/unit/engines/test_routing.py -> 17 passed, 0 failed; ruff check clean; ruff format clean | [WP-10]
2026-11-14T14:55+05:30 | WP-10 | 5 of 5 | WP-10 Fix Round 2: removed numeric parameter defaults in cost.py (max_slope_deg and roughness_warning_m are now required parameters across precompute_cell_cost_factors and compute_normalized_roughness); updated call sites; added test_slope_penalty_scaling_with_max_slope testing slope penalty scaling for max_slope_deg 15 vs 20 with hand derivation (13/9 vs 1.25); replaced test expected values in test_t_eva_01, test_t_eva_02, test_t_route_01, and test_t_route_12 with independently derived literal constants (rel_tol 1e-6); executed real-data routing acceptance check on Gale Crater processed rasters on 401x401 window; ruff check and format clean; 100% pure ASCII | real-data acceptance check completed: Case 1 (enclosed goal) NO_FEASIBLE_ROUTE, Case 2 (contiguous goal) OK (LOWEST_RISK 408 cells/482.39 m, BALANCED 378 cells/463.98 m) | [WP-10]
2026-11-14T15:20+05:30 | WP-10 | 5 of 5 | WP-10 Fix Round 3: removed silent fallback MarsCoordinateTransformer(center_lat=0.0, center_lon=0.0) from planner.py; transform and crs_transformer must be provided together or both None (raises ValueError on mismatch or if GeoPoint inputs given without spatial ref); grid-only mode documented in docstring and marked by geo_referenced=False on PlanOutcome (path_points, full_path_points, elevation_profile empty; max_distance_from_base_m computed via Euclidean grid spacing); added unit tests for spatial ref mismatch, geopoint without spatial ref, and grid-only vs georeferenced modes; documented true ground spacing in plan_routes docstring; 100% pure ASCII; ruff check clean; ruff format clean | cd backend; pytest tests/unit/engines/test_routing.py -> 21 passed, 0 failed; ruff check clean; ruff format clean | [WP-10]
2026-11-14T15:46+05:30 | WP-10 | 5 of 5 | Merged wp/WP-10-routing-engine into develop (status MERGED); terrain-aware A* routing engine and human walking-speed model complete; full backend suite 102 passed, 0 failed; ruff clean; frozen contract diff empty | merge --no-ff verified; full backend suite: 102 passed, 0 failed | 72fa583
2026-11-14T15:47+05:30 | WP-08b | 1 of 1 | Merged wp/WP-08b-layer-perf into develop; cached raster footprints per file version (mtime/size check) in layer_service.py; added regression test test_synthetic_raster_bounds_are_cached; full backend suite 103 passed, 0 failed; ruff clean; frozen contract diff empty | merge --no-ff verified; full backend suite: 103 passed, 0 failed | ec0e287
2026-11-14T17:00+05:30 | WP-RENAME | 1 of 1 | product renamed from MARSWALK to AresNav | checks clean | [WP-RENAME]
2026-11-14T17:28+05:30 | WP-RENAME | merge | Merged wp/rename-aresnav into develop (status MERGED); product renamed MARSWALK to AresNav; owner-run results at 4bd7c47: pytest 130 passed (103 from committed code plus 27 uncommitted WP-11 Part A tests present in local tree), ruff check clean, ruff format --check 87 files already formatted, git diff of backend/app/models empty, git diff of docs/openapi.json title-only; notes (1)-(5) recorded: (1) env vars MARSWALK_* are now ARESNAV_*; (2) openapi title only contract change, schemas/models unchanged; (3) earlier "checks clean" written before owner-run gate; (4) frontend gate runs after merge in frontend worktree; (5) GitHub repo and local folder renames done by owner after merge | merge --no-ff verified; owner-run suite at 4bd7c47: 130 passed, 0 failed | 314fd62
2026-11-14T17:55+05:30 | WP-11 | fix-round | WP-11 Part A Fix Round: spec 9.1 labels updated (0.9 factor, p95, 2 m post-spacing cite spec 9.1, not ASSUMPTION); EVA_DURATION and RETURN_RESERVE partial total rules implemented for return_to_base=False with 3 hand-derived tests; standardized Limitation sentence across all 7 checks with parameterized test; roughness basis text reviewed and synchronized with spec 6.2; T-SAFE-06 belongs to the site-selection WP, not WP-11 | cd backend; pytest tests/unit/engines/test_eva.py tests/unit/engines/test_safety.py -> 35 passed, 0 failed; ruff clean; ruff format clean | [WP-11]
2026-11-14T18:15+05:30 | WP-11 | fix-round-2 | WP-11 Part A Small Fix Round 2: replaced uncatalogued THEMIS_IR_GALE with catalog dataset THEMIS_DAY_IR_GLOBAL; audited all EvidenceRef source_ids against catalog/spec/EvaConfig; made return_to_base a required parameter without default in evaluate_eva_duration and evaluate_return_reserve; verified TypeError on omission; aligned UNAVAILABLE context indicator data_class with catalog (DataClass.MEASURED) | cd backend; pytest tests/unit/engines/test_eva.py tests/unit/engines/test_safety.py -> 36 passed, 0 failed; ruff clean; ruff format clean | [WP-11]
2026-11-14T19:42+05:30 | WP-11 | B2 | Route planning service, conservative 5x analysis grid, endpoint snapping (C-03), directional return leg (C-06), 30s timeout (ARESNAV_ROUTE_TIMEOUT_S default 30.0), API endpoints and test suites implemented | & "backend\.venv\Scripts\python.exe" -m pytest backend\tests\unit\engines\ -> 93 passed, 0 failed; unit suite without TestClient -> 103 passed, 0 failed; ruff check and format clean; frozen contract diff empty | uncommitted
2026-11-14T19:55+05:30 | WP-11 | B2-fix | WP-11 Part B2 Fix Round: test_route_api asserts all 9 spec 6.2 assumptions and structural invariants without hand-typed real-data numbers; test_models removes implemented stubs (defaults, plan_routes) and keeps envelope stub; API/service docstrings synchronized with API_CONTRACTS §4.11; checks.py line-number citations replaced with section 9.1 rule text; astar_search alias removed; Affine * replaced with @; test_timeout_with_no_science_layer added | & "backend\.venv\Scripts\python.exe" -m pytest backend\tests\unit\engines\ -> 94 passed, 0 failed; ruff check and format clean | uncommitted
2026-11-14T17:49+05:30 | — | github | PR #2 merged into main (64036ad); develop back-merged; main = develop = 0f6c52e | GitHub remote merge verified | 64036ad
2026-11-14T20:20+05:30 | WP-11 | merge | Merged wp/WP-11-route-service into develop (status MERGED); owner-run on tip b27e414: pytest 172 passed, 0 failed, 14 warnings (pyproj UserWarning only), 121 s; ruff check clean; ruff format --check clean (99 files); frozen contract diff empty; sweeps clean; commits 1dc7333, 5dd9b30, 4f1578b, b27e414; notes (1)-(8) recorded | merge --no-ff verified; owner-run full suite: 172 passed, 0 failed | 2c14d6b
2026-11-14T21:05+05:30 | WP-13 | 4 of 4 | Mission report backend implementation and unit tests completed; builder.py, report_service.py, mission.py implemented; 18 in-process tests pass; frozen contract diff empty; sweeps clean | & backend\.venv\Scripts\pytest.exe backend\tests\unit\engines\test_report_builder.py -> 18 passed, 0 failed, 1 warning (0.23s); full engines suite 112 passed, 0 failed (68.3s); ruff check and format clean | uncommitted
2026-11-14T21:40+05:30 | WP-13 | fix-round | WP-13 Fix Round completed: spec 14.1 wording updated; builder overall-status sentences for PASS/WARNING/BLOCKED/UNKNOWN synchronized; datasets routing layer text updated; test_nine_assumptions_labels asserts 9 literal values; test_prohibited_wording_audit_r6 parameterized over 10 states; genuine synthetic e2e journey test with temporary EQC rasters; genuine real Gale e2e test with REAL_DATA_EXISTS check; 125 full engine tests pass | cd backend; pytest tests/unit/engines/test_report_builder.py -> 31 passed, 0 failed (21.1s); pytest tests/unit/engines/ -> 125 passed, 0 failed, 12 warnings (88.9s); ruff check and format clean | uncommitted
2026-11-14T22:30+05:30 | WP-13 | small-fix | WP-13 Small Fix Round: WARNING prose in builder.py updated ('No hard safety constraint is violated; advisory conditions were detected... Review is recommended before execution'); test_status_sentence_warning verifies new sentence and absence of 'meets the configured prototype criteria'; test_e2e_real_gale_when_available compares against real region catalog (list_datasets) with UNAVAILABLE reasons; skip-guard proof executed (skipped on fake path, passes on real path); sweeps and contract diff clean | cd backend; pytest tests/unit/engines/test_report_builder.py -> 31 passed, 0 failed (21.9s); ruff check and format clean | uncommitted
```
