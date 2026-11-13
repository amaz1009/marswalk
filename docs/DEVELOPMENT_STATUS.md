# MARSWALK — Development Status

This is the single live record of progress. Every agent session reads it first and
updates it after every completed step. If this file and memory disagree, this file wins.

---

## 1. Owner Settings

Only the owner changes these values.

```text
CODE_START_AUTHORISED: YES        # YES once the owner confirms the event allows code before/at this time
REVIEW_MODE: milestone           # milestone = agent merges WPs into develop; owner approves develop → main
                                 # per-wp    = agent opens a PR for every WP into develop and waits
DOWNLOAD_APPROVED: NO            # YES once the owner approves the data download size (WP-06 step 2)
```

---

## 2. Current Checkpoint

Update this block after every step. It is what an interrupted session resumes from.

```text
ACTIVE_WP: none
BRANCH: develop
STEP: —
LAST_COMPLETED: Merged wp/WP-04-frontend-skeleton into develop (status MERGED)
NEXT_ACTION: Awaiting owner direction for next work package
BLOCKERS: none
WAITING_FOR_OWNER: yes — WP-04 merged; awaiting owner direction
UPDATED: 2026-11-14T03:30+05:30
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
| WP-06 | Data download and processing pipeline | P0 | PENDING | wp/WP-06-data-pipeline | — | Needs DOWNLOAD_APPROVED |
| WP-07 | Terrain and hazard engines | P0 | PENDING | wp/WP-07-terrain-engine | — | |
| WP-08 | Region, dataset, layer and terrain APIs | P0 | PENDING | wp/WP-08-layer-api | — | |
| WP-09 | Frontend map, layers and inspector | P0 | PENDING | wp/WP-09-frontend-map | — | Milestone M1 |
| WP-10 | Routing engine | P0 | PENDING | wp/WP-10-routing-engine | — | |
| WP-11 | EVA model, safety checks and route API | P0 | PENDING | wp/WP-11-eva-safety | — | |
| WP-12 | Frontend traverse planner and safety panel | P0 | PENDING | wp/WP-12-frontend-traverse | — | Milestone M2 |
| WP-13 | Mission report | P0 | PENDING | wp/WP-13-mission-report | — | Milestone M3 |
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
| O-5 | Confirm an MSL RAD product for site-level context | OPEN | |
| O-6 | Verify chosen PDS formats open with rasterio's bundled GDAL on Windows | OPEN | |

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
```
