// Shared types + client for the planner chat.
//
// The planner turns a plain-English transit goal into (a) reward weights for the
// RL agent and (b) a human-readable reply. The real implementation will call the
// open model + RL backend; until that exists, /api/chat returns a structured
// stub so the UI is fully functional and the contract is fixed.

/** Chat roles. "system" notices (e.g. errors) render distinctly. */
export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** Reward weights the planner inferred from the goal (assistant only). */
  weights?: RewardWeights;
  createdAt: number;
}

/** The four reward channels the RL agent optimizes (see project-idea.md). */
export interface RewardWeights {
  coverage: number;
  travelTime: number;
  equity: number;
  constraints: number;
}

export interface PlannerRequest {
  goal: string;
  history: { role: ChatRole; content: string }[];
}

export interface PlannerResponse {
  reply: string;
  weights: RewardWeights;
}

/** Example goals shown as one-tap prompts for first-time planners. */
export const EXAMPLE_GOALS = [
  "Improve access for low-income neighbourhoods in Scarborough without increasing downtown commute times.",
  "Close the biggest transit coverage gaps for seniors.",
  "Prioritize equity for the most marginalized neighbourhoods.",
  "Maximize how many jobs people can reach by transit.",
];

/** POST a goal to the planner endpoint and return its structured reply. */
export async function sendPlannerGoal(req: PlannerRequest): Promise<PlannerResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`Planner request failed (HTTP ${res.status})`);
  }
  return res.json();
}
