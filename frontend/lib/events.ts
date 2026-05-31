// Shared types + client for the events news feed.
//
// Mirrors the backend Event schema (app/schemas/events.py). The browser calls
// same-origin /api/events, which proxies to the backend GET /events.

export type EventCategory =
  | "sports"
  | "festival"
  | "concert"
  | "construction"
  | "closure"
  | "weather";

export type EventKind = "demand_surge" | "supply_disruption";
export type Magnitude = "low" | "medium" | "high" | "severe";

export interface Venue {
  name: string;
  lat: number | null;
  lon: number | null;
}

export interface TransitImpact {
  magnitude: Magnitude;
  expected_attendance?: number | null;
  radius_km?: number | null;
  affected_lines: string[];
  affected_stations: string[];
  shuttle_replacement?: boolean | null;
}

export interface CityEvent {
  id: string;
  title: string;
  category: EventCategory;
  kind: EventKind;
  venue: Venue;
  start: string; // ISO datetime
  end: string;
  impact: TransitImpact;
  description: string;
  source: string;
}

export interface EventsResponse {
  as_of: string;
  window_days: number;
  count: number;
  events: CityEvent[];
}

/** Display metadata per category: short label + an emoji marker. */
export const CATEGORY_META: Record<EventCategory, { label: string; icon: string }> = {
  sports: { label: "Sports", icon: "🏟️" },
  festival: { label: "Festival", icon: "🎉" },
  concert: { label: "Concert", icon: "🎵" },
  construction: { label: "Construction", icon: "🚧" },
  closure: { label: "Closure", icon: "⛔" },
  weather: { label: "Weather", icon: "🌧️" },
};

/** Accent color per magnitude (for the severity dot/border). */
export const MAGNITUDE_COLOR: Record<Magnitude, string> = {
  low: "#34d399",
  medium: "#fbbf24",
  high: "#fb923c",
  severe: "#f87171",
};

/** True if the event is a closure/disruption (vs. a demand surge). */
export function isClosure(e: CityEvent): boolean {
  return e.kind === "supply_disruption";
}

/** Properties carried on each event map feature. */
export interface EventFeatureProps {
  id: string;
  title: string;
  category: EventCategory;
  kind: EventKind;
  magnitude: Magnitude;
  color: string;
  isClosure: boolean;
  venueName: string;
}

/**
 * GeoJSON point FeatureCollection of events that have venue coordinates, for the
 * map's event markers. Diffuse events (no coords) are skipped.
 */
export function eventsToGeoJSON(events: CityEvent[]): GeoJSON.FeatureCollection<
  GeoJSON.Point,
  EventFeatureProps
> {
  const features: GeoJSON.Feature<GeoJSON.Point, EventFeatureProps>[] = [];
  for (const e of events) {
    if (e.venue.lat == null || e.venue.lon == null) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [e.venue.lon, e.venue.lat] },
      properties: {
        id: e.id,
        title: e.title,
        category: e.category,
        kind: e.kind,
        magnitude: e.impact.magnitude,
        color: MAGNITUDE_COLOR[e.impact.magnitude],
        isClosure: isClosure(e),
        venueName: e.venue.name,
      },
    });
  }
  return { type: "FeatureCollection", features };
}

// The mock catalogue is the 2026 World Cup era, so anchor the feed's window
// there rather than the machine clock (which may sit outside that range and
// return nothing). Swap to a live "today" once real feeds are wired in.
const DEMO_AS_OF = "2026-06-01";
const DEMO_DAYS_AHEAD = 200;

/** Fetch upcoming events from the same-origin proxy. */
export async function loadEvents(): Promise<EventsResponse> {
  const res = await fetch(
    `/api/events?as_of=${DEMO_AS_OF}&days_ahead=${DEMO_DAYS_AHEAD}`,
  );
  if (!res.ok) throw new Error(`Failed to load events (HTTP ${res.status})`);
  return res.json();
}
