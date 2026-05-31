// VIEW: Density of profession  (brainstorm Family B, #15-23)
//
// Neighbourhood choropleth of the share of the labour force in a chosen NOC
// broad category (noc0_pct .. noc9_pct), with a dropdown switcher across all
// 10 categories, ordered by transit relevance.

import {
  loadNeighbourhoods,
  propertyExtent,
  RAMP_PURPLE,
  type NeighbourhoodFC,
  type NeighbourhoodProps,
} from "@/lib/choropleth";
import {
  addChoroplethLayers,
  ensureNeighbourhoodsSource,
  recolorChoropleth,
  wireChoroplethPopup,
} from "./choropleth-helpers";
import type { LegendSpec, ViewContext, ViewModule } from "./types";

const FILL_ID = "occupation-fill";

// Each option is the % of the neighbourhood's labour force in one of Statistics
// Canada's 10 broad NOC occupation groups. Ordered by transit relevance.
const NOC_DESC =
  "% of the local workforce in this occupation group (Statistics Canada NOC).";
const OPTIONS = [
  { id: "noc3_pct", label: "Health", description: `Nurses, aides, technicians and other health workers — ${NOC_DESC}` },
  { id: "noc7_pct", label: "Trades & transport", description: `Construction, mechanics, drivers and equipment operators — ${NOC_DESC}` },
  { id: "noc6_pct", label: "Sales & service", description: `Retail, food service and customer-facing roles (often shift work) — ${NOC_DESC}` },
  { id: "noc1_pct", label: "Business, finance & admin", description: `Office, finance and administrative roles — ${NOC_DESC}` },
  { id: "noc2_pct", label: "Sciences & tech", description: `Engineering, IT and applied-science roles — ${NOC_DESC}` },
  { id: "noc0_pct", label: "Management", description: `Senior managers and executives — ${NOC_DESC}` },
  { id: "noc4_pct", label: "Education, law, social & gov", description: `Teachers, lawyers, social and government workers — ${NOC_DESC}` },
  { id: "noc5_pct", label: "Art, culture & recreation", description: `Artists, media, sport and recreation workers — ${NOC_DESC}` },
  { id: "noc8_pct", label: "Natural resources & agriculture", description: `Farming, forestry, fishing and mining — ${NOC_DESC}` },
  { id: "noc9_pct", label: "Manufacturing & utilities", description: `Factory, processing and utilities workers — ${NOC_DESC}` },
] as const;

// Module-scoped cache so legend() can read data after setup resolves.
let _fc: NeighbourhoodFC | null = null;
let _activeOption: (typeof OPTIONS)[number] = OPTIONS[0];

export const occupationView: ViewModule = {
  id: "occupation",
  label: "Occupations",
  group: "People",
  description: "Share of the labour force by occupation category, per neighbourhood.",
  layerIds: [],
  options: OPTIONS.map((o) => ({ id: o.id, label: o.label, description: o.description })),

  async setup(ctx: ViewContext) {
    const { map } = ctx;

    const fc = await loadNeighbourhoods();
    _fc = fc;

    ensureNeighbourhoodsSource(map, fc);

    const [fillId, outlineId] = addChoroplethLayers(map, {
      fillId: FILL_ID,
      visible: false,
      fillOpacity: 0.65,
    });
    occupationView.layerIds.push(fillId, outlineId);

    // Colour by the first (default) option.
    recolorChoropleth(map, FILL_ID, fc, _activeOption.id, RAMP_PURPLE);

    wireChoroplethPopup(map, FILL_ID, (props: Record<string, unknown>) => {
      const name = String(props["name"] ?? "Unknown");
      const raw = props[_activeOption.id];
      const pct =
        typeof raw === "number" && Number.isFinite(raw)
          ? raw.toFixed(1)
          : "N/A";
      return `<strong>${name}</strong><br>${_activeOption.label}: ${pct}% of labour force`;
    });
  },

  setOption(ctx: ViewContext, optionId: string) {
    const opt = OPTIONS.find((o) => o.id === optionId);
    if (!opt || !_fc) return;
    _activeOption = opt;
    recolorChoropleth(ctx.map, FILL_ID, _fc, opt.id, RAMP_PURPLE);
  },

  legend(): LegendSpec | null {
    const title = `${_activeOption.label} — % of labour force`;

    if (!_fc) {
      return {
        title,
        ramp: { colors: RAMP_PURPLE, lowLabel: "Low", highLabel: "High" },
      };
    }

    const prop = _activeOption.id as keyof NeighbourhoodProps;
    const extent = propertyExtent(_fc, prop);
    const lowLabel = extent ? `${extent[0].toFixed(1)}%` : "Low";
    const highLabel = extent ? `${extent[1].toFixed(1)}%` : "High";

    return {
      title,
      ramp: { colors: RAMP_PURPLE, lowLabel, highLabel },
    };
  },
};
