// VIEW: Transit coverage & gaps  (brainstorm #40, Family E)
//
// Coverage % choropleth over neighbourhoods (joined from coverage.json by `num`),
// an uncovered-grid red-dot layer, a popup, and a legend.

import type { FeatureCollection, Point } from "geojson";
import {
  loadNeighbourhoods,
  loadCoverage,
  stepColorExpression,
  RAMP_COVERAGE,
  type CoverageData,
} from "@/lib/choropleth";
import {
  ensureNeighbourhoodsSource,
  addChoroplethLayers,
  wireChoroplethPopup,
} from "./choropleth-helpers";
import type { ViewModule, LegendSpec } from "./types";

const FILL_ID = "coverage-fill";
// Own source: coverage joins cov/gap onto the features, so it must not share the
// dedupe-guarded base source (whichever view loads first would win otherwise).
const COVERAGE_SOURCE = "coverage-src";
// Note: outline id is derived by addChoroplethLayers as `${FILL_ID}-outline`.
const GAP_GRID_SOURCE = "coverage-gap-grid";
const GAP_GRID_LAYER = "coverage-gap-dots";

// Fixed scale breaks for 0–100% coverage.
const COV_BREAKS = [20, 40, 60, 80];

// Cached after setup() so legend() can read them without awaiting.
let cachedMeta: CoverageData["meta"] | null = null;

function formatPopup(props: Record<string, unknown>): string {
  const name = typeof props.name === "string" ? props.name : "Neighbourhood";
  const cov =
    typeof props.cov === "number" ? props.cov.toFixed(1) + "%" : "n/a";
  const gap =
    typeof props.gap === "number"
      ? props.gap.toLocaleString() + " people"
      : "n/a";
  return `<strong>${name}</strong><br/>Walk access: ${cov}<br/>Beyond 400 m: ${gap}`;
}

export const coverageView: ViewModule = {
  id: "coverage",
  label: "Transit coverage",
  group: "Transit",
  description: "Population within a 400 m walk of a transit stop — and the gaps.",
  layerIds: [],

  async setup({ map }) {
    const [fc, coverage] = await Promise.all([
      loadNeighbourhoods(),
      loadCoverage(),
    ]);

    cachedMeta = coverage.meta;

    // Join coverage data onto each neighbourhood feature's properties.
    for (const feature of fc.features) {
      const num = feature.properties.num;
      const entry = coverage.byNum[String(num)];
      if (entry) {
        (feature.properties as unknown as Record<string, unknown>).cov =
          entry.cov;
        (feature.properties as unknown as Record<string, unknown>).gap =
          entry.gap;
      }
    }

    // Own source carrying the joined cov/gap properties.
    ensureNeighbourhoodsSource(map, fc, COVERAGE_SOURCE);

    // Add choropleth fill + outline layers (hidden).
    const [fillId, outlineId] = addChoroplethLayers(map, {
      fillId: FILL_ID,
      sourceId: COVERAGE_SOURCE,
      visible: false,
      fillOpacity: 0.4,
    });
    coverageView.layerIds.push(fillId, outlineId);

    // Apply the fixed 0–100 coverage color scale.
    const colorExpr = stepColorExpression("cov", COV_BREAKS, RAMP_COVERAGE);
    map.setPaintProperty(FILL_ID, "fill-color", colorExpr as never);

    // Build the uncovered-grid GeoJSON (covered === 0 → red dot).
    const gapPoints: FeatureCollection<Point> = {
      type: "FeatureCollection",
      features: coverage.grid
        .filter(([, , covered]) => covered === 0)
        .map(([lon, lat]) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {},
        })),
    };

    if (!map.getSource(GAP_GRID_SOURCE)) {
      map.addSource(GAP_GRID_SOURCE, { type: "geojson", data: gapPoints });
    }

    if (!map.getLayer(GAP_GRID_LAYER)) {
      map.addLayer({
        id: GAP_GRID_LAYER,
        type: "circle",
        source: GAP_GRID_SOURCE,
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 3,
          "circle-color": "#d11149",
          "circle-opacity": 0.75,
          "circle-stroke-width": 0,
        },
      });
    }
    coverageView.layerIds.push(GAP_GRID_LAYER);

    // Hover + click popup on neighbourhood fill.
    wireChoroplethPopup(map, FILL_ID, formatPopup);
  },

  legend(): LegendSpec | null {
    let note: string | undefined;
    if (cachedMeta) {
      const pct = cachedMeta.citywideCoverage.toFixed(1);
      const gap = cachedMeta.gapPopulation.toLocaleString();
      note = `${pct}% covered · ${gap} beyond 400 m`;
    }
    return {
      title: "Walk access to transit (400 m)",
      ramp: {
        colors: RAMP_COVERAGE,
        lowLabel: "0% (gap)",
        highLabel: "100%",
      },
      note,
    };
  },
};
