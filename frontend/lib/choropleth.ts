// Shared helpers for neighbourhood-choropleth map views.
//
// Pure data/geometry utilities + color ramps + a MapLibre step-expression
// builder. No React and no maplibre *instance* state here, so view modules and
// tests can import freely. Each view module composes these into its own layers.

import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";

/** A neighbourhood's joined attributes (see scripts/build-neighbourhoods.py). */
export interface NeighbourhoodProps {
  num: number;
  name: string;
  is_nia: boolean;
  area_km2: number;
  pop: number | null;
  density: number | null;
  low_income_pct: number | null;
  transit_commute_pct: number | null;
  car_pct: number | null;
  active_pct: number | null;
  senior_pct: number | null;
  renter_pct: number | null;
  // Occupation shares (NOC 0-9) as % of the labour force.
  noc0_pct: number | null;
  noc1_pct: number | null;
  noc2_pct: number | null;
  noc3_pct: number | null;
  noc4_pct: number | null;
  noc5_pct: number | null;
  noc6_pct: number | null;
  noc7_pct: number | null;
  noc8_pct: number | null;
  noc9_pct: number | null;
  // ON-Marg 2021 quintiles (1 = least, 5 = most marginalized).
  marg_households?: number | null;
  marg_material?: number | null;
  marg_age_labour?: number | null;
  marg_racialized?: number | null;
}

export type NeighbourhoodFC = FeatureCollection<
  Polygon | MultiPolygon,
  NeighbourhoodProps
>;

/** Per-neighbourhood transit coverage (see scripts/build-coverage.py). */
export interface CoverageEntry {
  cov: number; // % of population within walk distance of a stop
  served: number;
  gap: number; // people beyond walk distance
}

export interface CoverageData {
  byNum: Record<string, CoverageEntry>;
  grid: [number, number, number][]; // [lon, lat, covered 0|1]
  meta: {
    walkM: number;
    stepM: number;
    citywideCoverage: number;
    gapPopulation: number;
    gridCells: number;
  };
}

const PUBLIC_NEIGHBOURHOODS = "/neighbourhoods.json";
const PUBLIC_COVERAGE = "/coverage.json";

/** Loads the enriched neighbourhood polygons from the public directory. */
export async function loadNeighbourhoods(): Promise<NeighbourhoodFC> {
  const res = await fetch(PUBLIC_NEIGHBOURHOODS);
  if (!res.ok) throw new Error(`Failed to load neighbourhoods (HTTP ${res.status})`);
  return res.json();
}

/** Loads the transit-coverage dataset from the public directory. */
export async function loadCoverage(): Promise<CoverageData> {
  const res = await fetch(PUBLIC_COVERAGE);
  if (!res.ok) throw new Error(`Failed to load coverage (HTTP ${res.status})`);
  return res.json();
}

// --- Color ramps (5-class, colour-blind-aware, tuned for the dark basemap) ---

/** Sequential blue — generic "more of a good thing" (e.g. density, transit use). */
export const RAMP_BLUE = ["#0d2247", "#1d4e89", "#2e8b9e", "#7fd17f", "#f4e04d"];

/** Sequential "heat" — need / disadvantage / low values are alarming (red). */
export const RAMP_NEED = ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#d11149"];

/** Coverage 0-100%: low coverage = red (gap), high = green. */
export const RAMP_COVERAGE = ["#d11149", "#f3722c", "#f9c74f", "#90be6d", "#1a9850"];

/** Purple sequential — neutral categorical/quantitative emphasis. */
export const RAMP_PURPLE = ["#2d1e3e", "#5a3a7e", "#8b5fbf", "#b98fd9", "#e7d4f5"];

/** 5 discrete quintile colors for ON-Marg style 1-5 data. */
export const RAMP_QUINTILE = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"];

/**
 * Quantile break points that split sorted numeric values into `classes` bins.
 * Returns the lower edge of bins 2..classes (so `classes-1` breaks). Nulls and
 * non-finite values are ignored. Falls back to evenly spaced breaks when there
 * are too few distinct values.
 */
export function quantileBreaks(
  values: (number | null | undefined)[],
  classes = 5,
): number[] {
  const v = values
    .filter((x): x is number => typeof x === "number" && Number.isFinite(x))
    .sort((a, b) => a - b);
  if (v.length === 0) return [];
  const breaks: number[] = [];
  for (let i = 1; i < classes; i++) {
    const q = i / classes;
    const idx = Math.min(v.length - 1, Math.round(q * (v.length - 1)));
    let b = v[idx];
    // ensure strictly increasing breaks for MapLibre "step"
    if (breaks.length && b <= breaks[breaks.length - 1]) {
      b = breaks[breaks.length - 1] + 1e-6;
    }
    breaks.push(b);
  }
  return breaks;
}

/**
 * Builds a MapLibre `step` paint expression mapping a numeric feature property
 * to `colors`, using `breaks` (length = colors.length - 1) as thresholds.
 * Missing values render as `nullColor`.
 */
export function stepColorExpression(
  property: string,
  breaks: number[],
  colors: string[],
  nullColor = "#2a2a35",
): unknown[] {
  const expr: unknown[] = [
    "case",
    ["==", ["typeof", ["get", property]], "number"],
    ["step", ["get", property], colors[0]],
    nullColor,
  ];
  const step = expr[2] as unknown[];
  breaks.forEach((b, i) => step.push(b, colors[i + 1]));
  return expr;
}

/** Min/max of a numeric property across a feature collection (ignores nulls). */
export function propertyExtent(
  fc: NeighbourhoodFC,
  property: keyof NeighbourhoodProps,
): [number, number] | null {
  let min = Infinity;
  let max = -Infinity;
  for (const f of fc.features) {
    const x = f.properties[property];
    if (typeof x === "number" && Number.isFinite(x)) {
      if (x < min) min = x;
      if (x > max) max = x;
    }
  }
  return min <= max ? [min, max] : null;
}
