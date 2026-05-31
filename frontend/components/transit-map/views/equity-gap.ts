// VIEW: Equity-weighted coverage gap  (brainstorm #64, Family J) — THE HEADLINE
//
// STATUS: STUB — to be implemented by the `equity-gap` agent.
//
// Goal: the project's thesis in one layer. Combine the transit COVERAGE GAP
// (people beyond a 400 m walk, from coverage.json) with MARGINALIZATION
// (ON-Marg quintiles in neighbourhoods.json) into a single composite score, so
// high-need + under-served neighbourhoods light up as intervention targets.
// See AGENT BRIEF in .claude/agents/view-equity-gap.md.

import type { ViewModule } from "./types";

export const equityGapView: ViewModule = {
  id: "equity-gap",
  label: "Equity-weighted gap",
  group: "Equity",
  description:
    "Coverage gap × marginalization — where under-service hits vulnerable people hardest.",
  layerIds: [],

  setup() {
    // TODO(agent): join coverage gap % with marginalization quintile into a
    // composite (e.g. normalized_gap × normalized_marg), write it onto the
    // neighbourhoods source, and paint a choropleth. Push layer ids. Hidden.
  },

  legend() {
    return null; // TODO(agent): "low priority -> high priority" ramp + note
  },
};
