# TransitRL — The Pitch

How to present TransitRL to win the Spark Hack Series (NVIDIA Toronto). Tuned to the
[judging rubric](hackathon-details.md) and grounded in real planner practice
([real-world-transit-practice.md](real-world-transit-practice.md)).

> **Status check:** every tool family in the vision is actually implemented — `city_state`,
> `diagnostics`, `simulation`, `optimization`, `explanation`, plus an `events` family and five
> map views. Pitch the **working copilot**, not the roadmap.

---

## Track

**Primary: Public Services** — "improve how people *access* city services, make them more
accessible and efficient." The headline (who gets left behind by transit, equity-weighted) is a
public-service-access argument.

Secondary lens: **Urban Operations** (stop placement, event surges). Don't claim Economic
Systems — weakest fit, dilutes the story. Name one track with conviction.

---

## The hook (elevator pitch — 30–40s)

> **A transit equity study in Toronto takes a planning team months and a GIS consultant. We
> compressed it into a sentence and a few seconds — running entirely on the box in front of you.**
>
> TransitRL is a planning copilot for Toronto transit. You ask in plain English — *"where are our
> transit deserts for low-income seniors?"*, *"add three stops in Scarborough without hurting
> downtown access — who benefits?"* — and a local Nemotron model orchestrates a toolbox of real
> analyses over Toronto's open data: it **diagnoses** gaps, **simulates** your what-if, runs an RL
> optimizer to **search** for a better layout, and hands back a map plus a council-ready memo that
> names exactly **who gains and who loses**. No data leaves the device.

**One-liner for the form:** *"Ask Toronto's transit network a question in plain English; a local
AI agent diagnoses inequity, simulates fixes, and optimizes stop placement — turning a months-long
equity study into a seconds-long, legible loop on the DGX Spark."*

The two things that make a judge lean in: the **compression claim** (months → seconds) and
**"who gets left behind" as a computed output, not an assumption.** Lead with both.

---

## Covering all four scoring criteria (100 pts)

Speak to each one explicitly — judges score with the rubric open.

### ① Technical Execution & Completeness (30) — strongest; demo it live end-to-end
- **Completeness (15):** one unbroken loop — English question → agent picks tools → map renders →
  memo exports. Don't list 20 tools; run 3–4 that visibly work. Message: "this is a *system*, not
  a slide deck" (quote the rubric back).
- **Depth (15):** name the real engineering — a custom **Gymnasium RL environment + CNN policy**, a
  walk-access **simulation engine** the optimizer calls thousands of times, and an **agentic MCP
  tool layer** Nemotron orchestrates. The rubric names "simulation" and "custom logic"; you have
  both plus orchestration.

### ② NVIDIA Ecosystem & Spark Utility (30) — make 2 pieces clearly load-bearing
- **The Stack (15):** **Nemotron served locally via NIM** is the anchor (also wins the bounty). Add
  one more genuinely load-bearing GPU piece — cuSpatial in the accessibility/reward hot loop, or
  GPU-resident parallel sim environments — and have a **measured number** ("N envs at X steps/sec,"
  or "accessibility kernel: Z ms on GPU vs W s on CPU"). A number here is worth real points and
  almost nobody has one.
- **The Spark Story (15):** one *true* reason it needs the Spark, with a figure: *"On 128 GB unified
  memory the rasterized city grid, the RL replay buffer, and the Nemotron context all sit resident
  at once — what-ifs return sub-second and the whole agent reasons locally, so a planner's queries
  about residents' incomes never leave the device."* Lean hard on **privacy/locality** (census +
  equity data on-device) — it's the most defensible angle.

### ③ Value & Impact (20) — the planner research wins this (see next section)
- **Insight (10):** `equity_gap_report` and `who_is_affected` produce inequity *computed, not
  assumed*.
- **Usability (10):** "a planner asks in English, gets a map + an exportable memo" is a textbook
  "use it tomorrow" story. Lead with the equity insight; pitch the optimizer as *exploratory*.

### ④ Innovation & Execution (20)
- **Creativity (10):** "City-as-multi-channel-image → CNN," "English goal → reward weights," "RL on
  both sides of the interface" (your agent learns by RL; Nemotron was post-trained with RL).
- **Performance (10):** reuse the measured number from criterion 2 — one real "we optimized X to
  run at Y."

### ⭐ Nemotron bounty
Hit it head-on: Nemotron plays **three** roles — orchestrates tool calls, translates English goals
→ structured reward JSON, narrates trade-offs — served locally through **NIM**, not an API. Say
"merely calling a cloud LLM scores zero here — ours runs on the Spark."

---

## Why a real city planner would actually use this (the research)

This converts "cool demo" into **Usability (10)** and **Insight (10)** points — and survives a
transit-literate judge. TransitRL mirrors how planning is *legally and operationally* done:

- **Equity analysis is mandatory, not a nicety.** US **FTA Title VI** requires a *Service Equity
  Analysis* for any major service change (±25% of a route's revenue hours, or moving a stop
  >¼ mile), testing **disparate impact** (harm to a racial group) and **disproportionate burden**
  (harm to low-income riders). **`who_is_affected(by=income)` and `equity_gap_report` are the literal
  computational form of those two tests.** TTC goes further — boardings near its **31 Neighbourhood
  Improvement Areas weighted at 125%**; your equity reward weight is the same idea.

- **The core trade-off it encodes is *the* industry trade-off.** Every network is a budget-constrained
  choice between **ridership** (frequency on dense corridors) and **coverage** (everyone near a
  stop). Agencies adopt an explicit split like "60% ridership / 40% coverage" — **exactly what
  `parse_goal`'s reward weighting picks.** You turned the foundational values-question into a
  tunable input.

- **It speaks the standards planners already use.** TTC: **90% of population within 400 m** of
  service; **300–400 m** local stop spacing; a **net-benefit test** weighting wait ×1.3, walk ×1.8,
  transfers ×6.0. Your accessibility tool + constraint checks compute against these. Quote the 400 m
  walkshed — it signals you did the homework.

- **It collapses a genuinely slow process.** A network redesign is a ~3-year, consultant-led study;
  the annual service plan is monitor → review → equity-assess → board approval → 12-month trial. You
  replace the slow **"ask better questions in the first week"** phase that today needs GIS staff —
  not the engineering study.

- **It's timely to the day.** Toronto hosts **6 FIFA World Cup matches at BMO Field in June 2026**
  with a transit-first plan (70% transit mode-share target; egress surge of ~70% of fans leaving
  within an hour). Your `events` tools answer *"what breaks when 45k people leave BMO Field at once,
  and which low-income areas lose service during the closures?"* — a question the city is answering
  **right now**. Strong second demo query if time allows.

**Honesty boundary is a feature — say it out loud:** "an accessibility-and-equity model, not a
ridership forecast — and we state that inside every exported memo." Transit-literate judges test for
over-claiming; pre-empting it earns trust and points.

---

## Demo video script (maps to the required 5-part structure)

1. **Team (20–30s).** Names + roles.
2. **Hook (30–40s).** The pitch above — months→seconds, equity-as-output, runs locally.
3. **Live core loop (45–60s).** Type *"Where are the worst transit gaps for low-income residents,
   and add a few stops to fix the biggest one — who benefits?"* → Nemotron picks tools → equity-gap
   map → optimizer animating stops → exported memo naming winners/losers. One unbroken take.
4. **How you built it (60–90s).** Nemotron-via-NIM orchestrating an MCP toolbox → simulation engine
   → RL optimizer → MapLibre/deck.gl frontend. Name the **Spark story + your one perf number**, and
   one tradeoff (e.g. corridor-constrained actions over free-floating stops for realism).
5. **So what (20–30s).** "Title VI equity analysis, in plain English, in seconds, on-device — a
   Toronto planner could use this for the World Cup next month." Close on usability + privacy.
