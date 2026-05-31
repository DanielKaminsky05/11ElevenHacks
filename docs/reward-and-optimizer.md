# Reward Function & Stop-Placement Optimizer — Design Spec

**Status:** design, not yet implemented. This is a brief for whoever builds the
optimizer. It supersedes the placeholder `_reward` / `_greedy_place` in
`backend/app/tools/optimization.py`.

**Related:** [Project Idea](project-idea.md) · [Map Data Layer Catalog](data-layer.md) · [Agent Tools](agent-tools.md)

---

## TL;DR

1. **Use greedy + local search, not RL.** Stop placement is a facility-location
   problem; coverage is monotone submodular, so greedy is provably within
   **(1 − 1/e) ≈ 63%** of optimal (Nemhauser 1978). RL gives no quality guarantee,
   needs flaky training, and must retrain on every weight change. Greedy is
   deterministic, millisecond-fast, and re-solves instantly when the planner
   changes weights — which unlocks the *interactive* demo.
2. **The reward function is the entire product.** Greedy and RL (and cuOpt) are
   just consumers of it. Invest here.
3. **The current `_reward` ignores all real data.** It scores pure geometry and
   fakes equity as "the southern half of the grid is poor"
   (`equity_cells = [c for c in cells if c[0] >= _GRID_ROWS // 2]`). The grid
   *already carries* real population / income / `pct_low_income` / existing stops
   (see `get_city_grid` in `app/tools/city_state.py`). The core work is grounding
   the reward in that data.

---

## Why greedy, not RL

This is a **Maximal Covering Location Problem** / p-median: place `k` stops to
maximize served demand.

- **Coverage is submodular & monotone** — each new stop helps less once nearby
  demand is served (diminishing returns). For a monotone submodular objective
  under a cardinality budget, **greedy ≥ (1 − 1/e)·OPT**. A real guarantee we can
  state to judges; RL has none.
- **Deterministic & fast** → same goal yields same answer (trust), and a re-solve
  is <50 ms (interactivity).
- **The more realistic the reward, the stronger greedy's guarantee**, because real
  access *saturates* — which *is* submodularity. Better reward and better algorithm
  are the same investment.

### The demo this enables (better than a training curve)

- **Per-step animation:** greedy places one stop at a time → stream each placement
  as a frame → the map shows the network *being built*, each stop landing where it
  does the most good.
- **Interactive re-solve (the money shot):** planner drags the equity weight up →
  optimizer re-solves in <50 ms → stops migrate toward marginalized neighbourhoods
  and the equity-gap heatmap closes, *live*. RL cannot do this without retraining.

---

## The reward function

### Per-cell demand model (the foundation)

For each grid cell `i`, attach from the data the grid already rasterizes:

| Quantity | Source channel (`get_city_grid`) | Meaning |
|---|---|---|
| `pop_i`     | `population`                       | how many people live there |
| `need_i`    | `pct_low_income` (+ ON-Marg / NIA) | how underserved/vulnerable, in [0,1] |
| `access0_i` | `stops` (existing network)         | how well-served **already** |
| `dest_i`    | `destinations`                     | jobs/amenities they travel to |

The unit of value is **person-weighted access delivered to people who need it** —
not "cells covered."

### Credit only *new* access (the crux)

Use a **distance-decay (gravity) access** rather than a hard cutoff — access fades
with walk distance, it doesn't cliff at 400 m:

```
access_i(S) = max over s in S of  exp( -dist(i, s) / d0 )     # d0 ≈ 400 m walk scale
gained_i(S) = max(0,  access_i(S) − access0_i)                # only NEW access counts
```

`gained_i` is what forces the optimizer to **close gaps** instead of piling stops
where service already exists. This operationalizes the headline `equity_gap_report`
view directly.

> **Units:** `d0` and any threshold must be in real metres mapped through the grid
> spacing — not "2 grid units." Convert via `_cell_to_lonlat` / a metres-per-cell
> constant.

### The four channels (normalized to [0,1])

```
coverage   = Σ_i  pop_i · gained_i                 / Σ_i pop_i
equity     = Σ_i  need_i · pop_i · gained_i         / Σ_i need_i · pop_i
travel     = 1 − normalize( Σ_i pop_i · dist_i(S) )       # person-weighted walk burden
constraint = 1 − spacing_penalty(S) − protect_penalty(S)  # too-close pairs; "don't worsen" areas
```

- **coverage** — share of *population* given new access.
- **equity** — same, weighted by need: "what share of *high-need* people got new
  access." The differentiator: coverage delivered to marginalized, currently-
  underserved residents, quantified from real census/ON-Marg data.
- **travel** — person-weighted proximity (breadth-vs-depth tradeoff vs. coverage).
- **constraint** — feasibility: spacing (no redundant clustering) + the `protect`
  field ("without hurting downtown commutes" → penalty if a protected area's access
  drops).

### Scalarization — make the number mean something

Combine with the planner's `RewardSpec` weights, but express each channel as
**"% of the achievable improvement captured"**:

```
score_k = ( value_k(S) − value_k(do_nothing) ) / ( value_k(ideal) − value_k(do_nothing) )
R(S)    = Σ_k w_k · score_k  /  Σ_k w_k
```

Now `R` is interpretable to a planner ("captures 78% of the coverage opportunity,
91% of the equity opportunity") and weights behave predictably — every channel is
on the same "fraction of what's possible" scale. `value_k(do_nothing)` and
`value_k(ideal)` are fixed per goal so scores stay comparable across layouts.

---

## Pitfalls to design against (these bite if ignored)

1. **Degenerate clustering** — pure equity weight dumps all stops on the single
   highest-need cell. The spacing constraint + saturation in `gained_i` (a covered
   cell stops paying out) prevent it. **Add a test.**
2. **Double-counting** — `access_i` must be `max` (or a saturating sum) over stops,
   never a plain sum, or cells near many stops get unbounded credit — and it breaks
   submodularity.
3. **Baseline drift** — `do_nothing` / `ideal` reference points fixed per goal, or
   cross-layout scores aren't comparable.
4. **Grid-scale units** — distances in real metres, not grid units.

---

## The optimizer

Upgrade `_greedy_place`:

1. **Warm-start** from the existing stop layout (`access0`), not an empty grid — we
   improve a real network, not build from scratch.
2. **Greedy-add** on marginal `ΔR` until `budget` is exhausted or `ΔR ≤ 0` (the
   current `best_cell is None` stop condition already handles non-improvement).
3. **Local-search swap pass** — try relocating each placed stop to a better
   neighbouring cell; accept improvements. Escapes greedy's local optima and
   handles *relocation*, not just addition.
4. **Stream every step** (`{stops, R, channel_scores}`) for the animation.

Deterministic, fast, near-optimal, demo-safe.

---

## The Spark / GPU path (no RL needed)

Two flagship RAPIDS components instead of hand-rolled PPO — a *stronger*
NVIDIA-ecosystem story:

- **cuSpatial / cuDF** — vectorize `access_i` over all cells × all candidate
  placements (the reward eval is the bottleneck; it's embarrassingly parallel).
  Marked `# TODO(spark)` in `get_city_grid` and the reward.
- **cuOpt** — solve the *exact* MCLP / p-median on the GB10 at full Toronto
  resolution, warm-started from the greedy solution, where the approximation gap
  starts to matter.

Hold the grid + candidate buffers + Nemotron context in the 128 GB unified memory.

---

## Concrete work items (file-scoped)

1. **`app/tools/city_state.py` — `get_city_grid`:** expose per-cell `pop_i`,
   `need_i` (from `pct_low_income`; ON-Marg/NIA later), `access0_i` (from existing
   `stops`). Pure pandas/geopandas now; `# TODO(spark)` GPU swap later.
2. **`app/tools/optimization.py` — `_reward`:** rewrite to the grounded,
   gained-access, person-weighted form above. **Delete the fake southern-half equity
   proxy.** Keep the `RewardSpec` weight fields as-is.
3. **`app/tools/optimization.py` — `_greedy_place`:** add warm-start + local-search
   swap pass; emit per-step states.
4. **`app/ws/training.py`:** replace the echo stub with a stream of per-step
   `{stops, R, channel_scores}` so the frontend animates the build and re-solves on
   weight change.
5. **Tests:** reward monotonicity on coverage-only goals; equity goal shifts stops
   toward high-`need` cells; no degenerate clustering; greedy ≥ a random baseline;
   determinism.

**Invariants:** the `RewardSpec` / `PlannerResponse` contracts and the camelCase
frontend weights stay unchanged. Reward stays a pure function of (layout, spec,
per-cell data) — no I/O inside `_reward`. All terms remain in [0,1].
