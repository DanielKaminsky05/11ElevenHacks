// Planner chat endpoint.
//
// Turns a plain-English transit goal into reward weights + a readable reply.
// This is a deterministic STUB that keyword-maps the goal onto the four reward
// channels so the UI works end-to-end today. Swap the body of `plan()` for a
// call to the open model + RL backend when it's available — the request/response
// contract (PlannerRequest / PlannerResponse) stays the same.

import { NextResponse } from "next/server";
import type {
  PlannerRequest,
  PlannerResponse,
  RewardWeights,
} from "@/lib/planner";

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

/** Deterministic keyword planner. Replace with the model/RL call later. */
function plan(goal: string): PlannerResponse {
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

  const result: PlannerResponse = plan(goal);
  return NextResponse.json(result);
}
