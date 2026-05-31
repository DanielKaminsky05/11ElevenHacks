---
name: view-coverage
description: Builds the transit coverage & gaps map view (brainstorm #40). Implements frontend/components/transit-map/views/coverage.ts only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Transit coverage & gaps view

First read `.claude/agents/SHARED-BRIEF.md` — it has the data schema, helper API,
conventions, and verification steps. Follow its hard rules.

## Your file (edit only this)

`frontend/components/transit-map/views/coverage.ts`

## What to build

A view that shows transit **coverage** per neighbourhood and the **gaps**:

1. **Coverage choropleth** — color each neighbourhood by its coverage % (from
   `loadCoverage().byNum[num].cov`). Use `RAMP_COVERAGE` (red = gap → green =
   covered). Since coverage % lives in `coverage.json`, not the polygon
   properties, join it: after loading both, write `cov`/`gap` onto each feature's
   properties (mutate the loaded FC) before `ensureNeighbourhoodsSource`, OR set
   the source data to the enriched FC. Then `addChoroplethLayers` + recolor by
   `cov`. A fixed 0–100 scale is better than quantiles here — build a step
   expression with breaks `[20,40,60,80]` over `RAMP_COVERAGE` via
   `stepColorExpression("cov", [20,40,60,80], RAMP_COVERAGE)` and
   `map.setPaintProperty(fillId,"fill-color", expr)`.
2. **Uncovered grid points** — add a circle layer from `coverage.json`'s `grid`
   (build a GeoJSON FeatureCollection of points where `covered === 0`), small
   red dots, to make the gaps visceral. Own source id e.g. `coverage-gap-grid`.
3. **Popup** — on a neighbourhood: name, coverage %, and gap (people beyond
   400 m). Use `wireChoroplethPopup`.

Push all layer ids you create into `layerIds` (fill, outline, gap-grid).
Create everything hidden.

## Legend

`title: "Walk access to transit (400 m)"`, a `ramp` using `RAMP_COVERAGE` with
`lowLabel: "0% (gap)"`, `highLabel: "100%"`, and a `note` with the citywide
figure from `coverage.json` meta (e.g. `"95.4% covered · 162,322 beyond 400 m"`).

## Acceptance

- `npx tsc --noEmit` clean, `npx eslint` clean for your file.
- `layerIds` populated; layers created hidden; coverage joined correctly.
- No edits outside your file.
