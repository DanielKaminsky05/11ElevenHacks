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

/** NOC options ordered by transit relevance (per spec). */
const OPTIONS = [
  { id: "noc3_pct", label: "Health" },
  { id: "noc7_pct", label: "Trades & transport" },
  { id: "noc6_pct", label: "Sales & service" },
  { id: "noc1_pct", label: "Business, finance & admin" },
  { id: "noc2_pct", label: "Sciences & tech" },
  { id: "noc0_pct", label: "Management" },
  { id: "noc4_pct", label: "Education, law, social & gov" },
  { id: "noc5_pct", label: "Art, culture & recreation" },
  { id: "noc8_pct", label: "Natural resources & agriculture" },
  { id: "noc9_pct", label: "Manufacturing & utilities" },
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
  options: OPTIONS.map((o) => ({ id: o.id, label: o.label })),

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
