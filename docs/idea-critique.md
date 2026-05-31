# TransitRL — Critique Against the Judging Criteria

A hard look at where **TransitRL** is weak relative to how this hackathon is actually scored.
The point is not to praise the idea (it has real strengths) but to find where a sharp judge
docks points — while there's still time to fix it.

**Scope of this review:** assessed against all three design docs —
[`project-idea.md`](project-idea.md) (the RL core), [`data-layer.md`](data-layer.md) (the
datasets), and [`agent-tools.md`](agent-tools.md) (the MCP/copilot reframe) — plus the local
[`data/`](../data/) inventory.

**The rubric we're graded on** (from [`hackathon-details.md`](hackathon-details.md)):

| # | Criterion | Pts | Sub-breakdown |
|---|---|---|---|
| 1 | Technical Execution & Completeness | 30 | 15 completeness · 15 technical depth |
| 2 | NVIDIA Ecosystem & Spark Utility | 30 | 15 "the stack" · 15 "the Spark story" |
| 3 | Value & Impact | 20 | 10 insight quality · 10 usability |
| 4 | Innovation & Execution | 20 | 10 creativity · 10 performance |

Plus the **Nemotron bounty**.

---

## TL;DR — the risk has moved from *design* to *execution*

> **On paper, the current design (copilot + MCP + Nemotron/NIM + RAPIDS + cuOpt + the 128 GB
> story) is strong and already hits the things most teams miss — agentic architecture and a
> real NVIDIA stack. That is exactly why the danger has flipped: the way TransitRL loses now
> is not a weak idea, it's an *over-scoped* one that demos broken, plus NVIDIA integrations
> that are convincing on a slide but thin under a judge's questions.**

The `agent-tools.md` reframe (RL is now *one tool among many* in a planning copilot) genuinely
fixes the two biggest holes a narrower version would have had: it makes the system **agentic**
(what the rubric and the Economic-Systems track explicitly want) and it gives every NVIDIA
library a home. Credit where due. But it also **roughly tripled the build surface** for a
weekend, and that is the new central threat.

Illustrative scoring — note the gap between *ceiling* (if it runs) and *floor* (if scope wins):

| Criterion | Floor (over-scoped, shaky demo) | Ceiling (tight vertical slice that runs) | The swing factor |
|---|---|---|---|
| 1. Technical Execution & Completeness | ~10 / 30 | ~25 / 30 | **Does the end-to-end loop actually run on stage?** |
| 2. NVIDIA Ecosystem & Spark Utility | ~12 / 30 | ~26 / 30 | Are the NVIDIA pieces load-bearing or decorative? Is the Spark story *true*? |
| 3. Value & Impact | ~11 / 20 | ~15 / 20 | Coarse-grid realism on the optimizer. |
| 4. Innovation & Execution | ~11 / 20 | ~16 / 20 | A real performance number, not just an architecture. |
| **Total** | **~44** | **~82** | **Scope discipline.** |

Everything below is in priority order. **The whole game is now Criterion 1a (completeness).**

---

## Criterion 1 — Technical Execution & Completeness (30 pts) — *now the dominant risk*

### 1a. Completeness (15 pts) — *the #1 thing that loses you the hackathon*
"Does the system complete the full workflow without crashing?" The design now spans, for a
**~48-hour** weekend:

- an **MCP server with ~20 tools** across five families,
- a **RAPIDS** cuDF/cuSpatial geospatial pipeline,
- a **cuOpt** routing/optimization integration,
- **Nemotron served via NIM** doing live tool-orchestration,
- a **custom Gymnasium RL** environment + CNN policy that must *visibly converge*,
- a **live-animating React/MapLibre/deck.gl** frontend over WebSockets.

Any *one* of these is a hackathon project. Stacked, the realistic outcome is **many
half-built tools and nothing that runs end-to-end** — which the rubric punishes hard ("not
just a slide deck"). Specific landmines:

- **DGX Spark is Grace-Blackwell aarch64.** RAPIDS, cuOpt, and NIM containers all have
  CUDA/driver/arch version constraints; getting the *whole* stack co-installed and talking on
  unfamiliar ARM hardware can eat a full day. **Test the full toolchain on the box in the
  first two hours**, and keep CPU fallbacks (geopandas/shapely, OR-Tools) so a missing wheel
  doesn't zero out a demo.
- **RL convergence is the least controllable piece.** PPO/DQN on a custom multi-term reward
  often won't converge cleanly in hours. If "watch it learn live" shows noise, your headline
  moment dies. **Pre-train checkpoints; make the live demo a fine-tune/replay; record a
  fallback video.**
- **20 tools reads as a spec, not a system.** Judges reward 3–4 tools that *demonstrably
  work* over 20 stubs. Pick the vertical slice (see "What to cut").

### 1b. Technical Depth (15 pts) — *a genuine strength*
Sim + RL + an agentic MCP tool layer + GPU data pipeline is well above "a static dashboard or
basic API wrapper" — the rubric literally names *Simulation* and *Custom Logic* as what earns
this, and you have both plus orchestration. Depth is not your problem; *finishing* is.

---

## Criterion 2 — NVIDIA Ecosystem & Spark Utility (30 pts) — *strong on paper, fragile under questioning*

The earlier "no NVIDIA library" problem is solved on paper. The new risk is **checkbox
integration**: lots of NVIDIA logos, each used thinly, with a Spark story that isn't literally
true. Where a judge will push:

- **cuSpatial may be decorative.** Rasterization / point-in-polygon over Toronto's geometries
  is a *one-time preprocessing* step that CPU geopandas does in seconds — the dataset isn't
  big. If cuSpatial only runs once at startup, it's not load-bearing. **Make it matter by
  putting it in the hot loop**: the accessibility/reward kernel that the RL calls thousands of
  times per episode. That's a defensible "we need the GPU" claim.
- **cuOpt is hand-wavy — and may make the RL redundant.** "cuOpt warm-starts the RL search" is
  vague; cuOpt solves routing/VRP, and it's not obvious how it seeds stop-*placement*. Worse:
  if cuOpt actually solves the placement well, **a judge will ask why you need RL at all.** Pick
  a lane: either (a) cuOpt is the optimizer and RL is dropped/demoted, or (b) RL is the
  optimizer and cuOpt powers `reachability` travel-time surfaces (a cleaner, real fit). Don't
  claim both do placement.
- **The 128 GB unified-memory story isn't literally true at current scale.** A 20×20–30×30
  grid + small CNN + replay buffer + one quantized Nemotron fits in a fraction of 128 GB.
  Claiming you "need" 128 GB invites an easy puncture. **Make the story true** by choosing the
  real reason: *running a large Nemotron locally for low-latency agentic loops* and/or
  *thousands of GPU-resident parallel sim environments*. State the one that's actually
  happening, with a number.
- **Nemotron-via-NIM is the strongest, cleanest win** — it earns stack points, the Spark
  story (local inference), *and* the bounty in one move. Protect this; it's your highest-ROI
  NVIDIA integration. (Watch the practical risk: NIM container + a Nemotron checkpoint on
  aarch64 — validate it serves on day 1.)

**Net:** the ceiling here is high (~26/30) but only if ≥2 NVIDIA pieces are genuinely
load-bearing and you can articulate one *true* Spark story. Thin usage caps you around 15–18.

---

## Criterion 3 — Value & Impact (20 pts)

### 3a. Insight Quality (10 pts) — *strong, and the copilot reframe helps*
`equity_gap_report` ("who gets left behind," computed not assumed) and `reliability_report`
are exactly the "non-obvious, valuable" insights the rubric wants, and the copilot means the
product has value **even if the optimizer is weak** — diagnosis/reachability/reliability don't
depend on stop-placement realism. Good architectural hedge.

But the optimizer — still your headline demo — has a concrete validity flaw:

- **Grid resolution makes the actions physically unrealistic.** Toronto is ~43 km × ~21 km. A
  20×20 grid → cells ≈ **2.1 km × 1.0 km**; 30×30 → ≈ **1.4 km × 0.7 km**. Real bus-stop
  spacing is **~250–400 m**, so "nudge a stop one cell" *moves it ~1 km* and the grid can't
  represent realistic spacing. A transit-literate judge sees this instantly.
- **Free-floating stops ignore that stops live on routes.** Moving a stop independent of its
  line is operationally meaningless; the route-proximity penalty acknowledges but doesn't
  resolve it.
- **Fix / hedge:** use the finer resolution the tools already parameterize (≈400 m cells →
  ~100×60 — which *also* feeds the real Spark compute story), and/or constrain
  `optimize_layout` to **add/remove/space stops along existing corridors**. And **wire SAM
  (now downloaded) as the reward benchmark** — a validated accessibility metric turns "is this
  real?" into evidence. Lead the demo with the *equity insight*, not literal stop coordinates.

### 3b. Usability (10 pts)
The copilot framing genuinely improves this — "a planner asks in English, gets a map + memo"
is a real "use it tomorrow" story, and `generate_brief` is a smart, concrete deliverable. Two
caps:
- **Agentic tool-routing with a local open model is unreliable.** Smaller local Nemotron
  variants are weaker at multi-step tool selection than frontier models; the doc's "the agent
  isn't scripted" is riskier to demo than a guided flow. **For the demo, constrain to 2–3
  rehearsed flows** (function-calling with a tight tool set), even if the architecture is
  general underneath.
- Usability is still capped by the optimizer realism above — pitch the optimizer as
  *exploratory*, lean on the diagnostic tools for the "decision-ready" claim.

---

## Criterion 4 — Innovation & Execution (20 pts)

### 4a. Creativity (10 pts) — *strong*
"City-as-multi-channel-image → CNN," English-goal → reward-weights, "RL on both sides," and a
planner copilot over an MCP toolbox are creative and demo-friendly. Keep it.

### 4b. Performance (10 pts) — *now has a path, needs a number*
The architecture *claims* GPU acceleration but the doc has no measured speed/scale result.
This sub-criterion wants "we optimized X to run at Y." **Produce one real number** — e.g.
"N parallel environments at X steps/sec via GPU-resident sim," or "cuSpatial accessibility
kernel: Z ms vs CPU's W s." Without a number you score low even with the right libraries.

---

## The scope tension (read this twice)

Every fix that raises Criterion 2/3/4 (finer grid, cuSpatial-in-the-loop, cuOpt, more tools,
agentic generality) **adds scope and threatens Criterion 1a**. You cannot build all of
`agent-tools.md` in a weekend, and trying to is the single most likely way to end up with
nothing that runs. **Treat `agent-tools.md` as the 6-month vision and ruthlessly pick a
vertical slice to actually build.**

### What to cut / what to build (highest points-per-hour)
1. **Build Phase 0 + Phase 1 only** (per `agent-tools.md` §7): `get_city_grid`,
   `compute_accessibility`, `equity_gap_report`, `simulate_change`, `parse_goal`,
   `optimize_layout`, `explain_result`, `who_is_affected`. That *is* the headline loop, and
   it runs on data already on disk. **Defer demand/reliability/reachability/brief** unless
   time remains.
2. **Make exactly two NVIDIA pieces load-bearing:** **Nemotron-via-NIM** (agent + bounty) and
   **cuSpatial in the accessibility/reward hot loop** (real Spark story + a perf number). Treat
   cuOpt as a stretch/`reachability` helper, not a core dependency.
3. **One true Spark story, with a number.** Write the sentence now; build toward it.
4. **De-risk the demo:** pre-trained RL checkpoints + replay; 2–3 rehearsed agent flows;
   recorded fallback; CPU fallbacks for every GPU lib.
5. **Resolution/action realism** on the optimizer — cheapest version that removes the "toy"
   objection.

If you do only one thing: **cut scope to the vertical slice and make it run end-to-end.**

---

## Demo-day risks (the "it works on stage" checklist)
- **Stack won't install on aarch64 Spark** → validate RAPIDS + NIM + cuOpt in hour 1; CPU fallbacks ready.
- **RL doesn't converge live** → pre-train + replay; never train from scratch on stage.
- **Local agent mis-routes tools** → rehearsed, constrained flows; tight tool schemas.
- **"Why do you need 128 GB / a Spark?"** → memorize the one true story with a number.
- **"Why RL when you have cuOpt?"** → decide the lane before the demo; have the answer.
- **Coarse-grid output looks silly to a transit person** → finer grid or corridor-constrained actions; lead with the equity insight.
- **Breadth reads as vapor** → show 3–4 tools *working* end-to-end, not 20 listed.

## What's already strong (don't lose it)
The copilot/MCP reframe (agentic + "usable tomorrow") · genuine technical depth (sim + RL +
orchestration + GPU pipeline) · Nemotron/NIM hitting stack + Spark + bounty at once · the
equity-as-output headline · `generate_brief` as a concrete deliverable · the up-front honesty
boundary · a data layer that's now almost fully downloaded. The idea is good. **Protect it by
building less of it, well.**
