// Events feed endpoint — proxies the browser to the FastAPI backend.
//
// Same-origin for the browser (no CORS); forwards to the backend GET /events.
// Query params pass through, so /api/events?category=closure works. If the
// backend is unreachable, returns a small built-in fallback so the news feed
// still shows something in a frontend-only demo.

import { NextResponse } from "next/server";
import type { EventsResponse } from "@/lib/events";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:9000";

const FALLBACK: EventsResponse = {
  as_of: new Date().toISOString().slice(0, 10),
  window_days: 120,
  count: 2,
  events: [
    {
      id: "fallback-king-closure",
      title: "Road closure: King St W (Bathurst → Jarvis)",
      category: "closure",
      kind: "supply_disruption",
      venue: { name: "King St W", lat: 43.645, lon: -79.395 },
      start: new Date().toISOString(),
      end: new Date(Date.now() + 5 * 864e5).toISOString(),
      impact: {
        magnitude: "high",
        affected_lines: ["504 King", "508 Lake Shore"],
        affected_stations: [],
        shuttle_replacement: true,
      },
      description:
        "Watermain work shuts the King corridor through the core; the 504 King is diverted.",
      source: "fallback",
    },
    {
      id: "fallback-worldcup",
      title: "FIFA World Cup 26 — Opening Match at BMO Field",
      category: "sports",
      kind: "demand_surge",
      venue: { name: "BMO Field", lat: 43.6332, lon: -79.4185 },
      start: new Date(Date.now() + 2 * 864e5).toISOString(),
      end: new Date(Date.now() + 2 * 864e5 + 3 * 36e5).toISOString(),
      impact: {
        magnitude: "severe",
        expected_attendance: 30000,
        radius_km: 2.5,
        affected_lines: [],
        affected_stations: [],
      },
      description: "Major arrival/departure surge on Line 1, GO Lakeshore, and 509/511 streetcars.",
      source: "fallback",
    },
  ],
};

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const target = new URL("/events", BACKEND_URL);
  // Forward whitelisted query params through to the backend.
  for (const key of ["as_of", "days_ahead", "category", "kind", "limit"]) {
    for (const value of incoming.searchParams.getAll(key)) {
      target.searchParams.append(key, value);
    }
  }

  try {
    const res = await fetch(target, { signal: AbortSignal.timeout(8000) });
    if (res.ok) {
      return NextResponse.json((await res.json()) as EventsResponse);
    }
  } catch {
    // Backend unreachable — fall through.
  }
  return NextResponse.json(FALLBACK);
}
