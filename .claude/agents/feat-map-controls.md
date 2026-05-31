---
name: feat-map-controls
description: Builds the 2D/3D camera control (auto-flatten for choropleths). Implements frontend/components/transit-map/map-controls.tsx only.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Agent: 2D / 3D view controls

Implement ONLY this file: `frontend/components/transit-map/map-controls.tsx`
(it already exists as a stub with the exact prop contract). Edit nothing else.

## Why
Choropleths distort under the map's 3D tilt — areas near the top get squished,
which defeats the point of a fill map. This control flattens the scene to true
top-down 2D when a data view is active, and restores the cinematic 3D for the
plain route network.

## Contract (already in the stub — keep it identical)
```ts
interface MapControlsProps {
  getMap: () => maplibregl.Map | null;  // live map, or null pre-load
  activeViewId: string | null;          // non-null = a choropleth is showing
  ready: boolean;
}
export function MapControls(props): JSX.Element | null
```

## What to build
- A small, neat floating control cluster. Placement: **bottom-center**
  (`absolute bottom-4 left-1/2 -translate-x-1/2`) — the four corners are taken
  (legend TL, view switcher TR, planner BR, route details BL). Keep
  `pointer-events-auto` and `z-10`.
- A **2D / 3D toggle** (two segmented buttons or one toggle). 3D = the demo
  camera (`pitch 58, bearing -18`); 2D = `pitch 0, bearing 0`. Use
  `map.easeTo({ pitch, bearing, duration: 600 })`. Import `TORONTO_VIEW` from
  `@/lib/transit` for the 3D angles (`TORONTO_VIEW.pitch`, `.bearing`).
- **Auto-flatten:** a `useEffect` on `activeViewId` — when it becomes non-null,
  ease to 2D; when it returns to null, ease back to 3D. Keep a local `is3D`
  state so the toggle reflects/overrides the current camera.
- A **Reset** button: `easeTo` back to `TORONTO_VIEW` (center, zoom, pitch,
  bearing).
- Guard every map access: `const map = getMap(); if (!map) return;`. Do nothing
  until `ready`.

## Styling (match the other panels exactly)
Container: `rounded-xl border border-sky-400/25 bg-[#0c1628]/90 text-[#dce6f5]
shadow-2xl backdrop-blur-md`. Buttons: small, `text-[12px]`, active state uses a
brighter bg like `bg-sky-500/30 border-sky-400/60 text-white`, inactive
`bg-white/[0.04] hover:bg-white/[0.08]`.

## Verify (in your worktree's frontend/ dir)
1. Junction node_modules: `cmd //c "mklink /J node_modules C:\Users\Danie\code\11ElevenHacks\frontend\node_modules"`
2. `npx tsc --noEmit` — clean
3. `npx eslint components/transit-map/map-controls.tsx` — clean (note: refs
   must not be assigned during render; use effects)

Then commit ONLY `map-controls.tsx` to your worktree branch. Don't push/merge.
Report: branch name + commit SHA, what you built, tsc/eslint results, blockers.
