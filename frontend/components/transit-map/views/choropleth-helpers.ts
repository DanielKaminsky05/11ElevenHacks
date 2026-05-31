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
export function ensureNeighbourhoodsSource(
  map: maplibregl.Map,
  data: NeighbourhoodFC,
): void {
  if (!map.getSource(NEIGHBOURHOODS_SOURCE)) {
    map.addSource(NEIGHBOURHOODS_SOURCE, { type: "geojson", data });
  }
}

export interface ChoroplethLayerOptions {
  /** Unique fill layer id (the view owns this). Outline id is `${fillId}-outline`. */
  fillId: string;
  /** Start hidden; the shell toggles visibility on activate. */
  visible?: boolean;
  fillOpacity?: number;
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

  if (!map.getLayer(opts.fillId)) {
    map.addLayer({
      id: opts.fillId,
      type: "fill",
      source: NEIGHBOURHOODS_SOURCE,
      layout: { visibility },
      paint: {
        "fill-color": "#1d4e89",
        "fill-opacity": opts.fillOpacity ?? 0.6,
      },
    });
  }
  if (!map.getLayer(outlineId)) {
    map.addLayer({
      id: outlineId,
      type: "line",
      source: NEIGHBOURHOODS_SOURCE,
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

/**
 * Wire a hover-cursor + click popup for a choropleth fill layer. `format`
 * returns the popup HTML for a clicked neighbourhood's properties. Call once
 * per fill layer in setup().
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
    const props = e.features?.[0]?.properties;
    if (!props) return;
    popup.setLngLat(e.lngLat).setHTML(format(props)).addTo(map);
  });
}
