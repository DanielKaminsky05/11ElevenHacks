// Client for the stop-placement optimizer.
//
// The optimizer is the backend `optimize_layout` tool: given reward weights it
// runs greedy + local search and returns the recommended stop layout plus the
// per-step trajectory (so the map can animate the network being built). The
// browser calls same-origin `/api/optimize`, which proxies to the FastAPI
// backend `POST /tools/optimize_layout` (see app/api/optimize/route.ts).

import type { RewardWeights } from "@/lib/planner";

/** A stop position the optimizer placed. */
export interface OptStop {
  lon: number;
  lat: number;
}

/** Per-channel "% of the budget-achievable best" scores, each in [0, 1]. */
export interface ChannelScores {
  coverage: number;
  equity: number;
  travel: number;
  constraint: number;
}

/** One step of the greedy/swap trajectory — a frame for the build animation. */
export interface OptStep {
  stops: OptStop[];
  R: number;
  channel_scores: ChannelScores;
}

/** The full optimize_layout result. */
export interface OptResult {
  stops: OptStop[];
  steps: OptStep[];
  channel_scores: ChannelScores;
  final_reward: number;
  /** "budget" (filled) or "diminishing_returns" (stops stopped paying off). */
  stopped_reason: string;
  budget: number;
  stop_cost: number;
}

export interface RunOptimizerParams {
  weights: RewardWeights;
  /** Max number of new stops to place (upper bound; greedy may stop early). */
  budget: number;
  region?: string;
  seed?: number;
}

/** Map the chat's camelCase weights to the backend RewardSpec field names. */
function toRewardSpec(p: RunOptimizerParams) {
  return {
    coverage_weight: p.weights.coverage,
    travel_weight: p.weights.travelTime,
    equity_weight: p.weights.equity,
    constraint_weight: p.weights.constraints,
    region: p.region ?? "Toronto",
    budget: p.budget,
    protect: null,
  };
}

/** Run the optimizer and return its layout + per-step trajectory. */
export async function runOptimizer(p: RunOptimizerParams): Promise<OptResult> {
  const res = await fetch("/api/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reward_spec: toRewardSpec(p), seed: p.seed ?? 42 }),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.error) detail = body.error;
    } catch {
      /* keep status-only detail */
    }
    throw new Error(`Optimizer request failed (${detail})`);
  }
  return res.json();
}
