# Map Views — Brainstorm & Data Catalogue

A catalogue of map views we can build for TransitRL, grounded in what is
**actually on disk** in `data/`. The current frontend renders one view (the dark
TTC route + stop network). This doc maps out the space of *additional* views, the
exact data each needs, how to join it, and the civic question each answers.

Related: [Project idea](project-idea.md) · the live map lives in `frontend/components/transit-map/`.

---

## 1. How a map view is composed

Every view is a combination of three choices:

```
  CANVAS (geometry)   ×   METRIC (a number/category per shape)   ×   ENCODING (how it looks)
```

- **Canvas** — the geometry we paint onto: neighbourhood polygons, dissemination
  areas (DA), route lines, stop points, a computed grid, or OD line pairs.
- **Metric** — the value joined to each shape: a raw count, a density (per km²),
  a share (%), a rank/quintile, or a composite index.
- **Encoding** — choropleth fill, graduated circles, line width/color, heatmap,
  3D extrusion, or desire lines.

Most "neighbourhood X view" ideas are the **same canvas (158 neighbourhoods) +
a different metric column**. That means once we build one neighbourhood
choropleth with a metric switcher (like the demo's `hoodctl`), adding a new view
is often just adding a column to the join — cheap. The expensive views are the
ones needing a new canvas or a computed surface (coverage, OD, accessibility).

---

## 2. Data inventory (what can drive a view)

### 2.1 Polygon canvases (choropleth bases)

| File | Shapes | Join key | Notes |
|---|---|---|---|
| `geospatial/neighbourhoods-158.geojson` | 158 neighbourhoods (MultiPolygon) | `AREA_SHORT_CODE` (= neighbourhood number) / `AREA_NAME` | **Primary canvas.** Fields: `AREA_SHORT_CODE`, `AREA_NAME`, `AREA_DESC` ("South Eglinton-Davisville (174)"), `CLASSIFICATION` (carries NIA status directly), `OBJECTID`. **No centroid or area field** — compute area geodesically at build time (the demo's `build-neighbourhoods.py` already does this). |
| `geospatial/neighbourhood-improvement-areas.geojson` | 33 polygons (the designated NIAs only) | `AREA_SHORT_CODE` / `AREA_NAME` | Equity designation as actual polygons. Note: `neighbourhoods-158.geojson` already encodes NIA status per neighbourhood via its `CLASSIFICATION` field, so a binary overlay needs no extra join. |
| `geospatial/priority-investment-neighbourhoods/*.shp` | ~13 polygons | name | Older equity designation (shapefile — needs parse). |
| `census-demographics/statcan-2021-da-boundaries/lda_000a21a_e.shp` | all-Ontario DAs (filter to Toronto) | `DAUID` | Finer granularity than neighbourhoods (161 MB shapefile → convert to GeoJSON first). |
| `geospatial/areas.geojson` | 37 polygons | `NAME` | Transit-oriented development / station sites (Ontario Line etc.). |

> No census-tract *boundary* file is on disk (only DA boundaries + CT
> *attributes*). For CT-level views we'd either fetch CT boundaries or aggregate
> DA → CT. Neighbourhood (158) is the most turn-key polygon canvas.

### 2.2 Attribute tables joinable to the 158 neighbourhoods

| File | What it holds | Rows |
|---|---|---|
| `census-demographics/neighbourhood-profiles-2021.xlsx` | **~2,600 census variables** per neighbourhood (the engine for most views) | sheet `hd2021_census_profile`, 2,604 rows × 159 cols (col 0 = variable label, cols 1–158 = neighbourhoods) |
| `census-demographics/on-marg-2021-toronto-n158.xlsx` | ON-Marg 2021 — 4 marginalization dimensions (quintiles) | sheet `Neighb_Toronto_ON-Marg2021`, 161 rows |
| `census-demographics/wellbeing-civics-equity-indicators.xlsx` | Wellbeing Toronto civics/equity indicators — **reference periods 2008 & 2011 (stale)**, and ~140 data rows suggest the **legacy 140-neighbourhood model** (needs a crosswalk to the 158 model before joining) | ~140 rows × 2 periods |
| `surveys/employment-survey-2025.xlsx` | Jobs / business counts — **city-wide summary tables (Tables 1–7), NOT per-neighbourhood**; useful for context, not a choropleth join | 7 tables |
| `surveys/seniors-survey-2017.xlsx` | Seniors' needs/experience | survey |

> **Verification note.** The variable families below were confirmed by parsing
> the sheet directly (labels in **column 0**, neighbourhood values in columns
> 1–158). Anchor row numbers are the *header* row of each family; sub-categories
> follow beneath. They're 2021-profile-specific — re-confirm at build time rather
> than hard-coding.

**Variable families confirmed present in `neighbourhood-profiles-2021.xlsx`** (each
populated across all 158 neighbourhood columns):

- **Age** — full age bands, average/median age, children (0–14), seniors (65+, 85+); the age block starts at row 4 (`Total - Age groups…`).
- **Income** — income statistics block at **row 62** (`Total - Income statistics in 2020…`): median/average total, after-tax, market, employment income; income composition; low-income measures below.
- **Housing / tenure** — dwelling structural type at **row 217**; **tenure at row 300** (`Owner` 301, `Renter` 302); condominium status (304), bedrooms/rooms; **unaffordability at row 352** (`households spending 30%+ of income on shelter`).
- **Immigration** — immigrant status & period at **row 1486** (`Immigrants` 1488, `Non-permanent residents` 1496); recent-immigrant place of birth at 1563.
- **Visible minority** — `Total - Visible minority…` at **row 1642**.
- **Education** — highest certificate at **row 1982** (`No certificate` 1983 → `Bachelor's degree or higher` 1992 → `Postsecondary…` 1985).
- **Occupation** — labour force by the **10 broad NOC categories** at **rows 2219–2231**:
  `Total - Labour force … by occupation` (2219), `All occupations` (2221), then
  `0` management (2222) · `1` business/finance/admin (2223) · `2` natural & applied sciences (2224) ·
  `3` health (2225) · `4` education/law/social/community/government (2226) · `5` art/culture/recreation/sport (2227) ·
  `6` sales & service (2228) · `7` trades/transport/equipment (2229) · `8` natural resources/agriculture (2230) ·
  `9` manufacturing & utilities (2231). *Confirmed real values, e.g. in neighbourhood #1: NOC 6 = 4,805; NOC 7 = 3,685; NOC 1 = 2,915.*
- **Industry** — labour force by NAICS sector at **rows 2232–2250+** (`23 Construction`, `31-33 Manufacturing`, `44-45 Retail trade`, `54 Professional/scientific/technical`, `62 Health care & social assistance`, etc.).
- **Commute** — **main mode of commuting** at **rows 2576–2582** (`Car, truck or van` 2577 — driver 2578 / passenger 2579 — `Public transit` 2580, `Walked` 2581, `Bicycle` 2582); **commuting duration** at row 2584; **time leaving for work** at row 2590.

> Population & density: the profile has `Population, 2021` but **no
> density column** — compute it from population ÷ geodesic polygon area at build
> time (as the demo's `build-neighbourhoods.py` does).

### 2.3 Attribute tables at fine (DA / dissemination-block) granularity

| File | What it holds |
|---|---|
| `census-demographics/spatial-access-measures-2024/acs_public_transit_peak.csv` (+ `_offpeak`, `acs_walking`, `acs_cycling_*`) | StatsCan accessibility indices **per dissemination block** (key `DBUID`) — normalised access to: employment (`acs_idx_emp`), health facilities (`acs_idx_hf`), childcare (`acs_idx_ccf`), primary/secondary ed (`acs_idx_ef`), post-secondary (`acs_idx_psef`), culture/arts (`acs_idx_caf`), sports/rec (`acs_idx_srf`), plus grocery travel-time levels (`acs_lvl_gs-1/3/5`) — for transit (peak/offpeak), walking, and cycling profiles. **Aggregate DB → neighbourhood/DA for a choropleth.** |
| `census-demographics/census-profile-2021-census-tracts/` (2.5 GB) | Full census profile at CT level (attributes only; no CT boundary on disk). |
| `census-demographics/on-marg-2021-ontario-DA.xlsx` | Marginalization at DA level. |

### 2.4 Network & line layers

| File | What it holds |
|---|---|
| `transit/ttc-routes-schedules-gtfs/` | TTC GTFS: 236 routes, 9,369 stops, 105k trips, 3.3M stop_times → **service frequency** is derivable. |
| `transit/go-transit-gtfs/` | GO regional rail/bus GTFS (a whole regional-rail layer). |
| `geospatial/toronto-centreline.geojson` (89 MB) | Street/path centreline. |
| `geospatial/pedestrian-network.geojson` (36 MB) | Walk graph (for true walk-sheds vs. circular buffers). |

### 2.5 Point layers (for density / point-pattern / dot views)

| File | Points | Use |
|---|---|---|
| `transit/ttc-routes-schedules-gtfs/stops.txt` | 9,369 | stop density, coverage |
| `bikeshare/ridership-2025/*.csv` | millions of trips, 12 months | **OD flows**, station demand, member vs casual, e-bike vs classic |
| `geospatial/address-points.geojson` (562 MB) | ~500k | built-density proxy / denominator |
| `geospatial/intersection-file.geojson` (33 MB) | all intersections | street connectivity / walkability |
| `traffic/traffic-signals.csv` | 2,545 | signal density |
| `geospatial/red-light-cameras.geojson` | 301 | safety enforcement |
| `geospatial/pedestrian-crossovers.geojson` | 498 | pedestrian infrastructure |
| `geospatial/traffic-beacons.geojson` | 360 | pedestrian infrastructure |
| `transit/ttc-bus-delay-2025.csv` / `ttc-streetcar-delay-2025.csv` | delay events w/ line, station, min-delay, bound | **reliability** by location/line |
| `geospatial/transit-stations.geojson` | 37 | future/planned GO stations |

---

## 3. The view catalogue

Grouped into families. Each entry: **what it shows · data + join · encoding ·
the civic question it answers · effort**. Effort is *Low* (column swap on an
existing choropleth), *Med* (new join/computation), *High* (new canvas or heavy
geoprocessing).

### Family A — Demographic choropleths (canvas: 158 neighbourhoods)

These all share one canvas + metric switcher. Build the switcher once.

1. **Population** — raw `Population, 2021`. *Where the people are.* — Low
2. **Population density** (per km²) — the demo's "density" view. *Where they're concentrated.* — Low
3. **Senior share (65+/85+)** — age bands ÷ population. *Where mobility-limited riders cluster.* — Low
4. **Children share (0–14)** — *School-trip and stroller-access demand.* — Low
5. **Median household income** / **after-tax** — *Affluence gradient.* — Low
6. **Low-income prevalence (LIM-AT)** — *Where transit is a lifeline, not a choice.* — Low
7. **Recent-immigrant share** — *Newcomer settlement; transit-reliant populations.* — Low
8. **Visible-minority share** — *Racialized geography (pair with coverage for equity).* — Low
9. **Renter share (tenure)** — *Housing precarity, turnover.* — Low
10. **Housing unaffordability** (shelter cost >30% income) — *Cost-burdened households.* — Low
11. **Apartment/high-rise share** (dwelling type) — *Built density → transit viability.* — Low
12. **Education (bachelor's+ share)** — *Skill geography.* — Low
13. **Household size / persons-per-room (crowding)** — *Overcrowding hotspots.* — Low
14. **No-knowledge-of-official-language share** — *Language-access need for signage/info.* — Low

### Family B — "Density of X profession" (canvas: 158 neighbourhoods)

The 10 broad NOC occupation rows (1822–1841) + NAICS industry rows. Each is a
choropleth of *share of the working labour force* (count ÷ total labour force).

15. **Health workers** (NOC 3) — *Where the care workforce lives; shift-work transit needs.* — Low
16. **Trades / transport / equipment operators** (NOC 7) — *Blue-collar geography; often off-peak commuters.* — Low
17. **Sales & service** (NOC 6) — *Lowest-wage, most transit-dependent occupations.* — Low
18. **Business / finance / admin** (NOC 1) — *Downtown-oriented office commuters.* — Low
19. **Sciences & tech** (NOC 2) — *Knowledge-economy clusters.* — Low
20. **Art / culture / recreation** (NOC 5) — *Creative-class neighbourhoods.* — Low
21. **Management** (NOC 0) — *Executive/affluent corridors.* — Low
22. **Industry-sector view** (NAICS switcher) — same idea by sector (manufacturing, retail, healthcare, education, etc.). — Low
23. **Dominant-occupation categorical map** — each neighbourhood colored by its
    *largest* occupation group (a categorical, not graduated, choropleth). *One
    glance: "what does this neighbourhood do for work?"* — Med

### Family C — Mobility behaviour (canvas: 158 neighbourhoods)

From the commute-mode rows (1864–1881). These tie demographics directly to transit.

24. **Public-transit commute share** — % who commute by transit. *Existing transit
    reliance — the single most on-mission demographic view.* — Low
25. **Car-dependence** — % car driver+passenger. *Where transit hasn't won (or can't).* — Low
26. **Active transport** — % walk + bike. *Walkable cores.* — Low
27. **Long-commute burden** — % commuting 60+ min. *Time-poverty geography.* — Low
28. **"Transit captive" estimate** — transit-commute share among low-income +
    no-vehicle households. *Riders with no alternative — priority for service.* — Med
29. **Mode-share small-multiples / radial glyph per neighbourhood** — mini mode
    split per area instead of one metric. — Med

### Family D — Equity & marginalization overlays

30. **ON-Marg: Material Deprivation** quintiles — *Material poverty.* — Low
31. **ON-Marg: Residential Instability** — *Housing churn / renters / movers.* — Low
32. **ON-Marg: Dependency** (age & labour force) — *Non-working-age load.* — Low
33. **ON-Marg: Racialized & Newcomer Populations** — *Concentration; equity lens.* — Low
34. **Neighbourhood Improvement Areas overlay** — binary designation outline on top
    of any choropleth. *City's own equity priority list.* — Low
35. **Composite marginalization** — average of the 4 ON-Marg quintiles. *Overall
    disadvantage in one layer.* — Med

### Family E — Transit supply (canvas: lines, stops, computed grid)

36. **Route network** (current view) — modes colored, glow + core. — *done* ✓
37. **Stop density** — kernel/grid heat of the 9,369 stops. *Where the network is
    dense vs. sparse.* — Med
38. **Service frequency** — color routes/stops by trips/hour from GTFS
    `stop_times`+`trips`. *Not just "is there a route" but "how often."* — Med
39. **Frequent Transit Network** — highlight only routes with ≤10-min headways.
    *The actually-useful network.* — Med
40. **Coverage / walk-shed** — 400 m buffers around stops → % population covered;
    color the *gaps* (demo's coverage view). *Who's beyond walking distance.* — High
41. **True walk-shed** — same but using `pedestrian-network.geojson` (network
    distance, not circular buffers). More honest, more work. — High
42. **GO regional-rail layer** — GO GTFS lines + planned `transit-stations`. *Regional
    context / future stations.* — Med

### Family F — Accessibility (canvas: dissemination block → aggregated, from Spatial Access Measures)

The SAM 2024 indices already encode "how much can you reach by mode X" per
dissemination block (`DBUID`); aggregate up to neighbourhood/DA to paint.

43. **Accessibility to jobs by transit** (`acs_idx_emp`, transit-peak) — *Opportunity
    reachable without a car.* — Med
44. **Access to healthcare / grocery / childcare by transit** — same, other amenities.
    *Essential-service reach.* — Med
45. **Transit-vs-car accessibility ratio** — transit index ÷ (a car proxy or walking).
    *The "transit penalty" — where not owning a car costs you the most.* — Med
46. **Peak vs off-peak access gap** — `acs_public_transit_peak` − `_offpeak`. *Who
    loses service evenings/weekends (shift workers).* — Med
47. **Cycling accessibility (AAA)** — `acs_cycling_all_ages_and_abilities`. *Bike-network
    reach; pair with bikeshare demand.* — Med

### Family G — Demand & flows

48. **Bikeshare demand** — graduated circles per station (trip counts). *Where
    micro-mobility is hot — first/last-mile signal.* — Med
49. **Bikeshare OD desire lines** — real origin→destination flows (not modelled).
    *Actual movement patterns; transit-gap corridors.* — Med
50. **Member vs casual bikeshare** — split demand by `User_Type`. *Commuters vs
    tourists.* — Med
51. **E-bike vs classic** — by `Bike_Model`. *Where electric assist unlocks hillier/longer trips.* — Low–Med
52. **Gravity-model OD** — modelled desire lines from population×population×e^(−βd)
    (demo's OD view). *Latent demand where no direct service exists.* — High
53. **Bikeshare ↔ transit-gap overlay** — bikeshare hotspots *outside* transit
    coverage. *Where people improvise around missing transit.* — High

### Family H — Reliability

54. **Delay hotspots** — aggregate bus/streetcar delay events by station/intersection
    → heat or graduated points. *Where service is unreliable.* — Med
55. **Worst routes by delay** — rank lines by total/avg min-delay; color the network.
    *Which lines fail riders most.* — Med
56. **Delay cause breakdown** — by `Code` (mechanical, security, etc.). — Med

### Family I — Built environment & safety (point/line layers)

57. **Intersection density** — connectivity proxy from `intersection-file`. *Walkable
    grid vs. cul-de-sac sprawl.* — Med
58. **Address-point / building density** — ~500k points → density surface. *Built
    form; a denominator for "stops per building."* — High (big file)
59. **Pedestrian infrastructure** — crossovers + beacons + signals as a safety layer.
    *Walk-to-transit safety.* — Low
60. **Red-light cameras / collisions-adjacent** — enforcement geography. — Low
61. **Traffic-signal density** — `traffic-signals.csv` (2,545). *Auto-priority corridors.* — Low

### Family J — Composite analytical indices (the "so what" views)

These combine layers into a single decision-relevant surface — the most
TransitRL-aligned, since they mirror the RL reward terms.

62. **Transit Need Index** — combine low-income + senior + no-vehicle + recent-immigrant
    + transit-commute share. *Where transit *should* be strong.* — Med
63. **Need vs. Supply gap** — Transit Need Index − (stop density or frequency).
    *High-need, low-service neighbourhoods = intervention targets.* — High
64. **Equity-weighted coverage gap** — coverage gap (Family E) weighted by
    marginalization (Family D). *Who's being left behind, weighted by vulnerability —
    the core civic question of the project.* — High
65. **Opportunity access score** — SAM job-access × equity weight. *Does transit
    connect disadvantaged areas to jobs?* — High
66. **15-minute-city score** — count of amenity types reachable in 15 min by transit
    (from SAM). *Complete-community geography.* — Med

---

## 4. Cross-cutting notes

### Join keys
- **Neighbourhood (158):** polygons key on `AREA_SHORT_CODE`; the profiles sheet
  exposes the same value in its `Neighbourhood Number` row (row 2), and ON-Marg
  keys on the same number. Polygon `AREA_DESC` carries the parenthesised form
  (`"South Eglinton-Davisville (174)"`) if you need to match on name. This is the
  cheapest, richest join in the dataset. **Caveat:** the Wellbeing file uses the
  older 140-neighbourhood model — crosswalk before joining.
- **DA / dissemination block:** SAM keys on `DBUID` (dissemination *block*);
  DA census + DA boundaries key on `DAUID`. Finer, but needs the 161 MB
  shapefile parsed to GeoJSON and DB→DA/neighbourhood aggregation first.
- **Stations/stops:** GTFS `stop_id`; bikeshare by station name/id (geocode from
  trip records or a station feed).

### Granularity trade-off
158 neighbourhoods = instant, legible, every demographic attached, but coarse
(averages hide block-level variation). DAs = finer and truer but heavier and
need geometry prep. **Recommendation:** ship all demographic/equity/occupation/
mobility views on the 158-neighbourhood canvas first (Families A–D, J); reserve
DA for accessibility (Family F) where the data only exists at DA level.

### Reuse the demo's pattern
`build-neighbourhoods.py` in the old `ttc-map/` demo already joins the profiles
xlsx to the polygons, computes geodesic area/density, rounds coordinates, and
emits a compact `neighbourhoods.json`. Extend that script to emit **all** the
metric columns above into one properties blob, then the frontend just switches
which property it paints — most of Families A–D become a single build step + a
metric dropdown.

### TransitRL relevance
The composite indices (Family J) are not just pretty maps — they *are* the RL
reward channels made visible: coverage, travel-time/job-access, equity weighting,
and need-vs-supply gap. Building these views doubles as building (and debugging)
the simulation's reward terms.

---

## 5. Suggested build order

1. **Neighbourhood choropleth engine** + metric switcher (unlocks ~30 views at
   Low effort: Families A, B, C, D). One build-data step, one dropdown.
2. **Coverage / walk-shed** (Family E #40) — high value, mirrors a reward term.
3. **Accessibility (SAM)** job-access by transit (Family F #43).
4. **Composite: Equity-weighted coverage gap** (Family J #64) — the headline view.
5. **Bikeshare OD / demand** (Family G) and **delay reliability** (Family H) as
   richer, real-data flow/quality layers.
