// Pure transit-network helpers. No React/Next imports so this stays testable
// and usable from both server and client code.

import type { Feature, FeatureCollection, LineString, Point } from "geojson";

export type TransitMode = "subway" | "streetcar" | "bus";

export interface ModeStyle {
  label: string;
  /** Base line width in pixels for the crisp "core" line. */
  width: number;
  color: string;
}

/** Per-mode rendering config (colors match the TTC palette used in the demo). */
export const MODE: Record<TransitMode, ModeStyle> = {
  subway: { label: "Subway", width: 5, color: "#F8C300" },
  streetcar: { label: "Streetcar", width: 3.2, color: "#DA251D" },
  bus: { label: "Bus", width: 1.6, color: "#3FA7FF" },
};

/** Color for bus-stop markers. */
export const STOP_COLOR = "#ffd66b";

/** Default Toronto camera, including the demo's signature 3D tilt. */
export const TORONTO_VIEW = {
  center: [-79.38, 43.715] as [number, number],
  zoom: 11.2,
  pitch: 58,
  bearing: -18,
};

/** Free OpenFreeMap dark vector basemap (no API key, OpenMapTiles schema). */
export const DARK_STYLE_URL = "https://tiles.openfreemap.org/styles/fiord";

/** Solid dark-blue fill shown behind the basemap while tiles load. */
export const MAP_BACKGROUND = "#0a1628";

// --- Raw schema of public/network.json (precomputed, [lat, lon] ordered) ----

interface RawRoute {
  id: string;
  short: string;
  long: string;
  mode: TransitMode;
  color: string;
  trips: number;
  /** Polyline points as [lat, lon] pairs. */
  pts: [number, number][];
}

/** Stop tuple: [lat, lon, name, modeFlags, routeIds]. */
type RawStop = [number, number, string, string, string[]];

export interface NetworkCounts {
  subway: number;
  streetcar: number;
  bus: number;
  busStops: number;
}

export interface NetworkData {
  routes: RawRoute[];
  stops: RawStop[];
  counts: NetworkCounts;
}

/** Fetches the precomputed transit network from the public directory. */
export async function loadNetwork(): Promise<NetworkData> {
  const res = await fetch("/network.json");
  if (!res.ok) {
    throw new Error(`Failed to load network.json (HTTP ${res.status})`);
  }
  return res.json();
}

export interface RouteProps {
  id: string;
  short: string;
  long: string;
  mode: TransitMode;
  name: string;
  color: string;
  trips: number;
}

/** GTFS feed window the `trips` counts are drawn from (for honest labelling). */
export const SERVICE_PERIOD = { label: "Jun 7–20, 2026", days: 14 };

export type ServiceLevel = "Frequent" | "Standard" | "Infrequent" | "Limited";

export interface RouteSchedule {
  tripsPerDay: number;
  /** Approximate headway in minutes, GTFS-derived (both directions, ~18h span). */
  headwayMin: number;
  level: ServiceLevel;
}

/**
 * Derives an approximate service level from the GTFS trip count. This is an
 * estimate from total trips over the feed window, NOT a published timetable.
 */
export function deriveSchedule(trips: number): RouteSchedule {
  const tripsPerDay = trips / SERVICE_PERIOD.days;
  // ~18h service span; trips count both directions, so per-direction = /2.
  const headwayMin = tripsPerDay > 0 ? Math.round((18 * 60) / (tripsPerDay / 2)) : 0;
  let level: ServiceLevel;
  if (tripsPerDay >= 120) level = "Frequent";
  else if (tripsPerDay >= 50) level = "Standard";
  else if (tripsPerDay >= 15) level = "Infrequent";
  else level = "Limited";
  return { tripsPerDay: Math.round(tripsPerDay), headwayMin, level };
}

export interface StopProps {
  name: string;
  modes: string;
  /** 1 when this stop is served by a bus route, else 0 (used as a map filter). */
  bus: number;
}

/**
 * Converts the precomputed `[lat, lon]` network data into GL-ready GeoJSON
 * (`[lon, lat]`) for the route lines and stop points.
 */
export function toGeoJSON(data: NetworkData): {
  routes: FeatureCollection<LineString, RouteProps>;
  stops: FeatureCollection<Point, StopProps>;
} {
  const routes: Feature<LineString, RouteProps>[] = data.routes.map((r) => ({
    type: "Feature",
    properties: {
      id: r.id,
      short: r.short,
      long: r.long,
      mode: r.mode,
      name: `${r.short} ${r.long}`.trim(),
      color: r.color,
      trips: r.trips,
    },
    geometry: {
      type: "LineString",
      coordinates: r.pts.map(([lat, lon]) => [lon, lat]),
    },
  }));

  const stops: Feature<Point, StopProps>[] = data.stops.map(
    ([lat, lon, name, modes]) => ({
      type: "Feature",
      properties: {
        name,
        modes: modes || "",
        bus: (modes || "").includes("b") ? 1 : 0,
      },
      geometry: { type: "Point", coordinates: [lon, lat] },
    }),
  );

  return {
    routes: { type: "FeatureCollection", features: routes },
    stops: { type: "FeatureCollection", features: stops },
  };
}
