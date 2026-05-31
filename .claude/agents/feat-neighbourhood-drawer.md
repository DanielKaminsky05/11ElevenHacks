---
name: feat-neighbourhood-drawer
description: Builds the neighbourhood detail drawer shown on map click. Implements frontend/components/transit-map/neighbourhood-drawer.tsx only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: Neighbourhood detail drawer

Implement ONLY this file:
`frontend/components/transit-map/neighbourhood-drawer.tsx` (it already exists as
a stub with the exact prop contract). Edit nothing else.

## Why
The map has ~25 metrics per neighbourhood but only ever showed one in a popup.
This drawer turns a glance into a real planning profile when a planner clicks a
neighbourhood.

## Contract (already in the stub — keep identical)
```ts
import type { NeighbourhoodProps } from "@/lib/choropleth";
interface NeighbourhoodDrawerProps {
  feature: NeighbourhoodProps | null;  // null = closed -> return null
  onClose: () => void;
}
export function NeighbourhoodDrawer(props): JSX.Element | null
```
`NeighbourhoodProps` (all already loaded — no fetching) includes:
`num, name, is_nia, area_km2, pop, density, low_income_pct,
transit_commute_pct, car_pct, active_pct, senior_pct, renter_pct,
noc0_pct..noc9_pct (occupation % of labour force),
marg_households, marg_material, marg_age_labour, marg_racialized (quintiles 1-5)`.
Any field may be null — render "—" for missing values.

## What to build
A slide-in panel from the **right edge**, full height (`absolute top-0 right-0
h-full`), width ~340px, `z-30` (above the other panels; it may overlay them while
open — that's fine for a focused detail view), with a close button calling
`onClose`. Return `null` when `feature` is null.

Sections (use the fields above; keep it scannable, not a data dump):
- **Header:** neighbourhood name; a small "NIA" badge if `is_nia`.
- **Snapshot:** population, density (/km²), area (km²).
- **Income & housing:** low-income prevalence %, renters %.
- **Mobility:** transit-commute %, car %, active (walk+bike) %.
- **Age:** seniors 65+ %.
- **Marginalization (ON-Marg quintiles 1–5):** the four dimensions as small
  Q1–Q5 chips/bars (1 = least, 5 = most marginalized). Labels: Material
  deprivation, Households & dwellings, Age & labour force, Racialized & newcomer.
- **Top occupations:** from `noc0_pct..noc9_pct`, show the top 3 by value with
  their labels (0 Management, 1 Business/finance/admin, 2 Sciences & tech,
  3 Health, 4 Education/law/social/gov, 5 Art/culture/rec, 6 Sales & service,
  7 Trades & transport, 8 Natural resources & agriculture, 9 Manufacturing &
  utilities).

## Styling (match the other panels)
`rounded-l-xl border-l border-sky-400/25 bg-[#0c1628]/95 text-[#dce6f5]
shadow-2xl backdrop-blur-md`, `pointer-events-auto`, padded, with a scrollable
body (`overflow-y-auto`). Section headers: `text-[10px] uppercase tracking-[1px]
text-[#6f86ab]`. A subtle slide/fade transition is a plus but optional.

## Verify (in your worktree's frontend/ dir)
1. `cmd //c "mklink /J node_modules C:\Users\Danie\code\11ElevenHacks\frontend\node_modules"`
2. `npx tsc --noEmit` — clean
3. `npx eslint components/transit-map/neighbourhood-drawer.tsx` — clean

Commit ONLY `neighbourhood-drawer.tsx` to your worktree branch. Don't push/merge.
Report: branch + commit SHA, what you built, tsc/eslint results, blockers.
