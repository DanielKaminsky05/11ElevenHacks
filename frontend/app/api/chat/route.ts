// Planner chat endpoint — proxies the browser to the FastAPI backend.
//
// The browser calls same-origin `/api/chat` (no CORS); this route forwards to
// the backend `POST /planner` (TransitRL FastAPI on the Spark). The backend URL
// comes from BACKEND_URL (server-only env), defaulting to the local dev port.
//
// If the backend is unreachable, fall back to a deterministic keyword planner so
// the UI still works in a frontend-only demo. Both paths return the same
// PlannerResponse contract (lib/planner.ts).

import { NextResponse } from "next/server";
import type {
  PlannerRequest,
  PlannerResponse,
  RewardWeights,
} from "@/lib/planner";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:9000";

function normalize(w: RewardWeights): RewardWeights {
  const total = w.coverage + w.travelTime + w.equity + w.constraints || 1;
  const r = (x: number) => Math.round((x / total) * 100) / 100;
  return {
    coverage: r(w.coverage),
    travelTime: r(w.travelTime),
    equity: r(w.equity),
    constraints: r(w.constraints),
  };
}

/** Offline fallback: keyword planner mirroring the backend service. */
function planLocally(goal: string): PlannerResponse {
  const g = goal.toLowerCase();
  const w: RewardWeights = { coverage: 1, travelTime: 1, equity: 1, constraints: 1 };
  const reasons: string[] = [];

  if (/(equity|low.?income|marginal|vulnerable|senior|newcomer|disadvantage)/.test(g)) {
    w.equity += 3;
    reasons.push("weighting equity for vulnerable populations");
  }
  if (/(coverage|gap|access|reach|underserved|desert|walk)/.test(g)) {
    w.coverage += 3;
    reasons.push("prioritizing coverage of underserved areas");
  }
  if (/(commute|travel time|fast|speed|downtown|job|employment)/.test(g)) {
    w.travelTime += 2;
    reasons.push("protecting travel times to key destinations");
  }
  if (/(without|don't|do not|keep|maintain|avoid|protect|budget|cost|spacing)/.test(g)) {
    w.constraints += 2;
    reasons.push("respecting your stated constraints");
  }

  const weights = normalize(w);
  const reasonText = reasons.length
    ? reasons.join(", ")
    : "balancing coverage, travel time, equity, and constraints";
  const reply =
    `Got it — I'll optimize stop placement by ${reasonText}. ` +
    `Translated into reward weights: coverage ${weights.coverage}, ` +
    `travel-time ${weights.travelTime}, equity ${weights.equity}, ` +
    `constraints ${weights.constraints}. ` +
    `Run the agent to watch it relocate stops toward this goal.`;
  return { reply, weights };
}

export async function POST(request: Request) {
  let body: PlannerRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const goal = (body?.goal ?? "").trim();
  if (!goal) {
    return NextResponse.json({ error: "Missing goal" }, { status: 400 });
  }

  // Prefer the real backend; fall back to the local planner if it's down.
  try {
    const res = await fetch(`${BACKEND_URL}/planner`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, history: body.history ?? [] }),
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = (await res.json()) as PlannerResponse;
      return NextResponse.json(data);
    }
  } catch {
    // Backend unreachable — fall through to the local planner.
  }

  return NextResponse.json(planLocally(goal));
}
