// Boilerplate helpers shared by choropleth-style view modules.
//
// A "choropleth" here = the neighbourhoods source painted by one numeric metric,
// with a thin outline and a click popup. Views call addChoroplethLayers once in
// setup(), then recolorChoropleth() whenever their metric/option changes.

import maplibregl, { type MapLayerMouseEvent } from "maplibre-gl";
import {
  quantileBreaks,
  stepColorExpression,
  type NeighbourhoodFC,
} from "@/lib/choropleth";

export const NEIGHBOURHOODS_SOURCE = "neighbourhoods";

/** Ensure the shared neighbourhoods GeoJSON source exists exactly once. */
// Views that only READ base properties (density, noc*, marg*) can share the one
// default source. Views that ENRICH or COMPUTE per-feature properties (e.g. join
// coverage, derive a composite score) MUST pass their own `sourceId` — otherwise
// the shared-source dedupe keeps whichever view loaded first and silently drops
// the later view's computed fields.
export function ensureNeighbourhoodsSource(
  map: maplibregl.Map,
  data: NeighbourhoodFC,
  sourceId: string = NEIGHBOURHOODS_SOURCE,
): void {
  if (!map.getSource(sourceId)) {
    map.addSource(sourceId, { type: "geojson", data });
  }
}

export interface ChoroplethLayerOptions {
  /** Unique fill layer id (the view owns this). Outline id is `${fillId}-outline`. */
  fillId: string;
  /** Start hidden; the shell toggles visibility on activate. */
  visible?: boolean;
  fillOpacity?: number;
  /** Source to read from; defaults to the shared neighbourhoods source. Views
   *  that enrich/compute per-feature properties pass their own source id (see
   *  ensureNeighbourhoodsSource) so their computed fields actually reach the map. */
  sourceId?: string;
}

/**
 * Adds a fill + outline layer pair over the neighbourhoods source. Created
 * hidden by default. Returns the [fillId, outlineId] this added.
 */
export function addChoroplethLayers(
  map: maplibregl.Map,
  opts: ChoroplethLayerOptions,
): [string, string] {
  const outlineId = `${opts.fillId}-outline`;
  const visibility = opts.visible ? "visible" : "none";
  const source = opts.sourceId ?? NEIGHBOURHOODS_SOURCE;

  if (!map.getLayer(opts.fillId)) {
    map.addLayer({
      id: opts.fillId,
      type: "fill",
      source,
      layout: { visibility },
      paint: {
        "fill-color": "#1d4e89",
        "fill-opacity": opts.fillOpacity ?? 0.4,
      },
    });
  }
  if (!map.getLayer(outlineId)) {
    map.addLayer({
      id: outlineId,
      type: "line",
      source,
      layout: { visibility },
      paint: { "line-color": "rgba(220,235,255,0.35)", "line-width": 0.5 },
    });
  }
  return [opts.fillId, outlineId];
}

/**
 * Recolor a choropleth fill layer by a numeric property using quantile breaks.
 * Pass the loaded FC so breaks reflect the real distribution.
 */
export function recolorChoropleth(
  map: maplibregl.Map,
  fillId: string,
  fc: NeighbourhoodFC,
  property: string,
  colors: string[],
): number[] {
  const values = fc.features.map(
    (f) => (f.properties as unknown as Record<string, unknown>)[property] as number | null,
  );
  const breaks = quantileBreaks(values, colors.length);
  map.setPaintProperty(
    fillId,
    "fill-color",
    stepColorExpression(property, breaks, colors) as never,
  );
  return breaks;
}

// When the neighbourhood detail drawer is active it supersedes the small
// per-view click popups, so the shell disables them to avoid double UI. Hover
// cursors still work; only the click popup is gated.
let _popupsEnabled = true;
export function setChoroplethPopupsEnabled(enabled: boolean): void {
  _popupsEnabled = enabled;
}

/**
 * Wire a hover-cursor + click popup for a choropleth fill layer. `format`
 * returns the popup HTML for a clicked neighbourhood's properties. Call once
 * per fill layer in setup(). The click popup is skipped while popups are
 * disabled (see setChoroplethPopupsEnabled).
 */
export function wireChoroplethPopup(
  map: maplibregl.Map,
  fillId: string,
  format: (props: Record<string, unknown>) => string,
): void {
  const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true });
  map.on("mouseenter", fillId, () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", fillId, () => {
    map.getCanvas().style.cursor = "";
  });
  map.on("click", fillId, (e: MapLayerMouseEvent) => {
    if (!_popupsEnabled) return;
    const props = e.features?.[0]?.properties;
    if (!props) return;
    popup.setLngLat(e.lngLat).setHTML(format(props)).addTo(map);
  });
}
