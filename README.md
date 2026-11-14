# AresNav

**Human EVA planning for the Martian surface, built on NASA mission data.**

AresNav is an interactive planning tool for a future astronaut's Martian EVA traverse. It
layers NASA datasets (terrain, imagery, thermal and geology) for one region, plans
walking routes for a suited astronaut, checks each route against configurable safety
limits, and explains every result with its data sources and limitations.

Built for the **NASA Space Apps Challenge 2026: "Interplanetary Survival Guide:
Martian Map"**
(https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/).

> **Disclaimer.** AresNav is a research and planning prototype. Results are
> computational assessments under stated assumptions and are not a certified
> astronaut safety analysis.

---

## Status

**Pre-implementation.** The architecture, contracts and specifications are complete.
Application code is built in the work-package order in
[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md). Live progress is in
[`docs/DEVELOPMENT_STATUS.md`](docs/DEVELOPMENT_STATUS.md).

---

## What It Does (planned)

- **Mars map for one region** (provisional demo: Gale Crater, lower Mount Sharp
  boxwork terrain). Layers include high-resolution terrain, slope, roughness, optical
  imagery, thermal data and geologic units.
- **Evidence chain:** click any value to see its dataset, instrument, resolution,
  processing steps and data class (measured, derived, model, assumption…).
- **Human traverse planning:** deterministic A* routes for a suited astronaut on
  foot, using a walking-speed model built from cited human-EVA sources (never rover
  data).
- **Three route options** (lowest risk, balanced, maximum science) with elevation
  profiles and EVA timelines.
- **Safety checks:** PASS / WARNING / BLOCKED / UNKNOWN against configurable limits.
  Missing data is never treated as a pass.
- **Data-confidence map** showing where the analysis is well supported.
- **Mission report** with datasets, assumptions and limitations.
- P1 extras: walk-back envelope, rover-eye image previews, Field View for a tablet or
  helmet HUD, a multi-agent briefing (works without an LLM), site ranking.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) | Architecture, decisions, conventions, ownership |
| [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) | Endpoints, shared models, configuration, data dictionary |
| [`docs/SCIENCE_AND_SAFETY_SPEC.md`](docs/SCIENCE_AND_SAFETY_SPEC.md) | Formulas, EVA model, routing, safety rules, references |
| [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md) | Test catalogue, procedures, Definition of Done |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Work packages, milestones, repository layout |
| [`docs/DEVELOPMENT_STATUS.md`](docs/DEVELOPMENT_STATUS.md) | Live progress and resume checkpoint |
| [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md) | Branching, releases, recovery |

---

## Tech Stack

Backend: Python 3.11/3.12, FastAPI, Pydantic v2, NumPy, SciPy, rasterio, pyproj,
GeoPandas. Frontend: React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Leaflet,
Recharts, Zustand. Optional agents: LangGraph with Anthropic or OpenAI models
(deterministic mode by default).

---

## Quick Start (Windows, available after WP-04 and WP-06)

```powershell
# once per machine, if PowerShell blocks local scripts:
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

copy .env.example .env
.\scripts\setup.ps1
# download and process the region data (exact commands added in WP-06)
.\scripts\dev.ps1
```

Then open http://localhost:5173.

---

## Data and Attribution

All scientific data comes from NASA missions and USGS Astrogeology through public
archives (for example the NASA Planetary Data System). The full list of products,
with sources, citations and processing steps, is generated in
`backend/data/manifests/dataset_catalog.json` and summarised here in WP-21.

---

## License

To be decided by the project owner.
