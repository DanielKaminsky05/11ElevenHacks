// Translate planner reward weights into a concrete map action.
//
// STATUS: STUB — implemented by the `planner-actions` agent.
//
// Pure + transport-agnostic (no React, no maplibre): given the weights the
// planner inferred and the loaded neighbourhood data, decide which data view to
// show and which neighbourhoods to focus on. map-view.tsx consumes the result
// (switches the view + fits the map to the highlighted neighbourhoods). Keep it
// pure so it's unit-testable. See .claude/agents/feat-planner-actions.md.

import type { NeighbourhoodFC } from "@/lib/choropleth";
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

/**
 * Decide the map action for a set of reward weights.
 *
 * TODO(agent): pick the view that matches the dominant weight (equity →
 * "equity-gap", coverage → "coverage", travelTime → "demographics" transit
 * commute, etc.) and choose the top-N most relevant neighbourhoods from `fc`
 * using fields available in NeighbourhoodProps.
 */
export function planToMapAction(
  weights: RewardWeights,
  fc: NeighbourhoodFC,
): PlanAction {
  void weights;
  void fc;
  return { viewId: "equity-gap", rationale: "", highlightNums: [] };
}
