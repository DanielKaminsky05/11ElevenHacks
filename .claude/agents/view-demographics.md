---
name: view-demographics
description: Builds the People & need demographic choropleth with a metric switcher (brainstorm #1,2,6,24). Implements frontend/components/transit-map/views/demographics.ts only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: People & need (demographic switcher) view

First read `.claude/agents/SHARED-BRIEF.md`. Follow its hard rules.

## Your file (edit only this)

`frontend/components/transit-map/views/demographics.ts`

## What to build

One neighbourhood choropleth with a **sub-metric dropdown** (`options` +
`setOption`) over fields that already exist per neighbourhood:

| option id | label | ramp | units |
|---|---|---|---|
| `density` | Population density | `RAMP_BLUE` | /km² |
| `low_income_pct` | Low-income prevalence | `RAMP_NEED` | % |
| `transit_commute_pct` | Transit commute share | `RAMP_BLUE` | % |
| `senior_pct` | Seniors (65+) | `RAMP_PURPLE` | % |
| `renter_pct` | Renters | `RAMP_PURPLE` | % |

(Keep `pop`/population too if you like — but the five above are the priority.)

Implementation:
1. `setup`: `loadNeighbourhoods()`, `ensureNeighbourhoodsSource`,
   `addChoroplethLayers` (hidden), then recolor by the **first option**
   (`density`). Push fill+outline ids into `layerIds`. Cache the loaded FC and
   the current option in module scope.
2. `setOption(ctx, optionId)`: `recolorChoropleth(map, fillId, fc, optionId,
   rampFor(optionId))` and update the cached current option.
3. Popup: show name + the active metric's value with units.
4. `legend()`: return a ramp legend whose `title`, ramp colors, and low/high
   labels reflect the **current option** (use `propertyExtent` for the labels;
   append units). Provide a sensible default if called before `setup`.

## Acceptance

- Dropdown switches the metric live; ramp + units update.
- `npx tsc --noEmit` + `npx eslint` clean for your file.
- Nulls handled; no edits outside your file.
