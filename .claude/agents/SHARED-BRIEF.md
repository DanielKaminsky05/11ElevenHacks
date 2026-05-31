# Shared brief — map view builder agents

You are one of five agents each building **one map-overlay view** for the
TransitRL frontend (Next.js + MapLibre). The shared infrastructure already
exists and is committed. Your job: implement **exactly one view module file** and
nothing else, so all five of us merge without conflicts.

## Hard rules (do not break these)

1. **Edit ONLY your assigned view file** (e.g. `frontend/components/transit-map/views/coverage.ts`).
   Do not touch the registry, the shell, other views, shared libs, or configs.
   If you think a shared file needs a change, STOP and note it in your final
   report instead of editing it.
2. You are working in a dedicated **git worktree on your own branch**. When your
   file is done and verified, **commit ONLY your one view file** to your current
   branch with a clear message, then **report your branch name and commit SHA**.
   Do **not** push, do **not** merge, do **not** switch branches, do **not**
   `git add` anything other than your single view file. The orchestrator merges.
3. Keep the public API of your module identical to the stub: same `export const
   xView: ViewModule`, same `id`/`group`. You may change `label`, `description`,
   `options`, and the bodies of `setup`/`setOption`/`legend`, and you MUST push
   real ids into `layerIds`.
4. TypeScript strict mode, no `any`. Match the surrounding code style.

## The data you have (already in `frontend/public/`, no raw data needed)

- `neighbourhoods.json` — 158 neighbourhood polygons. Load with
  `loadNeighbourhoods()` from `@/lib/choropleth`. Each feature's `properties`
  match the `NeighbourhoodProps` type:
  - `num`, `name`, `is_nia` (bool), `area_km2`, `pop`, `density`
  - `low_income_pct`, `transit_commute_pct`, `car_pct`, `active_pct`,
    `senior_pct`, `renter_pct`
  - `noc0_pct`..`noc9_pct` (occupation share of labour force, %)
  - `marg_households`, `marg_material`, `marg_age_labour`, `marg_racialized`
    (ON-Marg quintiles 1–5; 5 = most marginalized)
  - Any metric may be `null` for a neighbourhood — handle it (the helpers do).
- `coverage.json` — load with `loadCoverage()`. Shape:
  `{ byNum: { [num]: { cov, served, gap } }, grid: [[lon,lat,covered01], …], meta: {...} }`.
  `cov` is % of population within a 400 m walk of a transit stop.

## The helpers you should use (from `@/lib/choropleth`)

- `loadNeighbourhoods()`, `loadCoverage()` — async loaders.
- `quantileBreaks(values, classes)` — quantile thresholds for a metric.
- `stepColorExpression(prop, breaks, colors)` — MapLibre `step` paint expression.
- `propertyExtent(fc, prop)` — `[min,max]` for legend labels.
- Color ramps: `RAMP_BLUE`, `RAMP_NEED`, `RAMP_COVERAGE`, `RAMP_PURPLE`,
  `RAMP_QUINTILE` (each is a 5-color array).

## And from `./choropleth-helpers`

- `ensureNeighbourhoodsSource(map, fc)` — add the shared `neighbourhoods`
  GeoJSON source once (safe to call from multiple views; it dedupes).
- `addChoroplethLayers(map, { fillId, visible:false, fillOpacity })` → returns
  `[fillId, outlineId]`. Creates a fill + outline pair, **hidden**.
- `recolorChoropleth(map, fillId, fc, property, colors)` → returns the breaks.
- `wireChoroplethPopup(map, fillId, (props) => htmlString)` — hover + click popup.
- `NEIGHBOURHOODS_SOURCE` — the shared source id constant.

## The ViewModule contract (from `./types`)

```ts
setup(ctx: { map }): void | Promise<void>   // add hidden sources/layers once
layerIds: string[]                           // ids you created; shell toggles them
legend(): LegendSpec | null                  // { title, ramp?, rows?, note? }
options?: ViewOption[]                        // optional sub-metric dropdown
setOption?(ctx, optionId): void              // restyle in place (no add/remove)
```

`LegendSpec.ramp = { colors: string[], lowLabel: string, highLabel: string }`.
`LegendSpec.rows = { color, label, shape?: "swatch"|"line"|"dot" }[]`.

### Critical conventions

- In `setup`, **load data, add your source/layers HIDDEN** (`visible:false` /
  `layout.visibility:"none"`), and **populate `this`'s `layerIds`** by pushing
  the ids you created (mutate the exported object's `layerIds` array). The shell
  flips visibility when your view is selected — never make layers visible yourself.
- `setup` runs after the map `load` event and after the route/stop layers exist.
  Insert fills **below** the route lines for legibility by passing a `beforeId`
  if you add layers manually (e.g. `"subway-glow"`); the helper adds on top,
  which is acceptable for a first pass.
- `legend()` may be called before or after data loads. If your ramp/labels need
  loaded data, cache it in a module-scoped variable during `setup` and read it
  in `legend()`; return a sensible static legend if data isn't ready.
- If you have `options`, `setOption` must restyle existing layers (call
  `recolorChoropleth`), not add new ones. Default to `options[0]` in `setup`.

## How to verify your work (in your git worktree)

Your worktree has no `node_modules`. Create a junction to the main one, then
typecheck and lint **only**:

```bash
cmd //c "mklink /J node_modules C:\\Users\\Danie\\code\\11ElevenHacks\\frontend\\node_modules"
# run the two commands below from the frontend/ dir of your worktree
npx tsc --noEmit
npx eslint components/transit-map/views/<yourfile>.ts
```

Both must pass with no errors about your file. (If the junction fails, say so in
your report; the orchestrator will verify on merge.) You do **not** need to run
the dev server or build.

## Your final report back to the orchestrator

State: (1) the file you changed, (2) the layer ids you created, (3) the metric(s)
/ options you implemented, (4) tsc + eslint result, (5) anything you couldn't do
or any shared-file change you think is needed.
