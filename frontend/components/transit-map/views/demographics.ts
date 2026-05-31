// VIEW: People & need  (brainstorm #1, #2, #6, #24 — Families A & C)
//
// Neighbourhood choropleth with a metric switcher across demographic fields.
// Sub-metrics: density, low_income_pct, transit_commute_pct, senior_pct, renter_pct.

import {
  loadNeighbourhoods,
  propertyExtent,
  RAMP_BLUE,
  RAMP_NEED,
  RAMP_PURPLE,
  type NeighbourhoodFC,
  type NeighbourhoodProps,
} from "@/lib/choropleth";
import type { ViewContext, ViewModule } from "./types";
import {
  addChoroplethLayers,
  ensureNeighbourhoodsSource,
  recolorChoropleth,
  wireChoroplethPopup,
} from "./choropleth-helpers";

// ---------------------------------------------------------------------------
// Option metadata
// ---------------------------------------------------------------------------

interface MetricMeta {
  prop: keyof NeighbourhoodProps;
  label: string;
  ramp: string[];
  units: string;
}

const METRICS: Record<string, MetricMeta> = {
  density: {
    prop: "density",
    label: "Population density",
    ramp: RAMP_BLUE,
    units: "/km²",
  },
  low_income_pct: {
    prop: "low_income_pct",
    label: "Low-income prevalence",
    ramp: RAMP_NEED,
    units: "%",
  },
  transit_commute_pct: {
    prop: "transit_commute_pct",
    label: "Transit commute share",
    ramp: RAMP_BLUE,
    units: "%",
  },
  senior_pct: {
    prop: "senior_pct",
    label: "Seniors (65+)",
    ramp: RAMP_PURPLE,
    units: "%",
  },
  renter_pct: {
    prop: "renter_pct",
    label: "Renters",
    ramp: RAMP_PURPLE,
    units: "%",
  },
};

const FILL_ID = "demographics-fill";
const DEFAULT_OPTION_ID = "density";

// ---------------------------------------------------------------------------
// Module-scope state (populated during setup)
// ---------------------------------------------------------------------------

let _fc: NeighbourhoodFC | null = null;
let _activeOptionId: string = DEFAULT_OPTION_ID;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatValue(raw: unknown, units: string): string {
  if (raw === null || raw === undefined || raw === "") return "n/a";
  const n = Number(raw);
  if (!Number.isFinite(n)) return "n/a";
  return units === "/km²" ? `${Math.round(n).toLocaleString()}${units}` : `${n.toFixed(1)}${units}`;
}

function popupHtml(props: Record<string, unknown>): string {
  const meta = METRICS[_activeOptionId] ?? METRICS[DEFAULT_OPTION_ID];
  const name = String(props["name"] ?? "Unknown");
  const value = formatValue(props[meta.prop], meta.units);
  return `<strong>${name}</strong><br/>${meta.label}: ${value}`;
}

// ---------------------------------------------------------------------------
// View module
// ---------------------------------------------------------------------------

export const demographicsView: ViewModule = {
  id: "demographics",
  label: "People & need",
  group: "People",
  description: "Population, density, income, and who already rides transit.",
  layerIds: [],
  options: [
    {
      id: "density",
      label: "Population density",
      description: "Residents per km² — where the city is packed vs. spread out.",
    },
    {
      id: "low_income_pct",
      label: "Low-income prevalence",
      description:
        "% of residents below Statistics Canada's after-tax Low-Income Measure — higher means more poverty.",
    },
    {
      id: "transit_commute_pct",
      label: "Transit commute share",
      description: "% of workers who get to work by transit — where it's already the norm.",
    },
    {
      id: "senior_pct",
      label: "Seniors (65+)",
      description: "% of residents 65 or older — a proxy for mobility-limited, transit-reliant riders.",
    },
    {
      id: "renter_pct",
      label: "Renters",
      description: "% of households that rent vs. own — a proxy for housing precarity and turnover.",
    },
  ],

  async setup(ctx: ViewContext): Promise<void> {
    const { map } = ctx;

    // Load data
    const fc = await loadNeighbourhoods();
    _fc = fc;
    _activeOptionId = DEFAULT_OPTION_ID;

    // Add shared source (deduped)
    ensureNeighbourhoodsSource(map, fc);

    // Add fill + outline layers, both hidden
    const [fillId, outlineId] = addChoroplethLayers(map, {
      fillId: FILL_ID,
      visible: false,
      fillOpacity: 0.65,
    });

    // Register layer ids so the shell can toggle visibility
    demographicsView.layerIds.push(fillId, outlineId);

    // Paint the default metric
    const meta = METRICS[DEFAULT_OPTION_ID];
    recolorChoropleth(map, fillId, fc, meta.prop, meta.ramp);

    // Hover + click popup
    wireChoroplethPopup(map, fillId, popupHtml);
  },

  setOption(ctx: ViewContext, optionId: string): void {
    if (!_fc) return;
    const meta = METRICS[optionId];
    if (!meta) return;
    _activeOptionId = optionId;
    recolorChoropleth(ctx.map, FILL_ID, _fc, meta.prop, meta.ramp);
  },

  legend() {
    const meta = METRICS[_activeOptionId] ?? METRICS[DEFAULT_OPTION_ID];

    // Static fallback before data loads
    if (!_fc) {
      return {
        title: meta.label,
        ramp: {
          colors: meta.ramp,
          lowLabel: `Low ${meta.units}`,
          highLabel: `High ${meta.units}`,
        },
      };
    }

    const extent = propertyExtent(_fc, meta.prop);
    const [min, max] = extent ?? [0, 100];

    const lowLabel =
      meta.units === "/km²"
        ? `${Math.round(min).toLocaleString()}${meta.units}`
        : `${min.toFixed(1)}${meta.units}`;
    const highLabel =
      meta.units === "/km²"
        ? `${Math.round(max).toLocaleString()}${meta.units}`
        : `${max.toFixed(1)}${meta.units}`;

    return {
      title: meta.label,
      ramp: {
        colors: meta.ramp,
        lowLabel,
        highLabel,
      },
    };
  },
};
