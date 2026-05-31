// VIEW: People & need  (brainstorm #1, #2, #6, #24 — Families A & C)
//
// STATUS: STUB — to be implemented by the `demographics` agent.
//
// Goal: one neighbourhood choropleth with a METRIC SWITCHER (options dropdown)
// over: population, population density, low-income prevalence, transit-commute
// share, senior share, renter share. All fields already exist per neighbourhood
// in neighbourhoods.json. See AGENT BRIEF in .claude/agents/view-demographics.md.

import type { ViewModule } from "./types";

export const demographicsView: ViewModule = {
  id: "demographics",
  label: "People & need",
  group: "People",
  description: "Population, density, income, and who already rides transit.",
  layerIds: [],
  options: [
    { id: "density", label: "Population density" },
    { id: "low_income_pct", label: "Low-income prevalence" },
    { id: "transit_commute_pct", label: "Transit commute share" },
    { id: "senior_pct", label: "Seniors (65+)" },
    { id: "renter_pct", label: "Renters" },
  ],

  setup() {
    // TODO(agent): add neighbourhoods source + one choropleth fill; recolor by
    // the active option (default the first). Push layer ids. Create hidden.
  },

  setOption() {
    // TODO(agent): recolor the fill by the chosen property (recolorChoropleth).
  },

  legend() {
    return null; // TODO(agent): ramp + dynamic title/units per active option
  },
};
