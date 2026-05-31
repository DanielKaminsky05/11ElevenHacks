---
name: view-marginalization
description: Builds the ON-Marg marginalization quintile view with an NIA overlay (brainstorm #30-34). Implements frontend/components/transit-map/views/marginalization.ts only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Marginalization & equity designations view

First read `.claude/agents/SHARED-BRIEF.md`. Follow its hard rules.

## Your file (edit only this)

`frontend/components/transit-map/views/marginalization.ts`

## What to build

A **quintile** choropleth of the Ontario Marginalization Index with a dropdown
over its four dimensions, plus a **Neighbourhood Improvement Area (NIA)** outline
overlay.

Dimensions (fields are quintiles 1–5 in `neighbourhoods.json`):
- `marg_material` Material deprivation
- `marg_households` Households & dwellings (instability)
- `marg_age_labour` Age & labour force (dependency)
- `marg_racialized` Racialized & newcomer populations

Implementation:
1. `setup`: `loadNeighbourhoods()`, `ensureNeighbourhoodsSource`,
   `addChoroplethLayers` (hidden). Color by quintile using `RAMP_QUINTILE` — a
   **fixed** step expression over 1–5 (breaks `[2,3,4,5]`), NOT quantiles, since
   the values are already quintiles. Use `stepColorExpression(field,[2,3,4,5],
   RAMP_QUINTILE)`.
2. Add an **NIA outline layer** from the same source filtered to
   `["==", ["get","is_nia"], true]` — a bright dashed/solid line, no fill — so it
   reads as an overlay regardless of the active dimension. Own id e.g.
   `marg-nia-outline`. Include it in `layerIds` so it shows with this view.
3. `setOption`: re-color the fill by the chosen `marg_*` field (same fixed 1–5
   expression).
4. Popup: name, the active dimension's quintile (1–5, label "least → most"),
   and whether it is an NIA.
5. `legend()`: 5 `rows` (swatches) labelled "Q1 least … Q5 most marginalized"
   using `RAMP_QUINTILE`, plus a `line`-shape row for the NIA outline.

## Acceptance

- Dropdown switches dimension; NIA outline always visible with this view.
- `npx tsc --noEmit` + `npx eslint` clean for your file.
- Nulls handled; no edits outside your file.
