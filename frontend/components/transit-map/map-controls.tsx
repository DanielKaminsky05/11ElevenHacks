"use client";

import type maplibregl from "maplibre-gl";

export interface MapControlsProps {
  /** Returns the live map instance (or null before it's ready). */
  getMap: () => maplibregl.Map | null;
  /** The active data view id, or null for "Network only". Non-null = a
   *  choropleth is showing, which reads best flattened to 2D. */
  activeViewId: string | null;
  /** True once the map has loaded. */
  ready: boolean;
}

/**
 * VIEW CONTROLS — 2D/3D camera toggle + reset.
 *
 * STATUS: STUB — implemented by the `map-controls` agent.
 * See .claude/agents/feat-map-controls.md.
 *
 * Goal: a small, neat control cluster letting the planner flatten the tilted
 * 3D scene to a true top-down 2D view (and back), plus a reset. Choropleths
 * distort under perspective, so this should AUTO-flatten to 2D when a data view
 * becomes active and restore 3D for the plain network — while still allowing a
 * manual override.
 */
export function MapControls({ getMap, activeViewId, ready }: MapControlsProps) {
  void getMap;
  void activeViewId;
  void ready;
  return null;
}
