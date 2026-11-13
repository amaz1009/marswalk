# MARSWALK — Demo Scenario and Video Script

| Field          | Value                                                         |
|----------------|---------------------------------------------------------------|
| Document       | docs/DEMO_SCENARIO.md                                         |
| Version        | 1.0 (Draft)                                                   |
| Target Format  | 3 to 4 minute recorded video walkthrough                      |
| Region         | Gale Crater / Mount Sharp (Aeolis Mons) boxwork structure     |
| Last Updated   | 2026-11-13                                                    |

---

## 1. Required Pre-Event Disclosure

This exact disclosure statement must be included in the submission documentation, README, and video introduction:

> **Disclosure:** In accordance with NASA Space Apps Challenge rules, architectural plans, API contracts, scientific specifications, and data manifests were drafted prior to the event; all application code, data processing pipelines, and user interfaces were developed during the official hackathon window.

---

## 2. Video Walkthrough Script (Viewer Sequence)

> **Scientific Integrity Rule:** All numbers, coordinates, measurements, and timestamps below are placeholders (`[...]`). Real values come strictly from deterministic pipeline outputs generated during the hackathon. Never invent measured values.

### Scene 1: Introduction & Map Initialization in Gale Crater (0:00 – 0:30)
- **Visual:** Browser opens to MARSWALK Mission Control view. The viewport centers on Mount Sharp within Gale Crater (`[CENTER_LAT]°, [CENTER_LON]°`).
- **Narrator Audio:**
  *"Welcome to MARSWALK, an EVA traverse planning prototype developed for the NASA Space Apps Challenge. MARSWALK helps mission operators and astronauts design safe, science-optimized surface traverses on Mars using authentic NASA planetary datasets. Here in Gale Crater, we focus on the Mount Sharp boxwork structures investigated by the Curiosity rover."*
- **Action:** Pan across the high-resolution HiRISE optical basemap (`[HIRISE_PRODUCT_ID]`).

### Scene 2: Layer Exploration & Environmental Context (0:30 – 1:00)
- **Visual:** Operator toggles layers in the Layer Control drawer:
  1. **HiRISE 1 m DTM:** Displays localized digital elevation model (`[ELEV_MIN] m` to `[ELEV_MAX] m`).
  2. **Slope Map:** Server-rendered colormap showing gradients (`[0° to MAX_SLOPE°]`).
  3. **Roughness / Hazard Layer:** Terrain roughness proxy indicating potential rover/suit obstacles.
  4. **USGS Regional 50 m DEM:** Broader regional context across Gale Crater.
  5. **MSL RAD Surface Radiation:** Point and time-series context indicator at Curiosity's traverse location (`[RAD_DOSE_RATE] µGy/day` or `[STATUS]`).
- **Narrator Audio:**
  *"MARSWALK integrates multiple independent data kinds: 1-meter topography and roughness derived from MRO HiRISE stereo pairs, regional context from USGS elevation models, and environmental radiation measurements from Curiosity's MSL RAD instrument. Notice that radiation is reported strictly as localized measured history—we never fabricate an artificial surface-wide raster."*

### Scene 3: Terrain Point Inspector (1:00 – 1:25)
- **Visual:** Operator clicks on a potential traverse waypoint on the map. The Inspector panel pops out.
- **Data Displayed:**
  - Coordinate: `[CLICK_LAT]°, [CLICK_LON]°`
  - Elevation: `[ELEV_POINT] m`
  - Slope: `[SLOPE_POINT]°` (Status: `[PASS / WARNING / HARD_LIMIT]`)
  - Roughness: `[ROUGHNESS_POINT] m`
  - Data Provenance: `HiRISE DTM [PRODUCT_ID], PDS3 IMG, 1.0 m/px`
- **Narrator Audio:**
  *"Every point on the canvas provides full data provenance and scientific traceability. Operators can inspect slope, elevation, and terrain roughness with documented sensor lineage."*

### Scene 4: Traverse Planning & Parameter Setup (1:25 – 1:55)
- **Visual:** Operator sets EVA parameters in the Planning Panel:
  - Start Location: Landing Hab site at `[START_LAT]°, [START_LON]°`
  - Science Destination: Boxwork ridge target at `[DEST_LAT]°, [DEST_LON]°`
  - Maximum EVA Budget: `[e.g. 6.0 h]`
  - Crew Walking Speed: `[2.7 km/h]` (Apollo walkback benchmark)
  - Hard Slope Threshold: `[20°]` (per NASA EVA standards)
  - Warning Slope Threshold: `[15°]`
- **Action:** Operator clicks **Calculate Traverses**.

### Scene 5: Route Calculation & Multi-Profile Comparison (1:55 – 2:30)
- **Visual:** The backend A* routing engine computes the path in `[< 5.0 s]`. Two routes appear on the map:
  1. **Direct Path (Baseline):** Straight-line path between start and target (`[DIST_DIRECT] km`).
  2. **Safe EVA Route (Primary):** Terrain-following least-cost path contouring around steep slopes (`[DIST_SAFE] km`, elevation gain `[ELEV_GAIN] m`, estimated time `[EST_TIME] h:mm`).
- **Visual:** Elevation profile graph below map updates, showing grade profiles and warning zones.
- **Narrator Audio:**
  *"MARSWALK calculates routes using deterministic cost functions that penalize steep terrain. Here, the direct path violates our 20-degree hard slope limit across ridge faces. The planned EVA route negotiates the topography, keeping all segments below the hard constraint."*

### Scene 6: Safety Panel & Constraint Verification (2:30 – 3:00)
- **Visual:** Safety Panel displays the constraint checklist:
  - **Hard Slope Limit (≤ 20°):** `[PASS — Max slope on route: SLOPE_MAX°]`
  - **Warning Slope (≤ 15°):** `[PASS or WARNING — WARN_PCT% in warning zone]`
  - **Roughness Warning (≤ 0.3 m):** `[PASS or UNAVAILABLE]`
  - **Timeline Budget:** `[EST_TIME] h` / `[MAX_TIME] h` (`[TIME_REMAINING] h margin`)
  - **Walk-Back Envelope:** Walk-back return margin verified at all waypoints (`[MARGIN_MIN] min`).
  - **Radiation Context:** In-situ Curiosity environmental level: `[LEVEL]`.
- **Narrator Audio:**
  *"In accordance with NASA flight rules, safety constraints are non-negotiable hard boundaries that are never averaged against science scores. Notice our terminology adherence: we report 'no safety rule violations detected' rather than making absolute claims of safety."*

### Scene 7: Mission Report Generation (3:00 – 3:30)
- **Visual:** Operator clicks **Generate Mission Report**. A structured report modal opens containing:
  - Header with route ID, timestamp, and CRS definition (`IAU_2015:49900`).
  - Turn-by-turn waypoint table with cumulative distance, cumulative time, and waypoint coordinates.
  - Mandatory Scientific Limitations & Disclosures (Apollo speed analog caveats, roughness proxy notes, DEM resolution limits).
- **Action:** Operator downloads report as Markdown/PDF.

### Scene 8: Optional P1 Features / Closing (3:30 – 4:00)
- *(If implemented)*:
  - **Field View (WP-16):** Switch to high-contrast astronaut HUD view showing next waypoint bearing, distance, and slope ahead.
  - **Rover Imagery (WP-15):** Preview nearest Curiosity ground-level Mastcam frames at waypoint `[WP_INDEX]`.
  - **Automated Briefing (WP-17):** Deterministic natural language crew briefing summary.
- **Narrator Audio:**
  *"MARSWALK demonstrates how planetary data pipelines, deterministic routing, and human EVA physiology models come together to safeguard future Martian explorers. Thank you."*

---

## 3. If a Feature Was Cut (Honest Phrasing)

If specific P1 features were excluded at the Hour 28 cut line, use the following exact and honest wording in the video and final report:

| Feature Cut | Honest Script & Report Phrasing |
|-------------|---------------------------------|
| **CRISM Mineralogy** | *"CRISM hyperspectral mineralogy was excluded at our development cut line. Mineralogical context remains documented as a candidate layer in our data manifest, and all terrain decisions rely on verified HiRISE and USGS data products."* |
| **LLM Narrative Generation** | *"The crew briefing is generated by our deterministic rules engine. External LLM integration was omitted by design to guarantee 100% reproducible and verifiable safety outputs with zero hallucination risk and no external network dependency."* |
| **Site Selection (WP-19)** | *"Automated site selection was scoped to manual candidate waypoint placement. Multi-criterion algorithmic ranking matrices were deferred to maintain focus on the core routing and safety verification engine."* |
| **MSL RAD Fallback** *(if RAD data unobtainable)* | *"In-situ MSL RAD radiation data was unavailable for automated pipeline ingestion; environmental radiation context is explicitly marked UNAVAILABLE rather than simulated or assumed."* |
| **Rover Ground Imagery (WP-15)** | *"Ground-level rover imagery integration was deferred; all terrain roughness and obstacle assessments are computed directly from 1-meter orbital HiRISE digital elevation models."* |
| **Field View (WP-16)** | *"Traverse planning is demonstrated in the primary Mission Control desktop console; the tablet Field View interface was deferred."* |
