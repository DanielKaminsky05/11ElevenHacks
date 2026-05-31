// VIEW: Density of profession  (brainstorm Family B, #15-23)
//
// STATUS: STUB — to be implemented by the `occupation` agent.
//
// Goal: a neighbourhood choropleth of the share of the labour force in a chosen
// occupation (NOC broad category), with a SWITCHER across the 10 categories
// (noc0_pct .. noc9_pct in neighbourhoods.json). "Where do health workers /
// trades / sales & service workers live?" See AGENT BRIEF in
// .claude/agents/view-occupation.md.

import type { ViewModule } from "./types";

export const occupationView: ViewModule = {
  id: "occupation",
  label: "Occupations",
  group: "People",
  description: "Share of the labour force by occupation category, per neighbourhood.",
  layerIds: [],
  options: [
    { id: "noc3_pct", label: "Health" },
    { id: "noc7_pct", label: "Trades & transport" },
    { id: "noc6_pct", label: "Sales & service" },
    { id: "noc1_pct", label: "Business & finance" },
    { id: "noc2_pct", label: "Sciences & tech" },
    { id: "noc5_pct", label: "Art & culture" },
  ],

  setup() {
    // TODO(agent): add neighbourhoods source + one choropleth fill; recolor by
    // the active NOC option (default the first). Push layer ids. Create hidden.
  },

  setOption() {
    // TODO(agent): recolor the fill by the chosen noc*_pct property.
  },

  legend() {
    return null; // TODO(agent): ramp + "% of labour force" + active occupation
  },
};
