// Optimizer endpoint — proxies the browser to the FastAPI backend.
//
// The browser calls same-origin `/api/optimize` (no CORS); this route forwards
// to the backend per-tool REST endpoint `POST /tools/optimize_layout` (TransitRL
// FastAPI). The backend URL comes from BACKEND_URL (server-only env), defaulting
// to the local dev port — mirrors app/api/chat/route.ts.
//
// Unlike the planner there is no offline fallback: the optimizer needs the real
// city grid, so if the backend is unreachable we surface an error the panel can
// show.

import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:9000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const res = await fetch(`${BACKEND_URL}/tools/optimize_layout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // Greedy + local search is fast, but the first call also loads the city
      // grid; give it generous headroom.
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data?.detail === "string"
          ? data.detail
          : `backend returned HTTP ${res.status}`;
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    if (data?.error) {
      return NextResponse.json({ error: data.error }, { status: 422 });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Optimizer backend unreachable. Is the FastAPI server running?" },
      { status: 502 },
    );
  }
}
