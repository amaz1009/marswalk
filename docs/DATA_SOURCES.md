# MARSWALK — Data Source Selection (Provisional Shortlist)

| Field | Value |
|:---|:---|
| Document | DATA_SOURCES.md |
| Work Package | WP-05 (Data source selection) |
| Status | PROVISIONAL SHORTLIST (Awaiting Nov 13 Challenge Resources) |
| Author | Orchestrator / Data Agent (A1) |
| Date | 2026-11-12 |

---

## 1. Executive Summary & Operational Context

This document records the provisional data source selections, product identifiers, access URLs, and spatial bounds for the MARSWALK human-EVA planning prototype.

> [!IMPORTANT]
> **Provisional Status:** The NASA Space Apps 2026 Resources tab opens on **November 13, 2026**. Official recommended sources and regions will be announced at that time. Per owner constraints, all selections in this document constitute a **provisional shortlist** with verified access evidence and open questions, rather than an unalterable final baseline.

Per Scientific Integrity rules (§6) and WP-05 constraints:
- Only product IDs and direct download URLs verified against live official repositories (NASA PDS, USGS Astrogeology, UArizona HiRISE Operations Center) during this session are accepted as verified sources.
- Any product not directly verified via live HTTP header/page inspection is explicitly categorized as **`UNVERIFIED — candidate only`**.
- No raw raster data products have been downloaded (`DOWNLOAD_APPROVED: NO`).

---

## 2. Region Confirmation: Gale Crater / Mount Sharp Boxwork (Open Item O-1)

- **Region Identifier:** `gale_mount_sharp`
- **Location:** Gale Crater, Aeolis Mons (Mount Sharp) lower layered mound, Mars.
- **Geodetic Coordinates (Planetocentric, East-Positive):**
  - **Primary Local Traverse Box (HiRISE DTM Footprint):**
    - Latitude: $[-4.949^\circ, -4.721^\circ]$
    - Longitude: $[137.239^\circ, 137.354^\circ]$ East
  - **Regional Context Box (USGS MSL Merged Mosaic Footprint):**
    - Latitude: $[-5.099^\circ, -4.130^\circ]$
    - Longitude: $[137.124^\circ, 137.681^\circ]$ East
- **Selection Rationale:**
  1. Matches the challenge's example science objective (investigating ancient groundwater networks and boxwork mineral ridges formed in fractured bedrock).
  2. Features high-resolution 1 m/pixel stereo DTMs from MRO HiRISE and the USGS MSL team, meeting the resolution needed for suited human walking hazard detection.
  3. Ground-truth context is available from the NASA MSL *Curiosity* rover traverse, including direct in-situ surface radiation measurements from the Radiation Assessment Detector (RAD).

---

## 3. Verified Products Shortlist

Every URL below was checked and returned `HTTP 200 OK` (or valid redirect to public storage) during session testing on 2026-11-12.

| Dataset ID | Product ID | Instrument / Source | Format | Size | Resolution | Purpose | Verified Live URL |
|:---|:---|:---|:---|:---|:---|:---|:---|
| `HIRISE_DTM_GALE_MOUND` | `DTEEC_001488_1750_001752_1750_U02.IMG` | MRO HiRISE (USGS/UArizona) | PDS3 IMG | 360.4 MB | 1 m post spacing | Primary terrain model for slope, roughness, and EVA hazard routing | [UArizona HiRISE PDS](https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_001400_001499/PSP_001488_1750_PSP_001752_1750/DTEEC_001488_1750_001752_1750_U02.IMG) |
| `HIRISE_ORTHO_GALE_MOUND` | `PSP_001752_1750_RED_C_01_ORTHO.JP2` | MRO HiRISE (UArizona) | JPEG2000 | 33.3 MB | ~1 m / pixel (reduced) | Primary optical basemap co-registered with primary DTM | [UArizona HiRISE PDS](https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_001400_001499/PSP_001488_1750_PSP_001752_1750/PSP_001752_1750_RED_C_01_ORTHO.JP2) |
| `USGS_GALE_MERGED_DEM` | `MSL_Gale_DEM_Mosaic_1m_v3.tif` | HRSC + CTX + HiRISE (USGS Calef & Parker 2016) | GeoTIFF (Cloud-Optimized) | 3.87 GB | 1 m post spacing | Fallback & regional wide-area DEM covering the entire traverse corridor | [USGS Planetary Maps S3](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif) |
| `MOLA_MEGDR_GALE` | `MEGT00N090HB.IMG` | MGS MOLA (GSFC / PDS Geosciences) | PDS3 IMG | 129.8 MB | 128 px/deg (~463 m) | Regional topographic baseline (0°–44°S, 90°–180°E) and planetary datum reference | [PDS Geosciences Node](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt00n090hb.img) |
| `USGS_GEOLOGY_SIM3292` | `sim3292_database.zip` | USGS Geologic Map of Mars (Tanaka et al. 2014) | ZIP (GIS Database) | 808.9 MB | 1:20M global vector | Geologic units, contacts, and surface material context | [USGS Publications](https://pubs.usgs.gov/sim/3292/downloads/sim3292_database.zip) |
| `THEMIS_DAY_IR_GLOBAL` | `Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif` | Mars Odyssey THEMIS (ASU / USGS) | GeoTIFF | 22.77 GB | 100 m / pixel | Thermal daytime temperature basemap and thermophysical context | [USGS Planetary Maps S3](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif) |
| `MSL_RAD_SURFACE_RDR` | `MSL-M-RAD-3-RDR-V1.0` | MSL RAD (SwRI / PDS PPI Node) | PDS3 Bundle | Variable (by sol) | Point time-series | In-situ surface ionizing radiation dose rates along Curiosity traverse | [PDS PPI Node](https://pds-ppi.igpp.ucla.edu/collection/MSL-M-RAD-3-RDR-V1.0) |

---

## 4. Unverified Candidates (`UNVERIFIED — candidate only`)

The following candidate layers were evaluated but are **not** included in `data_sources.json` because specific file endpoints could not be fully verified against official repository indexes without downloading:

1. **CRISM Targeted Hyperspectral Observations (Mineralogy):**
   - Candidate observation: `FRT0000B204` or Mount Sharp targeted cubes.
   - Status: `UNVERIFIED — candidate only`.
   - Reason: Standard CRISM TRDR cubes require MTRDR spectral parameter pipelines (cat-pds). Needs review against challenge resource recommendations.
2. **Curiosity Navcam/Mastcam Surface Views (Field View):**
   - Candidate products: Sols 4200–4250 boxwork approach panoramas.
   - Status: `UNVERIFIED — candidate only`.
   - Reason: Individual PDS EDR/RDR image frames from MSL Mastcam must be matched to verified rover traverse waypoints in WP-15.
3. **Regional Tiled THEMIS Aeolis Quadrangle Daytime Mosaic:**
   - Candidate product: Controlled quadrangle tile for MC-23 / Gale.
   - Status: `UNVERIFIED — candidate only` (Night IR tile verified; 100 mpp daytime tile currently only verified in the 22.8 GB global mosaic).

---

## 5. Download Size and Ingestion Budget Analysis

| Option | Included Datasets | Raw Download Size | Processing Recommendation |
|:---|:---|:---|:---|
| **P0 Minimal Footprint** | HiRISE DTM (360 MB) + HiRISE Ortho (33 MB) + MOLA MEGDR (130 MB) + USGS Geology (809 MB) | **~1.33 GB** | **Recommended for initial local run.** Covers all core routing and science requirements without multi-gigabyte downloads. |
| **P0 Complete Footprint** | Above + USGS Gale Merged DEM (3.87 GB) | **~5.20 GB** | Recommended if operator wants full crater-wide routing beyond the immediate HiRISE stereo strip. |
| **Full Suite with Thermal Basemap** | Above + Global THEMIS Daytime IR (22.77 GB) | **~27.97 GB** | **Not recommended for direct bulk download.** For WP-06, a spatial window or Cloud-Optimized GeoTIFF range request should be used to extract the local Gale window (~5 MB) instead of pulling 22.8 GB. |

---

## 6. Open Items for Owner Confirmation (Nov 13 Milestone)

1. **Space Apps Resources Review (O-1):** On November 13, compare official challenge data links against this shortlist. If NASA provides pre-clipped regional bundles, substitute those to reduce ingestion footprint.
2. **Download Approval (O-2 / `DOWNLOAD_APPROVED`):** Decide between the 1.33 GB minimal footprint vs 5.20 GB complete corridor before starting WP-06.
3. **Format Compatibility (O-6):** Verify `rasterio` reads the HiRISE `.IMG` (PDS3 VICAR/ISIS detached/attached format) cleanly on Windows without native GDAL system packages.
