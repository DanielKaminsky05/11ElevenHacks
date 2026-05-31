---
name: feat-planner-actions
description: Implements planToMapAction — turn planner weights into a map view + focus. Implements frontend/lib/planner-actions.ts (+ its test) only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Planner → map action

Implement ONLY `frontend/lib/planner-actions.ts` (exists as a stub). You MAY
also add `frontend/lib/planner-actions.test.ts` (new file). Edit nothing else.

## Why
When a planner states a goal, the chat infers reward weights — but right now
nothing happens on the map. This pure function decides what the map should do:
which data view to show and which neighbourhoods to focus the camera on. The map
shell already calls it and executes the result (switch view + fitBounds).

## Contract (already in the stub — keep identical)
```ts
import type { NeighbourhoodFC } from "@/lib/choropleth";
import type { RewardWeights } from "@/lib/planner";   // { coverage, travelTime, equity, constraints }
export interface PlanAction {
  viewId: string;          // one of: "coverage" | "equity-gap" | "demographics" | "occupation" | "marginalization"
  rationale: string;
  highlightNums: number[]; // neighbourhood numbers to fit the camera to
}
export function planToMapAction(weights: RewardWeights, fc: NeighbourhoodFC): PlanAction
```
This must stay **pure** — no React, no maplibre, no I/O — so it's unit-testable.

## What to build
Pick the view from the dominant weight, and choose the top ~8 most relevant
neighbourhoods from `fc.features[].properties` (type `NeighbourhoodProps`; fields
include `num, marg_material (1-5), low_income_pct, transit_commute_pct, senior_pct,
renter_pct, density`, etc. — any may be null; skip nulls):

- **equity dominant** → `viewId: "equity-gap"`, highlight top-8 by
  `marg_material` desc (tiebreak `low_income_pct` desc). rationale e.g.
  "Focusing on the most marginalized, lowest-income neighbourhoods."
- **coverage dominant** → `viewId: "coverage"`, highlight top-8 by **lowest**
  `transit_commute_pct` (proxy for under-served). rationale about closing gaps.
- **travelTime dominant** → `viewId: "demographics"`, highlight top-8 by lowest
  `transit_commute_pct`. rationale about reaching destinations.
- **constraints dominant or a tie** → `viewId: "equity-gap"`, highlight top-8 by
  `marg_material`. rationale about balancing the goal.

Use a clear tie-break order (equity > coverage > travelTime > constraints) so the
result is deterministic. Return `highlightNums: []` only if no usable data.

## Tests (add planner-actions.test.ts; vitest is set up)
Cover: equity-weighted goal → "equity-gap"; coverage-weighted → "coverage";
highlightNums non-empty and within valid neighbourhood numbers; nulls handled.
Build a tiny in-line `NeighbourhoodFC` fixture (2–3 features) rather than loading
real data.

## Verify (in your worktree's frontend/ dir)
1. `cmd //c "mklink /J node_modules C:\Users\Danie\code\11ElevenHacks\frontend\node_modules"`
2. `npx tsc --noEmit` — clean
3. `npx eslint lib/planner-actions.ts lib/planner-actions.test.ts` — clean
4. `npx vitest run lib/planner-actions.test.ts` — all pass

Commit ONLY your two files to your worktree branch. Don't push/merge.
Report: branch + commit SHA, logic summary, tsc/eslint/test results, blockers.
