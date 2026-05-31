// VIEW: Equity-weighted coverage gap  (brainstorm #64, Family J) — THE HEADLINE
//
// Composite choropleth: coverage gap × material marginalization.
// A neighbourhood lights up only when it is BOTH under-served AND marginalized,
// making it the project's primary intervention-targeting layer.

import {
  loadNeighbourhoods,
  loadCoverage,
  RAMP_NEED,
} from "@/lib/choropleth";
import {
  ensureNeighbourhoodsSource,
  addChoroplethLayers,
  recolorChoropleth,
  wireChoroplethPopup,
} from "./choropleth-helpers";
import type { ViewModule, LegendSpec } from "./types";

const FILL_ID = "equity-gap-fill";
// Own source: this view computes eq_score onto each feature, so it must not
// share the dedupe-guarded base source (the computed props would be dropped).
const EQUITY_SOURCE = "equity-gap-src";
const SCORE_PROP = "eq_score";

/** Build the interpretation string shown in the popup. */
function interpretScore(score: number | null): string {
  if (score === null) return "No marginalization data";
  if (score >= 0.75) return "High gap + high marginalization";
  if (score >= 0.5) return "Moderate–high priority";
  if (score >= 0.25) return "Moderate priority";
  return "Lower priority";
}

/** Format a number for display, defaulting to "N/A" when null. */
function fmt(v: number | null | undefined, digits = 1): string {
  return typeof v === "number" ? v.toFixed(digits) : "N/A";
}

export const equityGapView: ViewModule = {
  id: "equity-gap",
  label: "Equity-weighted gap",
  group: "Equity",
  description:
    "Coverage gap × marginalization — where under-service hits vulnerable people hardest.",
  layerIds: [],

  async setup({ map }) {
    // Load both datasets in parallel.
    const [fc, coverage] = await Promise.all([
      loadNeighbourhoods(),
      loadCoverage(),
    ]);

    // Compute the composite score for each neighbourhood and write it onto the
    // feature properties so MapLibre paint expressions can reference it.
    for (const feature of fc.features) {
      const { num, marg_material } = feature.properties;
      const entry = coverage.byNum[String(num)];

      const cov = entry?.cov ?? null;
      const gap = entry?.gap ?? null;

      // gapShare: fraction of population NOT within walk distance (0..1).
      const gapShare = cov !== null ? 1 - cov / 100 : null;

      // margNorm: material quintile (1–5) normalised to 0..1.
      const margNorm =
        typeof marg_material === "number" && marg_material !== null
          ? (marg_material - 1) / 4
          : null;

      // score is null if either input is missing.
      const score =
        gapShare !== null && margNorm !== null ? gapShare * margNorm : null;

      // Attach computed props — double-cast to allow writing extra fields.
      const p = feature.properties as unknown as Record<string, unknown>;
      p[SCORE_PROP] = score;
      p["eq_cov"] = cov;
      p["eq_gap"] = gap;
      p["eq_marg"] = marg_material ?? null;
    }

    // Own source carrying the computed eq_score / eq_cov / eq_marg properties.
    ensureNeighbourhoodsSource(map, fc, EQUITY_SOURCE);

    // Add fill + outline layers, both hidden. Capture ids.
    const [fillId, outlineId] = addChoroplethLayers(map, {
      fillId: FILL_ID,
      sourceId: EQUITY_SOURCE,
      visible: false,
      fillOpacity: 0.45,
    });
    equityGapView.layerIds.push(fillId, outlineId);

    // Paint by score using quantile breaks on non-null scores.
    recolorChoropleth(map, fillId, fc, SCORE_PROP, RAMP_NEED);

    // Hover cursor + click popup.
    wireChoroplethPopup(map, fillId, (props) => {
      const name = String(props["name"] ?? "Unknown");
      const cov = typeof props["eq_cov"] === "number" ? props["eq_cov"] : null;
      const marg = typeof props["eq_marg"] === "number" ? props["eq_marg"] : null;
      const rawScore = props[SCORE_PROP];
      const score = typeof rawScore === "number" ? rawScore : null;

      return `
        <strong>${name}</strong><br/>
        Coverage: ${fmt(cov)}%<br/>
        Marginalization (material quintile): ${fmt(marg, 0)}/5<br/>
        Priority score: ${fmt(score, 3)}<br/>
        <em>${interpretScore(score)}</em>
      `.trim();
    });
  },

  legend(): LegendSpec | null {
    return {
      title: "Equity-weighted coverage gap",
      ramp: {
        colors: RAMP_NEED,
        lowLabel: "lower priority",
        highLabel: "higher priority",
      },
      note: "coverage gap × marginalization (ON-Marg material)",
    };
  },
};
