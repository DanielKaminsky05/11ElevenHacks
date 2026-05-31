# TransitRL — Agent Tools & the MCP Layer

This is the document that turns the [data catalog](data-layer.md) into **functionality**. It defines what the AI agent can actually *do* on behalf of a city planner, how each capability is backed by real datasets, and how the tools compose into one system.

> **Companion docs:** [Project Idea](project-idea.md) (the why) · [Data Layer Catalog](data-layer.md) (the datasets) · this doc (the tools that connect them).

---

## 1. The reframe: from stop-placer to planning copilot

The original pitch was narrow: *an RL agent that learns where bus stops should go.* That's a great demo, but a planner's real job is broader — they diagnose problems, test hypotheses, weigh equity, and justify decisions. So we widen the product:

> **TransitRL is a transportation-planning copilot for Toronto.** A planner asks a question in plain English. A local language model (Nemotron) decides which tools to call, runs them against the city's open-data substrate, and answers — with maps, numbers, and a plain-language rationale.

The crucial move: **the RL optimizer becomes one tool among many.** Placing stops is what you call when you want the machine to *search* for a layout. But most planner questions don't need optimization at all — they need diagnosis ("where are the gaps?"), simulation ("what if I move this?"), or attribution ("who loses?"). A copilot that can do all four is something a planner can *generally query*, not a single-trick optimizer.

This reframe is also the strongest hackathon story. The judges are scoring **agentic systems** and "could a real city planner use this tomorrow." A toolbox the agent orchestrates hits both; a hard-coded RL loop hits neither.

---

## 2. Why MCP

The tools are exposed through an **MCP (Model Context Protocol) server**, `transitrl-mcp`. MCP matters here for three reasons:

1. **Model-agnostic.** The same toolbox works with Nemotron locally on the Spark, or any MCP client. The data/compute layer is decoupled from the model.
2. **Composable & inspectable.** Each tool has a typed signature and returns structured results (metrics + GeoJSON/grid). The agent chains them; the frontend renders whatever geometry a tool returns. Every action is legible — no black box between question and map.
3. **It *is* the agentic system.** "Agentic" isn't a chat wrapper — it's a model choosing and sequencing real tools against real data. MCP makes that the architecture, not an afterthought.

```
┌─────────────┐    English      ┌──────────────────┐   tool calls    ┌────────────────────┐
│ City planner │ ───────────────▶│  Nemotron agent  │ ───────────────▶│  transitrl-mcp     │
│  (human)     │◀─────────────── │ (NIM, local)     │◀─────────────── │  (MCP server)      │
└─────────────┘  answer + map    └──────────────────┘  structured     └─────────┬──────────┘
        ▲                                                                        │
        │ renders GeoJSON / grid / metric trajectories                          │ reads/computes
        │                                                                        ▼
┌──────────────────────┐                                       ┌───────────────────────────────┐
│ Map frontend         │                                       │  Compute & data substrate      │
│ React · MapLibre ·   │◀──────────── WebSocket stream ────────│  • Grid env (Gymnasium)         │
│ deck.gl              │   (live training / scenario diffs)    │  • RL (SB3 PPO/DQN, PyTorch)    │
└──────────────────────┘                                       │  • Sim engine (walk-access)     │
                                                                │  • RAPIDS cuDF / cuSpatial      │
                                                                │  • cuOpt solver                 │
                                                                │  • Open data layer (data/)      │
                                                                └───────────────────────────────┘
```

---

## 3. The toolbox

Tools are grouped into five families that mirror how a planner actually thinks: **understand → diagnose → simulate → optimize → explain.** All tools are namespaced `transitrl.*` and operate over a shared, GPU-resident city grid so results are mutually consistent and instant.

For each tool: what it does · the datasets behind it (from the [catalog](data-layer.md)) · the grid channels it reads/writes · NVIDIA acceleration · an example question that triggers it.

### Family A — City State & Lookup *(read the map)*

**`transitrl.get_city_grid(bbox?, channels[], resolution)`**
The substrate every other tool reads. Rasterizes the open-data layers into the multi-channel tensor that is *both* the RL observation and the queryable city state.
- **Data:** StatCan DA boundaries + Census/Neighbourhood Profiles (population, income), GTFS + transit-stations (stops), Centreline + Pedestrian Network (network), Employment Survey (jobs), Neighbourhoods-158/Wards (boundary), ON-Marg/NIA/PIN (equity).
- **Channels:** all (population · stops · income/equity · destinations · network · boundary).
- **NVIDIA:** RAPIDS **cuDF** + **cuSpatial** for point-in-polygon and rasterization across the whole city; the grid tensor lives in the **128 GB unified memory** so no tool ever reloads it.

**`transitrl.profile_area(area | name | point, metrics?)`**
A complete dossier on a neighbourhood, ward, or DA: population, age, income, equity rank, jobs, nearby amenities, and current transit access.
- **Data:** Neighbourhood Profiles, Ward Profiles, Census Profile 2021, Employment Survey, ON-Marg, amenity layers (schools/libraries/parks/health).
- **Channels:** population, income/equity, destinations, stops.
- **Q:** *"Tell me about Malvern — who lives there and how well are they served?"*

**`transitrl.list_transit(bbox?, modes?, live?)`**
Existing routes and stops; optionally live positions/service state.
- **Data:** TTC GTFS (+ Surface), GO/Metrolinx GTFS, TTC Subway shapefiles, GTFS-RT.
- **Channels:** stops, network.
- **Q:** *"What transit serves the Eglinton corridor today?"*

**`transitrl.compare_areas(areas[], metrics[])`**
Side-by-side ranking across any metrics the other tools produce.
- **Data:** profile sources + any diagnostic output.
- **Q:** *"Rank Scarborough's wards by transit access for seniors."*

### Family B — Accessibility & Equity Diagnostics *(diagnose)*

**`transitrl.compute_accessibility(area | bbox, mode=walk, threshold_m=400)`**
The core sim metric, exposed directly: share of population within a walk buffer of any stop, and average distance to nearest service.
- **Data:** GTFS stops, population (Census DA), Pedestrian Network / Centreline for walk distance; **SAM** as an external benchmark.
- **Channels:** stops, population, network.
- **NVIDIA:** cuSpatial buffer + spatial join; the same kernel the RL reward calls thousands of times per episode.
- **Q:** *"Show me Toronto's transit deserts."*

**`transitrl.equity_gap_report(bbox?)`**
The "who gets left behind" tool. Crosses accessibility with marginalization to surface cells of **high need + low access** — the project's headline insight, computed not assumed.
- **Data:** ON-Marg, Neighbourhood Improvement Areas, Priority Investment Neighbourhoods, Wellbeing Civics & Equity, income (Census), social/community housing, shelters & drop-ins.
- **Channels:** equity, population, stops.
- **Q:** *"Which low-income neighbourhoods are most underserved relative to need?"*

**`transitrl.reachability(origin, time_budget_min, mode)`**
Isochrone + opportunity count: how many jobs, schools, and clinics are reachable from a point within a time budget.
- **Data:** GTFS schedules (transit travel time), Centreline/Pedestrian/ORN (walk-bike), destinations (Employment Survey jobs, schools, libraries, health); **SAM** for validation.
- **Channels:** destinations, network, stops.
- **NVIDIA:** **cuOpt** / GPU graph traversal for the travel-time surface.
- **Q:** *"From Jane & Finch, how many jobs are reachable in 45 minutes by transit?"*

**`transitrl.estimate_demand(bbox?, horizon=now|2031|2051)`**
A latent-demand surface combining who lives where, where they need to go, and where growth is coming.
- **Data:** population, Employment Survey, Journey-to-Work O→D flows, TTC ridership, **Development Pipeline**, Intensification-to-2051, TOC / Major Transit Station Areas, registered condos; transit-dependent populations (housing, shelters, seniors survey).
- **Channels:** population, destinations, demand-signal.
- **Q:** *"Where is unmet demand growing fastest over the next decade?"*

**`transitrl.reliability_report(route | area)`**
Service-quality hotspots: delays and headway gaps. The "non-obvious insight" lever the rubric rewards.
- **Data:** TTC Bus / Streetcar / Subway Delay (local), GTFS-RT, King St. Transit Pilot benchmark.
- **Channels:** demand-signal.
- **Q:** *"Which routes in Ward 23 are least reliable at rush hour?"*

### Family C — Scenario Simulation *(what-if)*

**`transitrl.simulate_change(operations[])`**
The sim engine as a first-class tool. Operations are `add_stop` / `move_stop` / `remove_stop` / `add_segment` at coordinates; returns before/after coverage, travel-time proxy, equity-weighted access, and a per-group winners/losers breakdown.
- **Data:** same layers as accessibility + equity + demand.
- **Channels:** writes a hypothetical `stops` channel; recomputes the rest.
- **NVIDIA:** re-rasterize + recompute on GPU for **interactive** (sub-second) feedback — possible only because the full grid is resident in unified memory.
- **Q:** *"What happens if I move the stop at Kennedy & Eglinton two blocks east?"*

**`transitrl.diff_scenarios(a, b)`**
Tabular + map diff between any two layouts (baseline, hand-edited, or optimizer output).
- **Q:** *"Compare the community proposal against the optimizer's plan."*

**`transitrl.constraint_check(layout)`**
Feasibility gate: minimum stop spacing, proximity to a route line, stop budget, and hard barriers (rail/water/zoning).
- **Data:** route geometry (GTFS shapes, subway shapefiles), Centreline, Zoning By-law / land use, topographic barriers.
- **Channels:** network, boundary.
- **Q:** *"Is this 6-stop layout physically feasible?"*

### Family D — Optimization *(let the machine search)*

**`transitrl.parse_goal(text)`** → structured reward spec
Nemotron translates an English goal into reward weights (coverage / travel-time / equity / constraint), a target region, and a stop budget. The language→reward bridge.
- **Q:** *"Improve access for low-income Scarborough without raising downtown commute times."* → `{coverage:0.3, travel:0.2, equity:0.5, region:"Scarborough", protect:"downtown_commute", budget:8}`

**`transitrl.optimize_layout(reward_spec, region, budget)`**
The original RL core, now one tool. Runs the Gymnasium env with SB3 (PPO/DQN, CNN policy) — optionally seeding the search space with **cuOpt** for the combinatorial placement — and streams each episode to the map.
- **Data:** the full city grid.
- **NVIDIA:** **PyTorch** RL on the Blackwell GPU; **cuOpt** for warm-start/placement; unified memory holds env + replay buffer + LLM context simultaneously so training and narration coexist.
- **Q:** any goal sentence (via `parse_goal`).

**`transitrl.propose_candidates(goal, n)`** *(stretch)*
Nemotron suggests candidate relocation cells to warm-start exploration — RL on both sides of the interface.

**`transitrl.optimization_status(job_id)`** — live metric trajectory for the animated map (WebSocket).

### Family E — Explanation & Attribution *(narrate & justify)*

**`transitrl.who_is_affected(scenario, group_by=income|age|neighbourhood)`**
The distributional-impact table: who gains access, who loses, broken down by the group the planner cares about.
- **Data:** Census income/age, equity layers, neighbourhood boundaries.
- **Q:** *"Under this plan, which income groups gain and which lose?"*

**`transitrl.explain_result(scenario | job_id)`**
Nemotron reads before/after metrics and the agent's moves and narrates the trade-off in plain language — making the implicit value choice visible.

**`transitrl.generate_brief(scenario)`**
Exports a planner-ready memo (markdown/PDF): the question, the recommendation, the metrics, the equity impact, and the caveats. This is the "use it tomorrow" deliverable.

---

## 4. Dataset → tool traceability

Every dataset in the [catalog](data-layer.md) earns its place by powering at least one tool. This is the literal "map the data to functionality" mapping.

| Dataset (catalog) | Channel | Tool(s) it powers |
|---|---|---|
| TTC GTFS (Routes/Surface/Merged) | stops, network | `list_transit`, `compute_accessibility`, `reachability`, `simulate_change`, `optimize_layout` (baseline) |
| GO / Metrolinx GTFS | stops, network | `list_transit`, `reachability`, `compute_accessibility` (regional) |
| TTC GTFS-Realtime | stops | `list_transit(live)`, `reliability_report` |
| TTC Subway shapefiles | network | `list_transit`, `constraint_check` (route-line proximity) |
| Neighbourhood / Ward / Wellbeing Profiles | population, income | `profile_area`, `compare_areas`, `who_is_affected`, grid population channel |
| ⭐ Census Profile 2021 (DA/CT) | population, income, jobs | `get_city_grid`, `profile_area`, `estimate_demand`, `who_is_affected` |
| ⭐ Census Boundary Files / GAF | boundary | `get_city_grid` scaffolding — all rasterization & joins |
| Wellbeing Civics & Equity · NIA · Priority Investment | equity | `equity_gap_report`, `optimize_layout` (equity term), `who_is_affected` |
| ⭐ ON-Marg 2021 | equity | `equity_gap_report`, `optimize_layout` (equity term), `who_is_affected` |
| Centreline · Pedestrian Network · Intersection File · Address Points · ORN | network | `compute_accessibility`, `reachability` (walk distance), `get_city_grid` alignment, `constraint_check` |
| Neighbourhoods-158 · Wards · Regional Boundary · CMA 535 | boundary | `profile_area`, `compare_areas` aggregation, `get_city_grid` extent |
| Employment Survey · Census jobs | destinations | `estimate_demand`, `reachability` (job opportunities) |
| Transit Oriented Communities · Major Transit Station Areas | destinations | `estimate_demand` (planned density), `optimize_layout` (where growth lands) |
| Schools · Libraries · Parks · Child Care · Health · LTC · POIs | destinations | `reachability`, `estimate_demand`, `profile_area` (amenities) |
| Community/Social/Subsidized/Affordable Housing · Cost of Living · Shelters · Drop-ins | equity, population | `equity_gap_report`, `estimate_demand` (transit-dependent), `who_is_affected` |
| Development Pipeline · Intensification-to-2051 · Condos | demand-signal | `estimate_demand(horizon)`, `optimize_layout` (forward-looking) |
| ⭐ Spatial Access Measures (SAM) | stops, destinations | `compute_accessibility` & `reachability` **benchmark**, reward validation |
| Journey-to-Work O→D flows | demand-signal | `estimate_demand`, validation |
| TTC Ridership Analysis | demand-signal | `estimate_demand`, `reliability_report` baseline, validation |
| TTC Bus/Streetcar/Subway Delay | demand-signal | `reliability_report` |
| Bike Share · Cycling Network · Bike Parking · Multi-Use Trails | network, demand-signal | `reachability` (multimodal last-mile), `estimate_demand` (active transport) |
| Sidewalk · Bridges · TIN · Topographic · Road Restrictions · Crossovers | network | walk-friction in `compute_accessibility`/`reachability`, `constraint_check` (barriers) |
| KSI Collisions · Traffic Calming · Speed · Crime · Red Light · Signals · Beacons | (safety overlay) | `constraint_check` (avoid unsafe access), safety context in `profile_area` |
| King St. Transit Pilot suite | demand-signal | `reliability_report` benchmark, sim validation |
| Zoning · Secondary Plans · Land use · GeoHub parcels | boundary, destinations | `constraint_check` (feasibility), `estimate_demand` (land use), grid land-use channel |
| 311 · Labour Force · Parking · Uber/Lyft | demand-signal | `estimate_demand` (secondary signals) |
| Seniors Survey 2017 | equity/demand | `estimate_demand`, `who_is_affected(age)`, `profile_area` |

**Derived layers (computed, not raw):** `compute_accessibility` → an *access surface*; `equity_gap_report` → a *gap surface*; `estimate_demand` → a *demand surface*. These are tool outputs the frontend renders and other tools consume.

---

## 5. How the tools compose

The agent isn't scripted — Nemotron chooses the sequence. Three representative flows:

**(a) Diagnose → optimize → explain** — *"Improve access for low-income neighbourhoods in Scarborough without increasing downtown commute times."*
1. `parse_goal` → reward spec (high equity weight, protect downtown commute)
2. `equity_gap_report("Scarborough")` → surfaces the underserved cells
3. `get_city_grid` → observation tensor
4. `optimize_layout(reward_spec)` → streams episodes to the live map
5. `who_is_affected` + `explain_result` → narration of the trade-off the planner implicitly chose

**(b) What-if, no RL** — *"We have budget for 3 new stops near Jane & Finch. Where should they go, and what do we gain?"*
1. `profile_area` + `estimate_demand` → context
2. `optimize_layout(budget=3, region)` → candidate placement
3. `simulate_change` + `constraint_check` → verify feasibility & impact
4. `generate_brief` → memo for council

**(c) Pure diagnostic, no optimizer at all** — *"Which wards have the worst transit reliability for seniors?"*
1. `reliability_report` per ward + `profile_area(age)` 
2. `compare_areas` → ranked answer

Flow (c) is the proof the reframe worked: a planner question answered well **without ever placing a stop.** That's what makes it a general copilot rather than an optimizer with a chat box.

---

## 6. NVIDIA / DGX Spark mapping

How each capability lands on the stack the hackathon scores (Technical Execution 30 + NVIDIA Ecosystem 30):

| Capability | NVIDIA tech | Spark story |
|---|---|---|
| Spatial rasterization, buffers, joins (`get_city_grid`, `compute_accessibility`) | **RAPIDS** cuDF + cuSpatial | Whole-city point-in-polygon across 100k+ census/stop geometries on GPU |
| Travel-time surfaces, isochrones, combinatorial placement (`reachability`, `optimize_layout`) | **cuOpt** | GPU routing solver; warm-starts the RL search |
| RL training (`optimize_layout`) | **PyTorch** on Blackwell | PPO/DQN CNN over the grid image; 50×+ faster episode loop |
| Planner agent, goal-parsing, narration, tool orchestration | **Nemotron** via **NIM** | Targets the **Nemotron bounty**; local = data privacy + interactive latency |
| Everything resident at once | **128 GB unified memory** | City grid tensor + RL replay buffer + LLM context held simultaneously → instant `simulate_change`, no reload between tools |

The articulable "why Spark": *"We hold the entire rasterized city, the RL environment's replay buffer, and the Nemotron context in 128 GB of unified memory at once — so a planner gets sub-second what-if simulations and a locally-reasoned explanation without any data leaving the device."*

---

## 7. Build phases (grounded in what's already in `data/`)

The local inventory is richer than the catalog's stale "gaps" note implies — Metrolinx GTFS, Pedestrian Network, Intersection File, Address Points, Neighbourhoods-158, NIA, Priority Investment, ON-Marg (DA + n158), StatCan DA boundaries, and Wellbeing equity are **all already downloaded.** Nearly the whole toolbox is buildable offline today.

| Phase | Tools | Status of backing data |
|---|---|---|
| **0 — MVP loop** | `get_city_grid`, `list_transit`, `compute_accessibility`, `profile_area`, `simulate_change`, `parse_goal`, `optimize_layout`, `explain_result` | ✅ All local (GTFS, Centreline, Pedestrian Network, profiles, DA boundaries, employment) |
| **1 — Equity headline** | `equity_gap_report`, `who_is_affected` | ✅ Local (ON-Marg, NIA, PIN, Wellbeing equity, census income) |
| **2 — Reliability & reach** | `reliability_report`, `reachability` | ✅ Delay data local; ⚠️ SAM still to fetch for benchmark |
| **3 — Demand & future** | `estimate_demand`, `constraint_check`, `generate_brief` | ⚠️ Need Development Pipeline, Intensification-2051, Journey-to-Work, Zoning |

**First wedge to demo:** Phase 0 + Phase 1 = the full headline loop (English goal → equity-aware optimization → who-wins/loses narration) runs entirely on data already on disk.

---

## 8. Honesty boundary (carry over from the project idea)

Every tool inherits the same caveat: this is an **accessibility & equity model, not a demand forecast.** `estimate_demand` surfaces *latent* demand from land use and population — it does not predict ridership. The sim is walk-access and single-corridor; it deliberately excludes multi-leg transfer trips. Naming the limit inside the tooling (and in `generate_brief`) is part of the design — it's the first thing a transit-literate judge will probe.
