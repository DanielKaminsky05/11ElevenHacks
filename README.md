# TransitRL — a transit-planning copilot for Toronto

**Challenge track:** Urban Operations (with Economic Systems & Public Services overlap)
**Bounty:** Best Use of NVIDIA Nemotron

A city planner asks a question in plain English — *"where are our transit deserts?"*,
*"who's underserved relative to need?"*, *"add 3 stops in Malvern"* — and a **local
Nemotron model** answers with maps, numbers, and a defensible rationale. Behind the chat is
an agentic toolbox of real analyses over **7 GB of City of Toronto + StatCan open data**:
accessibility & equity diagnostics, what-if simulation, and a grounded stop-placement
optimizer. It compresses a months-long, GIS-expert planning study into a seconds-long loop
someone without GIS training can run — entirely on open weights and open data, on one box.

## Quick start

**Backend** (FastAPI; runs on the DGX Spark next to the NIM):
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows  (source .venv/bin/activate on *nix)
pip install -e ".[dev]"
# Laptop / no model: runs end-to-end against a deterministic offline NIM stub
TRANSITRL_NIM_OFFLINE=true python -m uvicorn app.main:app --port 9000
# On the Spark, wired to the local Nemotron NIM:
#   scripts/run_nim.sh          # serve Nemotron via NVIDIA NIM on :8001
#   scripts/run_backend.sh      # backend on :9001, NIM_OFFLINE=false
curl http://localhost:9000/health
```

**Frontend** (Next.js + MapLibre + deck.gl):
```bash
cd frontend
npm install
BACKEND_URL=http://localhost:9000 npm run dev    # http://localhost:3000
```

**Tests:** `cd backend && .venv/Scripts/python.exe -m pytest -q` → **361 passing.**

## Architecture

```
 Planner (plain English)
        │
        ▼
 Next.js + MapLibre/deck.gl  ──►  /chat tool-calling loop  ──►  Nemotron via NVIDIA NIM
 (chat + animated map views)         (app/routers/chat.py)        (local, OpenAI-compatible)
        ▲                                    │
        │   maps · metrics · rationale       ▼
        └───────────────────  ~26 typed tools over Toronto open data
                              city_state · diagnostics · simulation · optimization · explanation
                                            │
                              7 GB open data → rasterized city grid
                              (GTFS · census DAs · StatCan SAM · ON-Marg · neighbourhoods)
```

The model is the human-facing bookend; every number it states must come from a tool it
actually called this turn (a strict no-hallucination grounding rule, enforced in the system
prompt). Tools live one family per module under `backend/app/tools/`, each registered with
`@tool` and exposed to the model as an OpenAI-style schema.

## NVIDIA / Spark story

- **Nemotron via NVIDIA NIM** is the real, wired model layer (`backend/app/agent/nim_client.py`):
  it orchestrates tool calls, translates English goals into structured reward specs
  (`parse_goal`), and narrates trade-offs. Local, OpenAI-compatible, no data leaves the box.
- **GPU-resident reward kernel.** The optimizer's hot loop (`_layout_terms` in
  `backend/app/tools/optimization.py`) is a dense `(demand cells × candidate stops)`
  gravity/distance computation written against an array module, so the **same kernel** runs on
  NumPy (laptop) or **CuPy on the Spark's GPU** — the backend is resolved once in
  `app/tools/_gpu.py`, features are staged to the GPU once, and the search reads them with zero
  per-eval host↔device copies. `backend/scripts/bench_reward.py` prints the CPU-vs-GPU scaling
  on the real Toronto grid.
- **Why a DGX Spark:** the whole agentic loop — Nemotron + its long context, the Toronto grid
  features, and the GPU reward eval — co-resides in **128 GB of coherent unified memory**, so it
  runs **locally, privately, and unmetered**. A search loop doing thousands of tool-calls +
  scenario evals is impractical on per-token cloud billing; here it's free and the city's equity
  data stays on-device.

## The optimizer

The stop-placement optimizer is a **greedy + local-search** solver steered by the LLM. Stop
placement is a maximal-covering / p-median problem whose coverage objective is **monotone
submodular**, so greedy is provably within (1 − 1/e) of optimal, deterministic, and fast enough
to re-solve interactively when the planner changes weights — and its reward eval is the
GPU-accelerated kernel above. The reward is grounded in real per-cell data (population,
low-income *need*, existing-network gravity access) and credits only **new** access, so it
closes gaps instead of piling onto already-served areas. Demand is **SAM-validated** against
StatCan's transit employment-access index. See `docs/reward-and-optimizer.md`.

## Datasets & provenance

All from [City of Toronto Open Data](https://open.toronto.ca/) + Statistics Canada:
TTC & GO/Metrolinx GTFS · 2021 Census profiles & DA boundaries · StatCan Spatial Access
Measures (SAM) · Ontario Marginalization Index / Neighbourhood Improvement Areas ·
Neighbourhoods-158, Centreline, Pedestrian Network. (`data/`, ~7 GB; see `data/README.md`.)

## Known limitations & next steps

- **Accessibility & equity model, not a demand forecast.** The model is walk-access +
  single-corridor; it deliberately excludes multi-leg transfer trips.
- **GPU acceleration covers the reward eval, not yet the full pipeline.** The optimizer's hot
  loop is GPU-resident (CuPy) on the Spark; next is rasterizing the grid with RAPIDS
  cuSpatial/cuDF and adding a cuOpt MILP exact baseline warm-started from the greedy solution.
- The candidate grid is coarse (~2 km); next is a finer census-DA population raster + the
  Pedestrian Network/Centreline walk graph for true isochrones.
