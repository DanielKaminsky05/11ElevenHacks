# TransitRL — Map Data Layer Catalog

This is the source-of-truth catalog of datasets for TransitRL's **map data layer** — the geospatial substrate the RL agent queries and that gets rasterized into the multi-channel grid (population · stops · income/equity · destinations · network · boundary · demand-signal).

> **What these datasets *do*:** see [Agent Tools & MCP Layer](agent-tools.md) for how each dataset here maps to a concrete tool the AI agent can call (the dataset→tool traceability matrix is in §4), and the unified vision of how those tools compose.

Datasets are grouped by relevance:

- **CORE** — directly builds an observation channel.
- **SUPPORTING** — strong destination or equity-demand layers.
- **TANGENTIAL** — slight relevance; useful as secondary features or for validation. Included deliberately — we want anything relevant even slightly.

All Toronto sources are City of Toronto Open Data (open.toronto.ca). Federal sources are under the Statistics Canada Open Licence; Ontario sources under OGL–Ontario. **One exception:** ON-Marg is free for research/non-commercial use only — check terms before any commercial deployment.

> **Already downloaded?** See the [What we already have locally](#what-we-already-have-locally) table at the bottom before fetching anything.

---

## City of Toronto Open Data

### CORE — the channels the observation is built from

**Transit network — `stops`**

| Dataset | Channel | Link | Why |
|---|---|---|---|
| Merged GTFS — TTC Routes & Schedules | stops | [link](https://open.toronto.ca/dataset/merged-gtfs-ttc-routes-and-schedules/) | All modes (subway/streetcar/bus); canonical existing-stop layer |
| TTC Routes and Schedules | stops | [link](https://open.toronto.ca/dataset/ttc-routes-and-schedules/) | GTFS feed |
| Surface Routes & Schedules for BusTime | stops | [link](https://open.toronto.ca/dataset/surface-routes-and-schedules-for-bustime/) | Surface-only GTFS with alerts |
| TTC GTFS-Realtime (GTFS-RT) | stops | [link](https://open.toronto.ca/dataset/ttc-gtfs-realtime-gtfs-rt/) | Live positions/service; baseline state |
| TTC Subway Shapefiles | network | [link](https://open.toronto.ca/dataset/ttc-subway-shapefiles/) | Rapid-transit corridors/nodes as geometry |

**Population & income/equity**

| Dataset | Channel | Link | Why |
|---|---|---|---|
| Neighbourhood Profiles | population, income | [link](https://open.toronto.ca/dataset/neighbourhood-profiles/) | Census population, income, age, labour by neighbourhood — primary local demographic source |
| Wellbeing Toronto — Demographics / NHS / TaxFiler | population, income | [link](https://open.toronto.ca/dataset/wellbeing-toronto-demographics/) | Population & income breakdowns by neighbourhood |
| Wellbeing Toronto — Civics & Equity Indicators | equity | [link](https://open.toronto.ca/dataset/wellbeing-toronto-civics-equity-indicators/) | Ready-made neighbourhood equity score |
| Ward Profiles (25-ward + historical) | population, boundary | [link](https://open.toronto.ca/dataset/ward-profiles-25-ward-model/) | Demographic/socioeconomic profiles per ward |
| Neighbourhood Improvement Areas (31) | equity | [link](https://open.toronto.ca/dataset/neighbourhood-improvement-areas/) | Official low-equity designations → equity-weighting term |
| Priority Investment Neighbourhoods (13) | equity | [link](https://open.toronto.ca/dataset/priority-investment-neighbourhoods/) | Investment-priority areas → equity-weighting term |

**Network / walkability — `network`**

| Dataset | Channel | Link | Why |
|---|---|---|---|
| Toronto Centreline (TCL) | network | [link](https://open.toronto.ca/dataset/toronto-centreline-tcl/) | Street/road geometry; foundation for routing & walk distance |
| Pedestrian Network | network | [link](https://open.toronto.ca/dataset/pedestrian-network/) | Walk graph — best fit for the walk-buffer accessibility model |
| Intersection File | network | [link](https://open.toronto.ca/dataset/intersection-file-city-of-toronto/) | All intersections; routing topology |
| Address Points (One Address Repository) | network | [link](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/) | 500k geocoded points for grid alignment |

**Boundaries — `boundary`**

| Dataset | Channel | Link | Why |
|---|---|---|---|
| Neighbourhoods (158) | boundary | [link](https://open.toronto.ca/dataset/neighbourhoods/) | Aggregation units |
| City Wards | boundary | [link](https://open.toronto.ca/dataset/city-wards/) | Municipal ward boundaries |
| Regional Municipal Boundary | boundary | [link](https://open.toronto.ca/dataset/regional-municipal-boundary/) | Study-area extent |

**Jobs / destinations — `destinations`**

| Dataset | Channel | Link | Why |
|---|---|---|---|
| Toronto Employment Survey Summary Tables | destinations | [link](https://open.toronto.ca/dataset/toronto-employment-survey-summary-tables/) | Employment by location = jobs layer |
| Transit Oriented Communities | destinations | [link](https://open.toronto.ca/dataset/transit-oriented-communities/) | Planned high-density nodes near transit |
| Minister-Approved Major Transit Station Areas (120) | stops, destinations | [link](https://open.toronto.ca/dataset/minister-approved-major-transit-station-areas/) | Official densification/transit nodes |

### SUPPORTING — destination & equity-demand layers

**Destinations:** School Locations — All Types ([link](https://open.toronto.ca/dataset/school-locations-all-types/)) · Library Branch General Information ([link](https://open.toronto.ca/dataset/library-branch-general-information/)) · Parks & Recreation Facilities ([link](https://open.toronto.ca/dataset/parks-and-recreation-facilities/)) · Green Spaces ([link](https://open.toronto.ca/dataset/green-spaces/)) · Licensed Child Care Centres ([link](https://open.toronto.ca/dataset/licensed-child-care-centres/)) · EarlyON Child & Family Centres ([link](https://open.toronto.ca/dataset/earlyon-child-and-family-centres/)) · Sexual Health Clinics ([link](https://open.toronto.ca/dataset/sexual-health-clinic-locations-hours-and-services/)) · Ambulance / Fire / Police facility locations · Long-Term Care (City-operated) ([link](https://open.toronto.ca/dataset/long-term-care-locations-city-operated/)) · Places of Interest & Toronto Attractions ([link](https://open.toronto.ca/dataset/places-of-interest-and-toronto-attractions/)) · Cultural Hotspot POIs ([link](https://open.toronto.ca/dataset/cultural-hotspot-points-of-interest/)).

**Equity / transit-dependent populations:** Toronto Community Housing Data ([link](https://open.toronto.ca/dataset/toronto-community-housing-data/)) · Social Housing Unit Density by Neighbourhood ([link](https://open.toronto.ca/dataset/social-housing-unit-density-by-neighbourhoods/)) · Subsidized Housing Listings ([link](https://open.toronto.ca/dataset/subsidized-housing-listings/)) · Affordable Housing Pipeline ([link](https://open.toronto.ca/dataset/upcoming-and-recently-completed-affordable-housing-units/)) · Cost of Living for Low-Income Households ([link](https://open.toronto.ca/dataset/cost-of-living-in-toronto-for-low-income-households/)) · Daily Shelter Occupancy ([link](https://open.toronto.ca/dataset/daily-shelter-overnight-service-occupancy-capacity/)) · Shelter System Flow ([link](https://open.toronto.ca/dataset/toronto-shelter-system-flow/)) · Drop-In (TDIN) Locations ([link](https://open.toronto.ca/dataset/drop-in-locations-toronto-drop-in-network-members-tdin/)).

**Demand growth:** Development Pipeline ([link](https://open.toronto.ca/dataset/development-pipeline/)) · Neighbourhood Intensification Estimates to 2051 ([link](https://open.toronto.ca/dataset/neighbourhood-intensification-estimates-to-2051/)) · Registered Condominiums ([link](https://open.toronto.ca/dataset/registered-residential-non-residential-condominiums/)).

### TANGENTIAL — slight relevance (secondary features / validation)

- **Demand signals:** TTC Ridership Analysis & surface/station ridership · TTC Bus/Subway/Streetcar/LRT Delay Data · Bike Share ridership & stations · Private Transportation Company (Uber/Lyft) trip data · Parking Occupancy / Green P · 311 Service Requests · Labour Force Survey.
- **Walk/access friction:** Sidewalk Inventory & Construction Program · Bridge Structures · TIN (elevation) · Topographic layers (waterbodies / rail / buildings — natural & built barriers) · Road Restrictions · Pedestrian Crossovers.
- **Active-transport last mile:** Cycling Network / Bikeways / Cycling Network Plan · Bicycle Parking · Multi-Use Trails.
- **Safety / Vision-Zero context:** KSI Collisions · Traffic Calming · Watch-Your-Speed / School Safety Zones · Neighbourhood Crime Rates · Red Light Cameras · Traffic Signals & Beacons.
- **Validated corridor evidence:** King St. Transit Pilot suite (Bluetooth travel time, ped/traffic volumes, headway) — real-world before/after benchmark for the reward.
- **Land-use context:** Zoning By-law · Secondary Plans · Site & Area Specific Policies.

---

## Federal — Statistics Canada

Joins cleanly to a Toronto grid because everything shares StatsCan geography codes (DA / DB / CT). Toronto sits inside the Toronto CMA (code 535).

| Dataset | Granularity | Channel | Link | Why |
|---|---|---|---|---|
| ⭐ Census of Population 2021 — Census Profile | DA / CT | population, income, jobs | [link](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm) | Population, age, **income incl. LIM/LICO**, labour, immigration, commuting in one product; finer than city data |
| ⭐ Census 2021 — Boundary Files (DA/DB/CT/CMA/FSA) | polygon | boundary | [link](https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm) | Spatial scaffolding everything rasterizes onto |
| ⭐ Spatial Access Measures (SAM) | DB | stops, destinations, commute | [link](https://www150.statcan.gc.ca/n1/en/catalogue/272600012023001) | Accessibility to jobs/grocery/health/education by **transit (peak & off-peak)**, walk, bike — input feature AND reward benchmark |
| Geographic Attribute File (GAF) | DB | population, boundary | [link](https://open.canada.ca/data/en/dataset/1b3653d7-a48e-4001-8046-e6964bebe286) | DB→DA→CT→CMA crosswalk + block-level population |
| Commuting / Journey-to-Work flows (98-10-0459/0460/0462) | CSD / CMA | commute-demand, jobs | [link](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810046001) | Real O→D demand & mode split. **Caveat: CSD/CMA only — coarser than the grid; use for validation, not per-cell features** |
| Toronto CMA (535) definition | CMA | boundary | [link](https://www150.statcan.gc.ca/n1/pub/92-195-x/2021001/geo/cma-rmr/cma-rmr-eng.htm) | Canonical "Toronto" study extent |

## Provincial — Ontario

| Dataset | Granularity | Channel | Link | Why |
|---|---|---|---|---|
| ⭐ Metrolinx / GO Transit GTFS | point/line/schedule | stops, network, commute | [link](https://www.metrolinx.com/en/about-us/open-data) | Regional rail/bus overlapping Toronto; same GTFS schema as TTC — merges cleanly |
| ⭐ Ontario Marginalization Index (ON-Marg) 2021 | DA / CT | equity | [link](https://www.publichealthontario.ca/en/Data-and-Analysis/Health-Equity/Ontario-Marginalization-Index) | Pre-built DA-level, 4-dimension equity index — higher quality than raw income. ⚠️ Non-commercial/research terms |
| Ontario Road Network (ORN) | line | network | [link](https://data.ontario.ca/dataset/ontario-road-network-orn-composite) | Authoritative road centrelines for travel-time/cost surface |
| Ontario School Locations | point | destinations | [link](https://data.ontario.ca/) | Major demand generators (province-wide) |
| Ontario GeoHub — land use / parcels | polygon | destinations, network, boundary | [link](https://geohub.lio.gov.on.ca/) | Distinguish residential vs. commercial/industrial cells |

### The 5 to wire in first

1. **Census Profile 2021 (DA/CT)** — population + income/equity + jobs in one product.
2. **Census 2021 Boundary Files** — the spatial scaffolding everything joins to.
3. **Spatial Access Measures (SAM)** — transit accessibility; doubles as a reward benchmark.
4. **Metrolinx / GO Transit GTFS** — regional transit, GTFS-compatible with TTC.
5. **ON-Marg equity index** — pre-built DA-level equity channel.

---

## What we already have locally

Files already downloaded under [`data/`](../data/) (see [`data/README.md`](../data/README.md) for original filenames). Map shows how each maps to the catalog above.

| Local path | Catalog entry | Channel | Relevance |
|---|---|---|---|
| `data/transit/ttc-routes-schedules-gtfs/` | TTC Routes & Schedules (GTFS) | stops | **CORE** ✅ |
| `data/geospatial/transit-stations.geojson` | TTC stations geometry | stops, network | **CORE** ✅ |
| `data/geospatial/toronto-centreline.geojson` | Toronto Centreline (TCL) | network | **CORE** ✅ |
| `data/census-demographics/neighbourhood-profiles-2021.xlsx` | Neighbourhood Profiles | population, income | **CORE** ✅ |
| `data/census-demographics/ward-profiles-census-2011-2021.xlsx` | Ward Profiles (census 2011–2021) | population, boundary | **CORE** ✅ |
| `data/census-demographics/ward-profiles-geographic-areas.xlsx` | Ward Profiles (geographic areas) | boundary | **CORE** ✅ |
| `data/surveys/employment-survey-2025.xlsx` | Toronto Employment Survey | destinations (jobs) | **CORE** ✅ |
| `data/geospatial/areas.geojson` | Area boundaries (verify vs. Neighbourhoods 158) | boundary | CORE-ish ⚠️ |
| `data/transit/ttc-ridership-analysis-1985-2019.xlsx` | TTC Ridership Analysis | demand-signal | TANGENTIAL ✅ |
| `data/transit/ttc-bus-delay-2025.csv` | TTC Bus Delay Data | demand-signal | TANGENTIAL ✅ |
| `data/transit/ttc-streetcar-delay-2025.csv` | TTC Streetcar Delay Data | demand-signal | TANGENTIAL ✅ |
| `data/bikeshare/ridership-2025/` | Bike Share Toronto Ridership | demand-signal (last-mile) | TANGENTIAL ✅ |
| `data/traffic/traffic-signals.csv` | Traffic Signals Tabular | network | TANGENTIAL ✅ |
| `data/geospatial/pedestrian-crossovers.geojson` | Pedestrian Crossovers | network (walk) | TANGENTIAL ✅ |
| `data/geospatial/red-light-cameras.geojson` | Red Light Cameras | safety context | TANGENTIAL ✅ |
| `data/geospatial/traffic-beacons.geojson` | Traffic Beacons | safety context | TANGENTIAL ✅ |
| `data/surveys/seniors-survey-2017.xlsx` | Seniors Survey 2017 | equity/demand | TANGENTIAL ✅ |

### Inventory status (updated)

Most of the original CORE gaps are now closed — the following are **already in `data/`**:

- ✅ **Metrolinx / GO Transit GTFS** — `data/transit/go-transit-gtfs/`
- ✅ **Pedestrian Network** (full walk graph) — `data/geospatial/pedestrian-network.geojson`
- ✅ **Intersection File** / **Address Points** — `data/geospatial/intersection-file.geojson`, `address-points.geojson`
- ✅ **Neighbourhoods (158) polygons** — `data/geospatial/neighbourhoods-158.geojson`
- ✅ **Equity designations** — `neighbourhood-improvement-areas.geojson`, `priority-investment-neighbourhoods/`, `wellbeing-civics-equity-indicators.xlsx`
- ✅ **ON-Marg 2021** (DA + n158) — `data/census-demographics/on-marg-2021-*.xlsx`
- ✅ **StatCan 2021 DA boundaries** — `data/census-demographics/statcan-2021-da-boundaries/`
- ✅ **Census Profile 2021** — Census Tract (`census-profile-2021-census-tracts/`) and CMA (`census-profile-2021-cma/`) tables; join to boundaries by DGUID.
- ✅ **Spatial Access Measures (SAM) 2024** — `data/census-demographics/spatial-access-measures-2024/` (incl. `acs_public_transit_peak/offpeak.csv`, `acs_walking.csv`) — accessibility benchmark / reward-validation layer.
- ✅ **Ontario Road Network (ORN)** — `data/geospatial/ontario-road-network/` (file geodatabase) — provincial road network / cost surface.

**Still to fetch:**

- **Census Profile 2021 (per-DA)** — we have CT + CMA tables and DA *boundaries*; the per-DA profile attributes (GEONO=006, large national file) are optional if CT resolution suffices.
- **Demand & feasibility (Phase 3):** Development Pipeline, Neighbourhood Intensification to 2051, Journey-to-Work flows, Zoning By-law.

> **Note on size:** the heaviest local files are gitignored (`data/*` except `README.md`). Census CT CSV ≈ 2.5 GB, ORN ≈ 1.1 GB, address points ≈ 562 MB, SAM ≈ 276 MB, GO GTFS ≈ 178 MB, StatCan DA boundaries ≈ 164 MB. All sourced via the Toronto / open.canada.ca CKAN APIs and direct StatsCan/Metrolinx/Ontario URLs — no browser automation required.

See [Agent Tools §7 — Build phases](agent-tools.md#7-build-phases-grounded-in-whats-already-in-data) for which tools each remaining dataset unblocks.
