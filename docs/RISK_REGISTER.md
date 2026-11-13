# MARSWALK — Risk Register

| Field          | Value                                                     |
|----------------|-----------------------------------------------------------|
| Document       | docs/RISK_REGISTER.md                                     |
| Version        | 1.0                                                       |
| Status         | Active / Live                                             |
| Last Updated   | 2026-11-13                                                |
| Scope          | Hackathon execution, pipeline, tooling, and delivery risks |

This register tracks operational, technical, and process risks for the MARSWALK project during the condensed ~39-hour hackathon execution window (09:00 IST Sat 14 Nov to 23:59 IST Sun 15 Nov 2026).

---

## 1. Summary of Active Risks

| ID | Risk Title | Severity / Impact | Owner | Mitigation Summary | Status |
|----|------------|-------------------|-------|--------------------|--------|
| R-01 | Submission requirements unknown | High | Owner | Inspect event dashboard at start; reserve final 1 h (Hour 36–37) for submission; local schedule unconfirmed | OPEN |
| R-02 | Real Mars rasters not yet read with rasterio | Critical | A1 Data | WP-06 step 1 smoke test reads real raster window; GeoTIFF fallback; mark `UNAVAILABLE` rather than synthesise | OPEN |
| R-03 | Antigravity quota or rate limits | High | Owner | Use Claude/GPT for hard backend WPs (100% pool left); Flash for frontend/docs; reserve Pro backup accounts | OPEN |
| R-04 | AI positioning and judging expectations | Medium | Orchestrator | Core routing & safety is 100% deterministic; LLM is optional add-on; pitch and README state this prominently | OPEN |
| R-05 | Test suites unexecuted or weakened | High | A6 QA | Every WP must execute automated tests and log real command output before merge approval | OPEN |
| R-06 | Owner review bottleneck on merges | Medium | Owner | Follow strict per-WP checklist; working execution policy Default, switch to Request Review for merges/downloads; Turbo prohibited | OPEN |
| R-07 | Local workstation failure or data loss | High | All | Push WP branches to remote after every atomic commit | OPEN |
| R-08 | Fatigue and stamina management | Medium | Owner | Planned rest/sleep block scheduled during data downloads and heavy pipeline processing | OPEN |
| R-09 | Demo recording tooling failure | High | Owner | Pre-select and test screen recording/audio tool on Windows before event start | OPEN |
| R-10 | Agent self-reports unverified | Critical | Owner | Treat agent status updates as claims; owner verifies git diffs, test outputs, and rendered files | OPEN |

---

## 2. Risk Cards

### R-01: Submission Requirements Unknown
- **Risk:** Specific submission deliverables, video length limits, mandatory slide deck templates, or questions on the Space Apps dashboard may differ from planning assumptions. On Nov 13, the Kolkata local event page Details tab showed dates only (Nov 14-15) and the Local Event Schedule tab was empty; the owner decided to plan on 09:00 IST Sat 14 Nov to 23:59 IST Sun 15 Nov; the submission deadline and submission requirements are still unconfirmed.
- **Impact:** High. Late discovery of submission rules could require rushed rework during final submission hours.
- **Owner:** Owner.
- **Mitigation:** Owner checks the official event dashboard immediately upon opening at 09:00 IST Saturday. Reserve a dedicated 1-hour buffer (Hour 36 to Hour 37) solely for packaging submission text, repo links, and video upload.
- **Status:** OPEN.

### R-02: Real Mars Rasters Not Yet Read with Rasterio on Windows
- **Risk:** PDS3 IMG, Vicar, or large JPEG2000 raster formats may encounter driver or projection incompatibility with `rasterio`'s bundled GDAL on Windows.
- **Impact:** Critical. The terrain and routing pipeline depends directly on reading HiRISE DTM elevation arrays.
- **Owner:** A1 Data.
- **Mitigation:** WP-06 Step 1 must immediately attempt to open one real downloaded product and read a small sub-window before any pipeline code is written. Fallback sequence:
  1. Primary HiRISE DTM (`.IMG`).
  2. USGS Gale Crater DEM GeoTIFF (`.tif`) if downloaded.
  3. If neither can be parsed, mark the layer as `UNAVAILABLE` with an explicit reason. **Never fabricate or synthesize data.**
- **Status:** OPEN.

### R-03: Antigravity Quota or Rate Limits
- **Risk:** Token limits, model quotas, or API throttling during intense multi-turn development could stall agent progress.
- **Quota Status & Inspection (Nov 13 20:04 IST):**
  - Gemini pool: 88% weekly quota left (resets in 4 days, i.e. after the event window starts) and 87% of the 5-hour limit left.
  - Claude and GPT models operate on a separate pool, with both limits at 100%.
  - Models offered besides Gemini 3.8 Flash: Claude Sonnet 4.6 (Thinking), Claude Opus 4.6 (Thinking), GPT-OSS 120B. Gemini 4 models showed Unavailable.
- **Impact:** High. Blocks progress if developer cannot invoke agent commands.
- **Owner:** Owner.
- **Mitigation:**
  1. Run the harder backend work (WP-06 data pipeline, WP-07 terrain engine, WP-10 routing engine, WP-11 EVA safety) on a model from the separate Claude/GPT pool, keeping Flash for frontend, docs, and simple tasks.
  2. Owner has two further Pro accounts available as a third tier (owner to check Antigravity terms and verify whether the account can be switched mid-session before relying on it).
  3. Owner to read the "Notice" tags on the Claude/GPT models before the event.
- **Status:** OPEN.

### R-04: AI Positioning and Evaluation Alignment
- **Risk:** Judges may penalize purely LLM-generated safety routes or hallucinated flight rules, or conversely misunderstand the role of AI in the project.
- **Impact:** Medium. Misalignment with NASA safety principles.
- **Owner:** Orchestrator.
- **Mitigation:** Core routing, walk-back envelope, and safety checks are 100% deterministic, mathematically verified algorithms. LLM narrative generation is an optional add-on (ADR-07). README, pitch video, and documentation explicitly highlight deterministic safety guarantees first.
- **Status:** OPEN.

### R-05: Test Verification Discipline
- **Risk:** WPs marked complete without actually running automated tests or tests weakened to pass.
- **Impact:** High. Latent bugs cascade into downstream packages.
- **Owner:** A6 QA.
- **Mitigation:** Operating rules §4 & §7 are strictly enforced: every completed WP must execute tests in that session and display real stdout counts. No WP branch is merged without verified test evidence.
- **Status:** OPEN.

### R-06: Owner Review Bottleneck
- **Risk:** Delay in owner reviewing diffs and approving merges stalls agent development.
- **Impact:** Medium. Delays milestone completion.
- **Owner:** Owner.
- **Mitigation:** Use a standardized 3-step checklist (diff inspection, test confirmation, status update check); keep WP branch diffs small, focused, and scoped only to that WP's area. The working execution policy is Default; the owner switches the session to Request Review for merges and for the WP-06 data downloads; Turbo is prohibited.
- **Status:** OPEN.

### R-07: Workstation Failure or Uncommitted Loss
- **Risk:** Local hardware crash, power outage, or corrupted working copy causes work loss.
- **Impact:** High. Potential loss of hours of progress during a short window.
- **Owner:** All.
- **Mitigation:** Conventional commit after every completed step, followed immediately by `git push origin <branch>`. The remote repository on GitHub remains the up-to-date offsite backup.
- **Status:** OPEN.

### R-08: Fatigue and Sleep Schedule
- **Risk:** Solo developer exhaustion degrades decision-making and code review quality.
- **Impact:** Medium. High bug rate and missed deadlines in final hours.
- **Owner:** Owner.
- **Mitigation:** Schedule an explicit sleep / rest block during overnight hours when long data downloads or automated integration suites can run in the background.
- **Status:** OPEN.

### R-09: Demo Recording and Production Tooling
- **Risk:** Screen recording software fails, produces unreadable video, or encounters audio latency at hour 35.
- **Impact:** High. Final video submission is mandatory for judging.
- **Owner:** Owner.
- **Mitigation:** Pre-select and test the recording tool (OBS Studio, Windows Game Bar, or Screen Recorder) on the Windows development machine before the event starts. Verify microphone input and crisp 1080p text rendering.
- **Status:** OPEN.

### R-10: Agent Self-Reports Must Be Independently Verified
- **Risk:** AI agent claims a step is done, tests passed, or data validated when files were incomplete or commands simulated.
- **Impact:** Critical. Compromises scientific integrity and system reliability.
- **Owner:** Owner.
- **Mitigation:** Agent reports are treated strictly as claims. The owner verifies actual git diffs, test logs, generated files, and data manifests before approving any merge.
- **Status:** OPEN.
