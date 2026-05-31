// VIEW: Marginalization & equity designations  (brainstorm #30-34, Family D)
//
// STATUS: STUB — to be implemented by the `marginalization` agent.
//
// Goal: paint the ON-Marg 2021 quintiles (1-5) with a SWITCHER across the four
// dimensions (material deprivation, households/dwellings, age/labour-force,
// racialized & newcomer), plus a Neighbourhood Improvement Area (NIA) outline
// overlay from the `is_nia` flag. See AGENT BRIEF in
// .claude/agents/view-marginalization.md.

import type { ViewModule } from "./types";

export const marginalizationView: ViewModule = {
  id: "marginalization",
  label: "Marginalization",
  group: "Equity",
  description: "Ontario Marginalization Index 2021 quintiles, with NIA overlay.",
  layerIds: [],
  options: [
    { id: "marg_material", label: "Material deprivation" },
    { id: "marg_households", label: "Households & dwellings" },
    { id: "marg_age_labour", label: "Age & labour force" },
    { id: "marg_racialized", label: "Racialized & newcomer" },
  ],

  setup() {
    // TODO(agent): add neighbourhoods source + a quintile choropleth (1-5) for
    // the active dimension, plus an NIA outline layer (filter is_nia == true).
    // Push layer ids. Create hidden.
  },

  setOption() {
    // TODO(agent): recolor by the chosen marg_* quintile property (1-5 ramp).
  },

  legend() {
    return null; // TODO(agent): 5 quintile swatches + NIA outline key
  },
};
