// VIEW: Marginalization & equity designations  (brainstorm #30-34, Family D)
//
// Paints ON-Marg 2021 quintiles (1-5) with a switcher across four dimensions,
// plus a Neighbourhood Improvement Area (NIA) bright outline overlay.

import {
  loadNeighbourhoods,
  stepColorExpression,
  RAMP_QUINTILE,
} from "@/lib/choropleth";
import {
  ensureNeighbourhoodsSource,
  addChoroplethLayers,
  wireChoroplethPopup,
  NEIGHBOURHOODS_SOURCE,
} from "./choropleth-helpers";
import type { ViewModule, ViewContext, LegendSpec } from "./types";

// ── Constants ────────────────────────────────────────────────────────────────

const FILL_ID = "marg-fill";
const NIA_OUTLINE_ID = "marg-nia-outline";

/** Fixed quintile breaks (values are already 1–5 integers). */
const QUINTILE_BREAKS = [2, 3, 4, 5] as const;

type MargField =
  | "marg_material"
  | "marg_households"
  | "marg_age_labour"
  | "marg_racialized";

// ── Module state ─────────────────────────────────────────────────────────────

let _activeField: MargField = "marg_material";

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildFillExpression(field: MargField): unknown[] {
  return stepColorExpression(field, [...QUINTILE_BREAKS], [...RAMP_QUINTILE]);
}

function formatPopup(props: Record<string, unknown>, field: MargField): string {
  const name = typeof props.name === "string" ? props.name : "Unknown";
  const quintile = props[field];
  const quintileStr =
    typeof quintile === "number" ? String(quintile) : "N/A";
  const isNia =
    props.is_nia === true || props.is_nia === "true" ? "Yes" : "No";

  const dimLabels: Record<MargField, string> = {
    marg_material: "Material deprivation",
    marg_households: "Households & dwellings",
    marg_age_labour: "Age & labour force",
    marg_racialized: "Racialized & newcomer",
  };

  return `
    <strong>${name}</strong><br/>
    <em>${dimLabels[field]}</em>: Q${quintileStr} (1 = least, 5 = most)<br/>
    Neighbourhood Improvement Area: ${isNia}
  `;
}

// ── View module ───────────────────────────────────────────────────────────────

export const marginalizationView: ViewModule = {
  id: "marginalization",
  label: "Marginalization",
  group: "Equity",
  description: "Ontario Marginalization Index 2021 quintiles, with NIA overlay.",
  layerIds: [],
  options: [
    {
      id: "marg_material",
      label: "Material deprivation",
      description:
        "Inability to afford basic needs — built from low income, no diploma, unemployment, lone-parent families and homes needing repair. The closest measure to hardship.",
    },
    {
      id: "marg_households",
      label: "Households & dwellings",
      description:
        "Less-settled housing: people living alone, renting, in apartments, or moving often (formerly 'residential instability').",
    },
    {
      id: "marg_age_labour",
      label: "Age & labour force",
      description:
        "Share of people not in the workforce — seniors and children (formerly 'dependency'). Higher means more dependents per worker.",
    },
    {
      id: "marg_racialized",
      label: "Racialized & newcomer",
      description:
        "Concentration of recent immigrants and racialized groups (formerly 'ethnic concentration').",
    },
  ],

  async setup({ map }: ViewContext): Promise<void> {
    const fc = await loadNeighbourhoods();

    ensureNeighbourhoodsSource(map, fc);

    // Add fill + neighbourhood outline (hidden).
    const [fillId, outlineId] = addChoroplethLayers(map, {
      fillId: FILL_ID,
      visible: false,
      fillOpacity: 0.65,
    });

    // Apply fixed quintile color expression for the default dimension.
    map.setPaintProperty(
      fillId,
      "fill-color",
      buildFillExpression(_activeField) as never,
    );

    // NIA outline layer — bright dashed line, no fill, filtered to is_nia == true.
    if (!map.getLayer(NIA_OUTLINE_ID)) {
      map.addLayer({
        id: NIA_OUTLINE_ID,
        type: "line",
        source: NEIGHBOURHOODS_SOURCE,
        filter: ["==", ["get", "is_nia"], true],
        layout: { visibility: "none" },
        paint: {
          "line-color": "#ffffff",
          "line-width": 2,
          "line-dasharray": [4, 2],
        },
      });
    }

    // Register all layer ids (shell toggles visibility).
    marginalizationView.layerIds.push(fillId, outlineId, NIA_OUTLINE_ID);

    // Wire popup — captures _activeField at call time via closure.
    wireChoroplethPopup(map, fillId, (props) =>
      formatPopup(props, _activeField),
    );
  },

  setOption({ map }: ViewContext, optionId: string): void {
    const field = optionId as MargField;
    _activeField = field;
    map.setPaintProperty(
      FILL_ID,
      "fill-color",
      buildFillExpression(field) as never,
    );
  },

  legend(): LegendSpec | null {
    return {
      title: "ON-Marg quintile",
      rows: [
        { color: RAMP_QUINTILE[0], label: "Q1 — least marginalized", shape: "swatch" },
        { color: RAMP_QUINTILE[1], label: "Q2", shape: "swatch" },
        { color: RAMP_QUINTILE[2], label: "Q3", shape: "swatch" },
        { color: RAMP_QUINTILE[3], label: "Q4", shape: "swatch" },
        { color: RAMP_QUINTILE[4], label: "Q5 — most marginalized", shape: "swatch" },
        { color: "#ffffff", label: "Neighbourhood Improvement Area (NIA)", shape: "line" },
      ],
      note: "Source: Ontario Marginalization Index 2021",
    };
  },
};
