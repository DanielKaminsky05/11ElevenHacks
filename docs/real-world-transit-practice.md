# How Cities Actually Plan & Adapt Transit — A Reference for TransitRL

What real transit agencies and host cities do — both in routine route planning and when a shock
(a World Cup, a line closure) hits. This grounds TransitRL's simulation "physics", the
[event-shock parameters](#6-grounding-the-event-shock-feature), the reward design
([`reward-and-optimizer.md`](reward-and-optimizer.md)), and the agent's narration in actual
planner practice — so the tool is defensible to a transit-literate judge.

> **The two clocks.** Cities plan on two timescales, and they're separate disciplines:
> **routine network planning** (years — redesign routes, move stops, set frequency) and
> **short-term adaptation** (minutes→months — event surges, disruptions, construction). TransitRL
> touches both; the event feature lives in the second.

---

## 1. The master trade-off: ridership vs coverage

Routine planning hangs on one budget-constrained choice (Jarrett Walker's framing the whole
industry uses):

- **Ridership goal** → concentrate service on dense, walkable, **linear** corridors. Frequent
  service, short waits, more riders per dollar — but longer walks for the periphery.
- **Coverage goal** → spread service so everyone lives near a stop. Universal "lifeline" access
  and geographic equity — but low, "less useful" frequency.

They lead in opposite directions: under a fixed budget, more of one means less of the other.
Agencies adopt an explicit **service-allocation split** (e.g. "60% ridership / 40% coverage") that
turns a values question into a planning input. **This is exactly what TransitRL's `parse_goal`
reward weighting encodes** — every user goal picks a point on this spectrum.

Ridership-potential geometry (what makes a corridor worth frequency): **density × walkability ×
linearity × proximity**, plus land-use mix. High-frequency **grids** beat radial hub-and-spoke for
anywhere-to-anywhere travel because frequency makes transfers painless.

---

## 2. The routine planning process & service standards

**Process (steady state):** monitor (APC counts, reliability, feedback) → annual route-performance
review against standards → annual service plan (equity-assessed, ranked by cost vs benefit, board
approval) → ≥12-month trial → keep / modify / remove. Comprehensive **network redesigns** happen
periodically (~3 years, often consultant-led).

**Concrete numbers (from TTC's published Service Standards — a real agency example):**

| Standard | Value |
|---|---|
| Walkshed coverage | 90% of population within **400 m** of service |
| Stop spacing | local bus/streetcar **300–400 m**; express **800–1,200 m** |
| Min frequency / span | local bus ≥ every 30 min; rapid transit ≤ 6 min |
| Add service | crowding **>95%** of standard for 6 months |
| Cut service | crowding **<80%** for 6 months (never below the frequent-network floor) |
| Economic review | routes in the **bottom 10%** of their class → compulsory review |

**The net-benefit test** decides changes: a change must reduce *weighted* travel time, where
**wait ×1.3, walk ×1.8, and a mixed-traffic transfer ×6.0** (in-vehicle = 1.0). This is *why*
planners avoid forcing painful transfers and prefer frequency that makes transfers cheap — and it
maps directly to TransitRL's travel-time and coverage reward terms.

**Decision rule, in TransitRL terms:** add/move a stop when spacing is outside the class standard
*and* it captures dense/transit-dependent demand *and* it yields a net weighted-time benefit —
never if it clusters on a hotspot or violates speed/economic standards.

---

## 3. Equity is mandatory practice, not a nicety

This validates TransitRL's headline ("who gets left behind") as real regulation:

- **US FTA Title VI** requires a **Service Equity Analysis** for any *Major Service Change*
  (defined as **±25% of a route's weekly revenue hours**, or **moving a stop > ¼ mile**), testing:
  - **Disparate Impact** — disproportionate harm to a racial/ethnic group, and
  - **Disproportionate Burden** — disproportionate harm to **low-income** riders (≤150% of poverty).
  If found, the agency must avoid / minimize / mitigate.
- **Beyond compliance:** TTC applies an **equity-weighted productivity** measure — boardings within
  400 m of its 31 **Neighbourhood Improvement Areas** are weighted **125%**, raising the bar before
  such a route can be cut.

TransitRL's equity reward weight and `who_is_affected` (winners/losers by income) are the
computational form of Title VI's two tests.

---

## 4. The mega-event playbook (World Cup, Olympics, Super Bowl)

Four levers, in rough order of leverage:

1. **Suppress car demand structurally** — minimal/no stadium parking + park-and-ride (Sydney 2000,
   the gold standard).
2. **Free, ticket-integrated transit** — highest-leverage single move; removes the post-event fare
   bottleneck (Qatar 2022's Hayya fan card → free transit; **17.4M metro trips**, peak 827k/day).
3. **Boost supply** — extra frequency, extended hours, borrowed/chartered fleet, dedicated event
   shuttles, transit-only lanes (Paris 2024 +15% service; London 2012 Olympic Route Network).
4. **Manage demand & crowd flow** — staggered start times, TDM ("**Reduce, Re-time, Re-route,
   Re-mode**"), metered/pulse loading, staged empty trains for egress.

**The quantitative chain planners run:**
`expected attendance → person-trips → mode share (a policy lever, not just a forecast) → required capacity per mode`.

**The one rule that dominates: egress is the binding constraint, not ingress.** Fans *arrive*
spread over 2–3 hours but a 60k stadium *empties* in 30–60 min — that post-event spike is where
networks break. Atlanta 1996 (lost out-of-town shuttle drivers; "unmitigated transport disaster")
and Detroit's Super Bowl XL (68k leaving at once) both failed on egress. **Stadium location
pre-determines difficulty:** downtown + rail = easy mode (Seattle, Doha); suburban + parking lot =
a fragile bus-shuttle layer where driver familiarity and dispatch are single points of failure
(Atlanta, Kansas City's Arrowhead).

---

## 5. Toronto's actual FIFA World Cup 2026 plan

Toronto hosts **6 matches at BMO Field** ("Toronto Stadium", ~45k) on **June 12, 17, 20, 23, 26 and
July 2**. The City's official Mobility Plan is "transit-first":

- **Mode-share target: 70% transit** (TTC + GO), 13% active, 10% taxi/rideshare, **7% car**.
  Modelled ~36k to the stadium + ~25k to the Fan Fest (Fort York / The Bentway).
- **Departure profile** (the egress surge to model): **70% leave within 1 hour**, 25% within 2, 5%
  within 3. Arrival: 20% at T-3h, 50% at T-2h, 30% at T-1h.
- **Infrastructure:** Exhibition Loop **closed on match days** → temporary **Fleet Street Transit
  Hub**; **RapidTO transit-only red lanes** on Dufferin & Bathurst; streetcar frequency boosts
  (504 King 5→4 min, 509 Harbourfront 12→8 min, 511 Bathurst 10→6 min); **GO Lakeshore at 15-min**
  service Jun 10–Jul 5; **no public parking** near the venue; Liberty Village local-traffic-only.
- **The Line 2 Jane–Ossington closures (incl. the May 30–31 weekend) are confirmed *pre-tournament
  trackwork*** rushed to finish before the June crowds — *not* match-day operations. This is the
  real context behind that mock event in `app/data/events_mock.py`.

**Cross-host-city pattern (2026):** no stadium parking + advance-purchase shuttles +
**ticket-gated, capacity-capped rail** (NY/NJ caps NJ Transit at **40k/match**, ticket-holders only;
Boston ~20k/match on advance-only "Stadium Trains").

---

## 6. Short-term adaptation: disruptions, surges, construction

- **Operational control (minutes):** from a control centre — **holding**, **short-turning**,
  **stop-skipping**, injecting staged **"gap" buses**, headway management to fight bunching.
- **Bus bridging** (rail replacement) is the standard for closures, and *sizing* it is the hard
  part because buses can't match rail capacity. There's a **TTC-validated optimization** (genetic
  algorithm) that jointly decides how many shuttles to deploy **and which routes to pull them
  from**, constrained by bus-bay capacity → **>50% rider-delay reduction** vs ad-hoc. Express +
  all-stop shuttle patterns combine for faster turnaround.
- **Surge response:** extra trips/longer consists, real-time crowd monitoring (TfL's IoT + AI
  platform diverted thousands from overcrowded central stations during the 2025 London Marathon),
  station-level **capping/gating**, and capacity-aware trip planning (Paris 2024 routed travellers
  *away* from the fastest/most-crowded paths).
- **Construction (months):** sustained shuttles, temporary stops, weekend/overnight scheduling,
  extra accessible vehicles, phased closures, heavy rider communication.

**Real-time data substrate:** AVL/GPS (bunching/gaps), APC (loads/crowding), fare-tap (O-D),
IoT density sensors (capping), GTFS-realtime alerts (push to apps).

---

## 7. Grounding the event-shock feature

How this maps onto TransitRL's [`events` tools](../backend/app/tools/events.py) and the simulation:

| Real practice | TransitRL representation |
|---|---|
| attendance → trips → **mode share** → capacity | `TransitImpact.expected_attendance` + a mode-share assumption → demand bump |
| **egress surge** (70% leave in 1 h) dominates | model the post-event spike, not the average; shock has a sharp post-window |
| demand surge spreads ~2 km from venue | `TransitImpact.radius_km` with gravity-style falloff |
| line closure + **bus bridging** | `supply_disruption` + `shuttle_replacement`; the *response* mirrors the TTC bus-bridging optimization (which the optimizer can echo) |
| ridership vs coverage split | `parse_goal` reward weighting |
| Title VI disparate impact / disproportionate burden | equity reward weight + `who_is_affected(by=income)` |
| 400 m walkshed, 300–400 m spacing, transfer penalties | accessibility tool + constraint checks (H4–H6 in `agent-workflows.md`) |

**Credible demo defaults** (from Toronto's plan): 70% transit mode-share; the 20/50/30 arrival and
70/25/5 departure profiles; surge radius ~2–2.5 km around BMO Field.

**Honesty boundary (unchanged):** TransitRL models accessibility/equity and *what-if* shocks — it
is **not** a ridership/demand forecast. Real agencies use APC/fare/O-D data and demand models for
that; our shock magnitudes are transparent, stated assumptions, not predictions.

---

## Sources

**Routine planning & equity**
- [The Ridership–Coverage Tradeoff — Human Transit (Jarrett Walker)](https://humantransit.org/2018/02/basics-the-ridership-coverage-tradeoff.html)
- [TTC Service Standards and Decision Rules (May 2024, PDF)](https://cdn.ttc.ca/-/media/Project/TTC/DevProto/Documents/Home/About-the-TTC/Projects-Landing-Page/Transit-Planning/Service-Standards_May-2024.pdf)
- [Bus Network Redesigns in the Modern Age — Eno Center](https://enotrans.org/article/bus-network-redesigns-in-the-modern-age-how-u-s-transit-agencies-adapt-to-evolving-travel/)
- [Houston redesign ridership outcome — Kinder Institute, Rice](https://kinder.rice.edu/urbanedge/year-after-bus-redesign-metro-houston-ridership)
- [TCRP Report 19: Location & Design of Bus Stops (PDF)](https://onlinepubs.trb.org/onlinepubs/tcrp/tcrp_rpt_19-a.pdf)
- [FTA Title VI Service & Fare Equity Analyses](https://www.transit.dot.gov/regulations-and-guidance/civil-rights-ada/title-vi-service-fare-equity-analyses-video-transcript)

**Mega-event playbook**
- [London 2012 Travel Demand Management — Steer](https://steergroup.com/insights/news/understanding-london-2012-transport-success-story)
- [Olympic Route Network — Wikipedia](https://en.wikipedia.org/wiki/Olympic_route_network)
- [Qatar 2022 transport legacy — FIFA](https://www.fifa.com/en/articles/legacy-in-action-qatar-2022s-state-of-the-art-transport-systems)
- [Paris 2024 transport — Wikipedia](https://en.wikipedia.org/wiki/Transportation_during_the_2024_Summer_Olympics_and_Paralympics)
- [Sydney 2000 transport — The Conversation](https://theconversation.com/olympics-transport-how-did-sydney-handle-it-8249)
- [Atlanta 1996 'unmitigated transport disaster' — Creative Loafing](https://creativeloafing.com/content-214744-atlanta-olympics-were-an-unmitigated-transport)
- [To host the World Cup, KC built a new transit system — NPR](https://www.npr.org/2026/05/20/nx-s1-5818565/world-cup-kansas-city-new-transit-system)

**FIFA World Cup 2026 — Toronto & host cities**
- [City of Toronto — FIFA World Cup 2026 Mobility Plan](https://www.toronto.ca/news/city-of-toronto-releases-fifa-world-cup-2026-mobility-plan/)
- [Toronto's World Cup Transit Plan — Steve Munro](https://stevemunro.ca/2026/03/27/torontos-world-cup-transit-plan/)
- [TTC — Line 2 Jane–Ossington full weekend closure May 30–31, 2026](https://www.ttc.ca/service-advisories/subway-service/Line-2--Jane-to-Ossington-Full-weekend-closure-May-30-to-31-2026)
- [NJ Transit — NY/NJ Regional Stadium Mobility Plan](https://www.njtransit.com/press-releases/fifa-world-cup-2026tm-new-york-new-jersey-host-committee-and-nj-transit-announce)
- [How cities are preparing for FIFA World Cup 2026 — Smart Cities Dive](https://www.smartcitiesdive.com/news/fifa-world-cup-transportation-challenges/818604/)

**Real-time / disruption / construction**
- [Capacity-Constrained Bus Bridging Optimization (TTC data) — SAGE/TRR](https://journals.sagepub.com/doi/abs/10.1177/0361198120917399?journalCode=trra)
- [Optimizing Bus Bridging in Response to Rail Disruptions — INFORMS](https://pubsonline.informs.org/doi/10.1287/trsc.2014.0577)
- [From Research to Practice: Real-Time Control to Avoid Bus Bunching — Mass Transit](https://www.masstransitmag.com/technology/article/12358944/from-research-to-practice-implementing-real-time-control-to-avoid-bus-bunching)
- [Rail replacement bus service — Wikipedia](https://en.wikipedia.org/wiki/Rail_replacement_bus_service)
- [TTC subway closures & service adjustments](https://www.ttc.ca/news/2026/May/Upcoming-subway-closures-and-service-adjustments)
