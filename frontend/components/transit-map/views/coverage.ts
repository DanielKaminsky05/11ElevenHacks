// VIEW: Transit coverage & gaps  (brainstorm #40, Family E)
//
// STATUS: STUB — to be implemented by the `coverage` agent.
//
// Goal: show what share of each neighbourhood's population is within a 400 m
// walk of a transit stop, and surface the GAPS (low-coverage areas + the
// uncovered grid cells). Data: loadCoverage() (public/coverage.json) joined to
// loadNeighbourhoods() by `num`. See AGENT BRIEF in .claude/agents/view-coverage.md.

import type { ViewModule } from "./types";

export const coverageView: ViewModule = {
  id: "coverage",
  label: "Transit coverage",
  group: "Transit",
  description: "Population within a 400 m walk of a transit stop — and the gaps.",
  layerIds: [],

  setup() {
    // TODO(agent): add neighbourhoods source (ensureNeighbourhoodsSource),
    // a coverage choropleth fill keyed on coverage %, and the uncovered grid
    // points from coverage.json. Push layer ids into `layerIds`. Create hidden.
  },

  legend() {
    return null; // TODO(agent): coverage ramp 0-100% (red gap -> green covered)
  },
};
