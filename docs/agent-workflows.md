# TransitRL — Agent Workflows & Planner Mental Models

How a human transit planner *thinks* through real tasks — what they look for, what
information they request, in what order, and why — translated into the tool sequences the
Nemotron agent should run. This is the bridge between the [data layer](data-layer.md), the
[tools](agent-tools.md), and an agent that reasons like a planner instead of a chatbot.

Use this doc two ways: (1) as the **design spec** for the agent's planning behavior, and
(2) as the source of **few-shot planning patterns** to put in the agent's system prompt (each
workflow below is a ready-made reasoning template).

---

## 1. The universal planner loop (the meta-model)

Every transit-planning question, no matter how it's phrased, is worked through the same six
cognitive stages. The five tool families map almost 1:1 onto them — *the tool families are the
stages of planner cognition.*

| Stage | The planner's internal question | Tool family |
|---|---|---|
| **1. Understand** | "Who and what is here? What exists already?" | A — City State & Lookup |
| **2. Diagnose** | "Is there a real problem? Where, how big, for whom?" | B — Accessibility & Equity Diagnostics |
| **3. Frame** | "What exactly am I optimizing, and for whom, under what limits?" | D — `parse_goal` |
| **4. Generate** | "What are the candidate interventions?" | C/D — `simulate_change`, `optimize_layout` |
| **5. Evaluate** | "What does each option do — and who wins/loses?" | C/E — `simulate_change`, `diff_scenarios`, `who_is_affected` |
| **6. Justify** | "Can I defend this to a councillor / the public?" | E — `explain_result`, `generate_brief` |

> **Golden rule of the loop: never skip to Generate.** A planner who proposes a route before
> diagnosing the gap is guessing. The agent must **diagnose before it optimizes**, and
> **attribute (who loses) before it recommends.** Most bad answers come from jumping straight
> to stage 4.

---

## 2. The domain heuristics the agent must internalize

These are the "physics" of transit planning. They are *why* the planner asks what they ask.
Bake them into the system prompt so the model's tool choices and narration are transit-literate.

- **H1 — Ridership ⇄ Coverage is a spectrum, and every goal picks a point on it.** Maximize
  *ridership* → concentrate frequent service on dense, linear, destination-rich corridors.
  Maximize *coverage* → spread service thin so everyone gets a little. You can't max both with
  a fixed budget. `parse_goal` literally encodes the chosen point as reward weights — name the
  trade-off out loud.
- **H2 — Demand ≈ density × destinations × transit-dependence.** People ride where many
  origins connect to many destinations and alternatives (cars) are scarce. A corridor with
  people but no destinations (or destinations but no people) won't perform.
- **H3 — Weight the transit-dependent.** Low-income, car-less, seniors, youth, recent
  immigrants, and people with disabilities have no alternative — equity weighting exists
  because a stop matters *more* to someone with no other option.
- **H4 — The 400 m walkshed.** Access = share of population within ~400 m walk of a stop
  (~800 m for rapid transit). Stop spacing ~300–400 m trades **access (closer = better) vs
  speed (fewer stops = faster)**. This is the single most-used number in the toolkit.
- **H5 — Directness sells.** Good routes are reasonably straight along arterials connecting
  strong anchors. Every detour to "cover" one more pocket slows everyone and sheds riders.
- **H6 — Value comes from the network, not the line.** A route's worth includes the
  **transfers** it enables (to subway/GO/frequent routes) and the duplication it **avoids**.
  Always check what already exists.
- **H7 — Barriers break walksheds.** Rivers, rail corridors, highways, and steep grades mean a
  stop "400 m away" across a barrier is effectively unreachable. Euclidean distance lies;
  respect the network and physical barriers.
- **H8 — Every reallocation has losers.** Moving/adding service under a budget takes from
  somewhere. A recommendation without a winners-*and*-losers breakdown is not a recommendation.
- **H9 — Access ≠ ridership ≠ a demand forecast.** TransitRL models *accessibility and equity*,
  not predicted ridership. State this; it's the first thing a transit-literate judge probes.

---

## 3. Data layer → planner question (reverse index)

What each dataset is actually *for*, phrased as the planner question it answers. (Full catalog
+ local availability in [`data-layer.md`](data-layer.md).)

| The planner asks… | Data layer | Channel |
|---|---|---|
| "Who lives here, how many, how dense?" | Census / Neighbourhood Profiles (population, age) | population |
| "Are they transit-dependent / underserved vs need?" | Census income, ON-Marg, Neighbourhood Improvement Areas, Priority Investment | income, equity |
| "Where do they need to go?" | Employment Survey (jobs), schools, hospitals, libraries, child care | destinations |
| "What service exists right now?" | TTC + GO GTFS (routes/stops), subway shapefiles | stops, network |
| "Can people *walk* to a stop? Can a *bus* run here?" | Centreline, Pedestrian Network, Intersections, road network | network |
| "Where do trips actually go?" | Journey-to-Work O-D flows, ridership analysis | demand-signal |
| "Where is service unreliable/slow?" | TTC Bus/Streetcar/Subway Delay, GTFS-RT | demand-signal |
| "Where is demand *growing*?" | Development Pipeline, Intensification-to-2051, TOC / Major Transit Station Areas | demand-signal |
| "Is my access number *credible*?" | StatCan Spatial Access Measures (SAM) — validated benchmark | (validation) |
| "What's physically/legally feasible?" | Zoning, land use, barriers (rail/water/topo), road restrictions | network, boundary |
| "What unit do I report in?" | Neighbourhoods-158, Wards | boundary |

---

## 4. The workflows

Each is a mental model: **Trigger → What they're really asking → How a planner reasons (the
ordered questions) → Information requested → Tool sequence → What "good" looks like → Pitfalls.**

---

### 4.1 ⭐ Create a new bus route *(the flagship — the user's example, worked in full)*

**Trigger.** "A councillor / community group says neighbourhood X needs better transit," or a
diagnostic flagged a gap, or new development is coming.

**What they're really asking.** *Is there enough unmet, connectable demand to justify a line —
and if so, what's the best corridor + stops, who does it serve, and what does it cost?*

**How a planner reasons (the ordered questions):**
1. **Who is here, and are they the kind of people who'll ride / need it?** Density, income,
   age, car-ownership/transit-dependence along the corridor. *(A route through empty or
   car-rich, affluent low-density land is a hard sell — unless the goal is explicitly equity
   coverage.)*
2. **Where would they go?** The anchors — downtown, job centres, hospitals, schools,
   colleges, malls, and especially **existing rapid-transit stations** to transfer into.
3. **Is there actually a gap?** What's current walk access and what routes already exist? Don't
   build where service already runs (H6).
4. **Where do trips from here actually want to go?** The origin→destination pattern — a route
   is a *line between a strong origin cluster and a strong destination cluster.*
5. **What's the feasible corridor?** Which arterials can physically carry a bus and connect the
   anchors with reasonable **directness** (H5)? Avoid residential-only streets, dead-ends,
   barriers.
6. **Where do the stops go?** ~300–400 m spacing (H4), at intersections, adjacent to the
   anchors and to walkable, sidewalk-served blocks.
7. **What does it accomplish, and who benefits/loses?** New population + jobs brought within
   the walkshed, equity-weighted; duplication created; anyone worse off.
8. **Is it buildable & affordable?** Route-km (→ operating cost), turn feasibility, depots,
   barriers.
9. **Make the case.** A council-ready brief with the equity story and the numbers.

**Information requested (in order):** demographics+income (1) → destinations/anchors (2) →
current access + existing service (3) → O-D demand (4) → street network/feasibility (5) →
simulated coverage/impact (7) → distributional effects (7) → cost/constraints (8).

**Tool sequence:**
```
Understand   profile_area(corridor)               # who & income
             get_city_grid(bbox, all channels)    # resident tensor for everything below
             list_transit(bbox)                   # what already runs (avoid duplication)
Diagnose     estimate_demand(bbox)                # where latent demand & O-D concentrate
             compute_accessibility(bbox)          # current gap
             reachability(key origins)            # can they reach jobs today?
Frame        parse_goal("connect X to downtown/jobs, prioritize low-income")  # → reward spec
Generate     optimize_layout(reward_spec, region) # propose corridor + stops (RL)
             # or simulate_change([...]) for a hand-drawn corridor
Evaluate     simulate_change(proposed stops)      # before/after coverage, jobs, equity
             constraint_check(layout)             # streets/barriers/spacing feasible?
             who_is_affected(scenario, by=income) # winners & losers
             diff_scenarios(baseline, proposed)
Justify      explain_result(scenario)             # narrate the trade-off
             generate_brief(scenario)             # council memo
```

**What "good" looks like.** A reasonably **direct** corridor connecting a dense/transit-
dependent origin cluster to real destinations and a **transfer point**, with ~400 m-spaced
stops, a clear **+N residents / +M jobs within walkshed** (equity-weighted), an honest note on
duplication/cost, and an explicit **who-gains / who's-unaffected** table.

**Pitfalls the agent must avoid.** Proposing a route with no destination anchor; a winding
"coverage" route that serves everyone slowly and no one well; stops mid-highway / across a
river barrier (H7); duplicating an existing frequent route; claiming ridership numbers (H9);
recommending without `who_is_affected`.

---

### 4.2 Add / relocate stops on an existing route

**Trigger.** "This route has a coverage hole / stops are too far apart / a new building opened."
**Really asking.** *Given the line is fixed, where do stops maximize equity-weighted access
without slowing the route unacceptably?*
**Planner reasoning:** Where along the line are people beyond the 400 m walkshed? Which gaps sit
next to dense or transit-dependent blocks or new destinations? Does adding a stop here slow
everyone too much (H4 trade-off)? Are there sidewalks/crossings to actually reach it?
**Info requested:** population/income along the line → current per-segment access → destinations
near candidate cells → walk-network/sidewalk feasibility.
**Tools:** `list_transit(route)` → `compute_accessibility(corridor)` → `parse_goal` →
`optimize_layout(budget=k, constrain to route)` / `propose_candidates` →
`simulate_change(add/move stops)` → `constraint_check` (spacing, route proximity) →
`who_is_affected` → `explain_result`.
**Good looks like:** k stops that close the biggest equity-weighted gaps at the smallest
speed cost, each on a walkable block. **Pitfalls:** clustering stops on one hotspot (gaming
coverage); ignoring the dwell-time/speed cost; a stop with no sidewalk to it.

---

### 4.3 Find & explain transit deserts *(pure diagnostic — no optimization)*

**Trigger.** "Where are our worst-served areas?" (council, news, planning review).
**Really asking.** *Which areas have low access AND high need, ranked, with the reason?*
**Planner reasoning:** Access alone isn't a desert — low access in a car-rich exurb matters less
than low access in a dense low-income tower cluster (H3). Cross access with need.
**Info requested:** access surface citywide → marginalization/income → population → existing
service (to confirm it's truly a gap).
**Tools:** `get_city_grid` → `compute_accessibility(citywide)` → `equity_gap_report()` →
`compare_areas(worst, by access+need)` → `explain_result`.
**Good looks like:** a ranked list of high-need + low-access areas with the *non-obvious* ones
surfaced (H9: "obvious vs valuable"). **Pitfalls:** reporting raw access without the need
overlay; flagging low-density rural cells as "deserts."

---

### 4.4 Improve access for a target group (low-income / seniors / a ward)

**Trigger.** "Improve transit for seniors in Scarborough" / "for low-income riders without
hurting downtown commute times."
**Really asking.** *Optimize access weighted toward this group, within a protect-constraint.*
**Planner reasoning:** Who/where is the group? What destinations matter *to them* (seniors →
clinics, pharmacies, community centres; low-income → jobs, schools)? What's their access now?
Then optimize with a heavy equity weight and a guardrail on what must not get worse.
**Info requested:** group geography (age/income/equity layers) → group-relevant destinations →
group's current access/reachability → the protected metric's baseline.
**Tools:** `profile_area(group)` → `equity_gap_report(region)` → `reachability(group origins →
group destinations)` → `parse_goal(goal+protect clause)` → `optimize_layout` →
`who_is_affected(by=age/income)` → `diff_scenarios` → `generate_brief`.
**Good looks like:** measurable access gain *for the named group*, the protected metric held,
losers named. **Pitfalls:** optimizing generic access that helps the average but not the group;
silently violating the "without hurting X" clause.

---

### 4.5 Plan service for new development / future growth

**Trigger.** "10k units are coming to the Port Lands / this corridor is intensifying."
**Really asking.** *Where will demand be in 5–10 years, and what service gets ahead of it?*
**Planner reasoning:** Today's density is the wrong input — use the pipeline. Where are units +
jobs landing? Will existing service absorb it? Plan the corridor to the *future* demand surface,
ideally tied to planned transit-oriented nodes.
**Info requested:** development pipeline + intensification-to-2051 → planned TOC / station areas
→ current service → future O-D estimate.
**Tools:** `estimate_demand(horizon=2031/2051)` → `list_transit` (current capacity) →
`compute_accessibility(future grid)` → `parse_goal` → `optimize_layout` →
`simulate_change` → `generate_brief`.
**Good looks like:** service sized to projected, not current, demand, anchored to planned nodes.
**Pitfalls:** planning to today's population; ignoring planned rapid-transit that changes the
network.

---

### 4.6 Fix an unreliable / slow corridor (service quality)

**Trigger.** "Route 36 is always late" / complaint clusters.
**Really asking.** *Where and when is reliability worst, who's affected, and is it a stop/spacing
issue or an operations issue I can't fix by moving stops?*
**Planner reasoning:** Diagnose *where* and *when* delays concentrate; check if it correlates
with stop density (too many stops → slow) or external (traffic). Reliability may be an ops
problem (signal priority, frequency) outside stop-placement — say so (scope honesty).
**Info requested:** delay data by segment/time → ridership exposed to it → stop spacing on the
segment → who rides it (equity).
**Tools:** `reliability_report(route/area)` → `profile_area(affected riders)` →
`compute_accessibility` (if stop-spacing implicated) → `who_is_affected` → `explain_result`.
**Good looks like:** pinpointed worst segments/times, riders affected, and an honest split
between "stop-placement can help" vs "this is an operations fix." **Pitfalls:** proposing stop
moves for a problem that's actually frequency/traffic; ignoring time-of-day.

---

### 4.7 Connect a neighbourhood to jobs (economic access)

**Trigger.** "People in Jane-Finch can't reach jobs." (Economic Systems track.)
**Really asking.** *How many jobs are reachable within a realistic time budget now, and what
intervention raises that most?*
**Planner reasoning:** The metric is **jobs reachable in ~45 min by transit**, not raw coverage.
Find where reachability is low despite job demand; the fix may be a new connection to a rapid
line (transfer), not local stops.
**Info requested:** job locations (employment survey) → current reachability isochrones →
O-D/commute flows → network/transfer options.
**Tools:** `reachability(origins, 45min)` → `estimate_demand` (jobs side) → `parse_goal(maximize
reachable jobs)` → `optimize_layout` / `simulate_change(add connector)` → `who_is_affected` →
`generate_brief`.
**Good looks like:** a measurable jump in reachable jobs for the target origins, often via a
network connection. **Pitfalls:** optimizing coverage instead of *reachability*; ignoring
transfers/rapid transit.

---

### 4.8 Budget-constrained improvement ("we have $X / N new stops — where?")

**Trigger.** "We can fund 8 new stops this year. Best placement?"
**Really asking.** *Maximize equity-weighted access gain subject to a hard budget.*
**Planner reasoning:** This is the optimizer's home turf — a fixed budget, an objective, feasibility
constraints. Rank candidate placements by marginal access-per-dollar with the equity weight.
**Info requested:** access gaps citywide → need overlay → feasibility of candidate cells → cost
per stop.
**Tools:** `parse_goal(budget=8)` → `optimize_layout(budget=8)` → `propose_candidates` →
`simulate_change` → `constraint_check` → `who_is_affected` → `diff_scenarios` → `generate_brief`.
**Good looks like:** the N placements with the highest equity-weighted marginal gain, each
feasible, with the runner-ups shown. **Pitfalls:** exceeding budget; ignoring marginal
(diminishing) returns of clustered stops.

---

### 4.9 Evaluate a proposal / compare scenarios ("a councillor suggests moving stop Y")

**Trigger.** "Here's a proposed change — is it good?"
**Really asking.** *What does this specific change do vs today, and who wins/loses?*
**Planner reasoning:** Don't optimize — *measure the given option*. Run it through the sim, diff
against baseline, surface distributional effects, check feasibility. Be neutral and factual.
**Info requested:** the proposed operations → baseline metrics → distributional breakdown →
feasibility.
**Tools:** `simulate_change(proposal)` → `diff_scenarios(baseline, proposal)` →
`who_is_affected` → `constraint_check` → `explain_result`.
**Good looks like:** an even-handed before/after with winners, losers, and feasibility flags —
even if the verdict is "this helps Y but costs Z access." **Pitfalls:** advocacy instead of
assessment; hiding the losers.

---

### 4.10 Equity audit / "who gets left behind" report for council

**Trigger.** "Give us a transit-equity snapshot of the city/ward."
**Really asking.** *Where is the access-vs-need mismatch worst, citywide, in reportable units?*
**Planner reasoning:** This is diagnosis at scale, aggregated to wards/neighbourhoods, with the
distributional story front and centre — the project's headline ("who gets left behind" as a
visible output, not an assumption).
**Info requested:** citywide access + need + population, aggregated to boundaries.
**Tools:** `get_city_grid` → `equity_gap_report(citywide)` → `compare_areas(by ward)` →
`who_is_affected(by income/age)` → `generate_brief`.
**Good looks like:** a ranked, reportable equity map with the worst mismatches named and
quantified. **Pitfalls:** dumping raw access maps without the need cross; no aggregation unit.

---

## 5. Agent operating principles (how the model should behave)

These turn the mental models into reliable behavior — put them in the system prompt.

1. **Diagnose before you optimize; attribute before you recommend.** Follow the loop (§1); never
   jump to `optimize_layout` without `equity_gap_report`/`compute_accessibility` first, and
   never present a recommendation without `who_is_affected`.
2. **Ground every claim in a tool result.** No invented numbers. If you state an access %, a
   `compute_accessibility`/`reachability` call produced it. (H9.)
3. **Name the trade-off.** Every goal sits on the ridership⇄coverage spectrum (H1); state which
   way you weighted it and what it costs.
4. **Always surface losers.** Reallocation has losers (H8); a recommendation without them is
   incomplete.
5. **Respect physics.** 400 m walksheds, ~300–400 m spacing, directness, barriers, transfers
   (H4–H7). Don't place stops in infeasible spots — `constraint_check` before recommending.
6. **Hold the honesty boundary.** Accessibility/equity model, *not* a ridership/demand forecast
   (H9). Say so when asked to predict.
7. **Pick the right loop depth.** Pure questions ("where are deserts?") stop at Diagnose — don't
   force an optimization. Proposals get Evaluate, not Generate.
8. **Latency policy (from on-box testing):** run tool-selection and `parse_goal` with
   **thinking OFF** (`/no_think`, ~0.8–1 s/turn); run `explain_result`/`generate_brief` with
   **thinking ON** (reasoning adds value there). See `backend-hosting-plan.md`.

---

## 6. How these become the agent

Each workflow above is a **planning template** the agent can pattern-match a user request to,
then execute the tool sequence — i.e., they double as **few-shot examples in the system
prompt** and as **integration-test scripts** (each expected tool sequence is a test the agent
loop should reproduce). Start by wiring the three highest-value, fully-local workflows —
**4.3 (transit deserts)**, **4.4 (target-group access)**, and **4.1 (new route)** — since their
data (GTFS, census, equity layers, network) is already on disk per
[`data-layer.md`](data-layer.md), and they showcase the diagnose→optimize→explain arc end to end.
