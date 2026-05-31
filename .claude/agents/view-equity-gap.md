---
name: view-equity-gap
description: Builds the equity-weighted coverage gap view — the headline (brainstorm #64). Implements frontend/components/transit-map/views/equity-gap.ts only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Equity-weighted coverage gap view (THE HEADLINE)

First read `.claude/agents/SHARED-BRIEF.md`. Follow its hard rules. This is the
project's flagship view — make it correct and legible.

## Your file (edit only this)

`frontend/components/transit-map/views/equity-gap.ts`

## What to build

A single composite choropleth: **where under-service collides with vulnerability.**

1. Load `loadNeighbourhoods()` and `loadCoverage()`.
2. For each neighbourhood compute a **priority score**:
   - `gapShare` = uncovered fraction = `1 - cov/100` (from coverage.json byNum).
   - `marg` = `marg_material` quintile (1–5) → normalize to `(q-1)/4` → 0..1.
     If `marg_material` is null, treat the neighbourhood as score `null`.
   - `score = gapShare * margNorm` (both 0..1 → score 0..1). This makes a
     neighbourhood light up only when it is BOTH under-served AND marginalized.
   - Optionally multiply by population for a "people affected" flavour, but keep
     the primary metric the 0..1 product for interpretability.
3. Write `score` (and the inputs `cov`, `gap`, `marg_material`) onto each
   feature's properties, set as the source data, `addChoroplethLayers`, and color
   by `score` with `RAMP_NEED` (green = low priority → red = high priority) using
   **quantile breaks** (`quantileBreaks(scores, 5)`).
4. Popup: name, coverage %, marginalization quintile, and the priority score,
   with a one-line interpretation (e.g. "high gap + high marginalization").

Push fill + outline ids into `layerIds`. Create hidden.

## Legend

`title: "Equity-weighted coverage gap"`, `ramp` = `RAMP_NEED` with
`lowLabel: "lower priority"`, `highLabel: "higher priority"`, and a `note`
explaining the composite: `"coverage gap × marginalization (ON-Marg material)"`.

## Acceptance

- `npx tsc --noEmit` + `npx eslint` clean for your file.
- Score handles nulls; neighbourhoods missing marg render in the null color.
- No edits outside your file.
