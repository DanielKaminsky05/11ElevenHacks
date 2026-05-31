// Conversational agent endpoint — proxies the browser to the backend's
// tool-calling agent (POST /chat). Unlike /api/chat (the planner: goal -> reward
// weights for the map), this answers Toronto transit *questions* by calling tools
// and grounding every figure in real data, and returns the answer plus the tool
// trace (so the UI can show "via profile_area" provenance, or react to a step).
//
// Backend URL comes from BACKEND_URL (server-only env), same as /api/chat.

import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:9001";

/** One executed tool call in the agent's trace (mirrors backend ChatStep). */
export interface AgentStep {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface AgentResponse {
  reply: string;
  steps: AgentStep[];
}

export async function POST(request: Request) {
  let body: { message?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const message = (body?.message ?? "").trim();
  if (!message) {
    return NextResponse.json({ error: "Missing message" }, { status: 400 });
  }

  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      // The agent loop may run several tool turns; allow generous time.
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `backend returned ${res.status}` },
        { status: 502 },
      );
    }
    return NextResponse.json((await res.json()) as AgentResponse);
  } catch {
    return NextResponse.json(
      { error: "TransitRL backend unreachable" },
      { status: 502 },
    );
  }
}
