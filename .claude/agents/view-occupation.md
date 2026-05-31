---
name: view-occupation
description: Builds the density-of-profession choropleth with an occupation switcher (brainstorm Family B). Implements frontend/components/transit-map/views/occupation.ts only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Density of profession (occupation switcher) view

First read `.claude/agents/SHARED-BRIEF.md`. Follow its hard rules.

## Your file (edit only this)

`frontend/components/transit-map/views/occupation.ts`

## What to build

One neighbourhood choropleth showing **share of the labour force in a chosen
occupation**, with a dropdown over the 10 NOC broad categories. The fields are
`noc0_pct`..`noc9_pct` (already % of labour force) in `neighbourhoods.json`.

NOC labels (use these for the `options`):
- `noc0_pct` Management
- `noc1_pct` Business, finance & admin
- `noc2_pct` Sciences & tech
- `noc3_pct` Health
- `noc4_pct` Education, law, social & gov
- `noc5_pct` Art, culture & recreation
- `noc6_pct` Sales & service
- `noc7_pct` Trades & transport
- `noc8_pct` Natural resources & agriculture
- `noc9_pct` Manufacturing & utilities

Order the dropdown to lead with the most transit-relevant ones (Health, Trades,
Sales & service, Business & finance, Sciences) then the rest.

Implementation:
1. `setup`: `loadNeighbourhoods()`, `ensureNeighbourhoodsSource`,
   `addChoroplethLayers` (hidden), recolor by the first option using `RAMP_BLUE`
   (or `RAMP_PURPLE`). Push ids into `layerIds`. Cache FC + current option.
2. `setOption`: recolor by the chosen `noc*_pct` (quantile breaks).
3. Popup: name + "<occupation>: X% of labour force".
4. `legend()`: ramp + title "<occupation> — % of labour force" + low/high labels
   from `propertyExtent` of the active field.

## Acceptance

- Dropdown switches occupation live.
- `npx tsc --noEmit` + `npx eslint` clean for your file.
- Nulls handled; no edits outside your file.
