// The plugin contract every map view implements.
//
// The map shell (map-view.tsx) owns the MapLibre instance and the active-view
// state. Each view is a self-contained module that knows how to add its own
// sources/layers and describe its legend. Views are registered once in
// registry.ts; the shell shows/hides them by id. This lets each view live in
// its own file so multiple can be built in parallel without conflicts.

import type maplibregl from "maplibre-gl";

/** Everything a view needs from the shell to build itself. */
export interface ViewContext {
  map: maplibregl.Map;
}

/** A single legend row a view wants rendered when it is active. */
export interface LegendRow {
  color: string;
  label: string;
  /** "swatch" = filled box (choropleth bin), "line" = route line, "dot" = point. */
  shape?: "swatch" | "line" | "dot";
}

/** A continuous legend gradient (e.g. a choropleth ramp) when active. */
export interface LegendSpec {
  title: string;
  rows?: LegendRow[];
  /** Optional gradient bar: ordered colors + low/high labels. */
  ramp?: { colors: string[]; lowLabel: string; highLabel: string };
  /** Optional footnote (units, source, caveat). */
  note?: string;
}

/** Optional sub-metric a view can expose (e.g. occupation category, ON-Marg dimension). */
export interface ViewOption {
  id: string;
  label: string;
}

export interface ViewModule {
  /** Stable unique id, kebab-case (e.g. "coverage", "equity-gap"). */
  id: string;
  /** Short label for the view switcher. */
  label: string;
  /** Grouping bucket in the switcher UI (e.g. "Transit", "Equity", "People"). */
  group: string;
  /** One-line description shown under the active view. */
  description: string;

  /**
   * Add this view's sources and layers to the map. Called once, after the map's
   * "load" event. Create layers HIDDEN (layout.visibility = "none"); the shell
   * toggles them via setActive. Safe to assume the basemap + network sources
   * may or may not exist yet — only depend on your own sources.
   */
  setup(ctx: ViewContext): Promise<void> | void;

  /** Layer ids this view owns. The shell flips their visibility on activate. */
  layerIds: string[];

  /** Legend to render while this view is active. May depend on loaded data. */
  legend(): LegendSpec | null;

  /** Optional sub-metric options (rendered as a dropdown when this view is active). */
  options?: ViewOption[];

  /**
   * Switch the active sub-metric (only called if `options` is non-empty).
   * Re-style the layers in place; do not add/remove layers here.
   */
  setOption?(ctx: ViewContext, optionId: string): void;
}
