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
  /** Tool-call trace from the grounded agent (assistant only). */
  steps?: AgentStep[];
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

/** One executed tool call in the agent's trace (mirrors the backend ChatStep). */
export interface AgentStep {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface AgentResponse {
  reply: string;
  steps: AgentStep[];
}

/**
 * A streamed event from the agent loop (mirrors the backend's SSE payloads):
 * one `tool` event the moment the model calls each tool (so the UI can show it
 * live), then a final `done` event with the answer + full trace.
 */
export type AgentEvent =
  | { type: "tool"; tool: string; arguments: Record<string, unknown> }
  | { type: "done"; reply: string; steps: AgentStep[] };

/**
 * Ask the grounded tool-calling agent (Nemotron) a question. Unlike
 * sendPlannerGoal — which only returns reward weights — this returns a real
 * answer grounded in tool results, plus the tool trace. Hits /api/agent, which
 * proxies the backend's POST /chat/stream loop as Server-Sent Events.
 *
 * `onEvent` fires for each streamed event as it arrives (use the `tool` events
 * to show calls live); the promise still resolves with the final answer + trace.
 */
export async function sendAgent(
  message: string,
  history: { role: "user" | "assistant"; content: string }[] = [],
  onEvent?: (event: AgentEvent) => void,
): Promise<AgentResponse> {
  const res = await fetch("/api/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Agent request failed (HTTP ${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: AgentResponse | null = null;

  // Parse the SSE byte stream into "data: {json}\n\n" frames as they arrive.
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("");
      if (!data) continue;
      let event: AgentEvent;
      try {
        event = JSON.parse(data) as AgentEvent;
      } catch {
        continue; // ignore a malformed frame rather than failing the turn
      }
      if (event.type === "done") final = { reply: event.reply, steps: event.steps };
      onEvent?.(event);
    }
  }

  if (!final) {
    throw new Error("Agent stream ended without a final answer");
  }
  return final;
}
