// Translate planner reward weights into a concrete map action.
//
// Pure + transport-agnostic (no React, no maplibre): given the weights the
// planner inferred and the loaded neighbourhood data, decide which data view to
// show and which neighbourhoods to focus on. map-view.tsx consumes the result
// (switches the view + fits the map to the highlighted neighbourhoods). Keep it
// pure so it's unit-testable. See .claude/agents/feat-planner-actions.md.

import type { NeighbourhoodFC, NeighbourhoodProps } from "@/lib/choropleth";
import type { RewardWeights } from "@/lib/planner";

export interface PlanAction {
  /** Data-view id to activate (must match a view id in views/registry.ts:
   *  "coverage" | "equity-gap" | "demographics" | "occupation" | "marginalization"). */
  viewId: string;
  /** One-line explanation of why (shown/logged by the caller). */
  rationale: string;
  /** Neighbourhood numbers to emphasize / fit the camera to (may be empty). */
  highlightNums: number[];
}

const TOP_N = 8;

/**
 * Determine the dominant weight channel using a deterministic tie-break order:
 * equity > coverage > travelTime > constraints.
 */
function dominantChannel(weights: RewardWeights): keyof RewardWeights {
  const { equity, coverage, travelTime, constraints } = weights;
  const max = Math.max(equity, coverage, travelTime, constraints);
  if (equity === max) return "equity";
  if (coverage === max) return "coverage";
  if (travelTime === max) return "travelTime";
  return "constraints";
}

/** Extract and sort neighbourhood properties, skipping features with null sort key. */
function topByDesc(
  features: NeighbourhoodFC["features"],
  primary: keyof NeighbourhoodProps,
  secondary: keyof NeighbourhoodProps | null,
  ascending = false,
): number[] {
  type ScoredEntry = { num: number; prim: number; sec: number };

  const entries: ScoredEntry[] = [];
  for (const f of features) {
    const p = f.properties;
    const primVal = p[primary];
    if (typeof primVal !== "number" || !Number.isFinite(primVal)) continue;
    const secVal =
      secondary !== null
        ? typeof p[secondary] === "number" && Number.isFinite(p[secondary] as number)
          ? (p[secondary] as number)
          : 0
        : 0;
    entries.push({ num: p.num, prim: primVal, sec: secVal });
  }

  entries.sort((a, b) => {
    const primCmp = ascending ? a.prim - b.prim : b.prim - a.prim;
    if (primCmp !== 0) return primCmp;
    // secondary tiebreak always descending (higher = worse-off)
    return b.sec - a.sec;
  });

  return entries.slice(0, TOP_N).map((e) => e.num);
}

/**
 * Decide the map action for a set of reward weights.
 *
 * Picks the view that matches the dominant weight (equity → "equity-gap",
 * coverage → "coverage", travelTime → "demographics") and chooses the top-8
 * most relevant neighbourhoods from `fc`. Tie-break order: equity > coverage >
 * travelTime > constraints. Returns `highlightNums: []` only if no usable data.
 */
export function planToMapAction(
  weights: RewardWeights,
  fc: NeighbourhoodFC,
): PlanAction {
  const channel = dominantChannel(weights);

  switch (channel) {
    case "equity": {
      const highlightNums = topByDesc(
        fc.features,
        "marg_material",
        "low_income_pct",
        false,
      );
      return {
        viewId: "equity-gap",
        rationale:
          "Focusing on the most marginalized, lowest-income neighbourhoods.",
        highlightNums,
      };
    }

    case "coverage": {
      const highlightNums = topByDesc(
        fc.features,
        "transit_commute_pct",
        null,
        true, // lowest transit use = most under-served
      );
      return {
        viewId: "coverage",
        rationale:
          "Highlighting neighbourhoods with the lowest transit use to close coverage gaps.",
        highlightNums,
      };
    }

    case "travelTime": {
      const highlightNums = topByDesc(
        fc.features,
        "transit_commute_pct",
        null,
        true,
      );
      return {
        viewId: "demographics",
        rationale:
          "Showing neighbourhoods where transit is least used to improve travel time access.",
        highlightNums,
      };
    }

    default: {
      // constraints dominant or unexpected value
      const highlightNums = topByDesc(
        fc.features,
        "marg_material",
        "low_income_pct",
        false,
      );
      return {
        viewId: "equity-gap",
        rationale:
          "Balancing constraints while protecting the most marginalized neighbourhoods.",
        highlightNums,
      };
    }
  }
}
