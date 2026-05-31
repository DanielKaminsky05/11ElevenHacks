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

/** Fetch upcoming events from the same-origin proxy. */
export async function loadEvents(): Promise<EventsResponse> {
  const res = await fetch("/api/events");
  if (!res.ok) throw new Error(`Failed to load events (HTTP ${res.status})`);
  return res.json();
}
