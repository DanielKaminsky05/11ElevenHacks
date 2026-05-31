// Conversational agent endpoint — proxies the browser to the backend's
// tool-calling agent (POST /chat/stream). Unlike /api/chat (the planner: goal ->
// reward weights for the map), this answers Toronto transit *questions* by calling
// tools and grounding every figure in real data.
//
// It streams the backend's Server-Sent Events straight through: a `tool` event the
// moment the model calls each tool (so the UI shows the call live), then a final
// `done` event with the answer + full step trace.
//
// Backend URL comes from BACKEND_URL (server-only env), same as /api/chat.

import { NextResponse } from "next/server";

// SSE must not be statically cached or buffered — render per request.
export const dynamic = "force-dynamic";

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

/** A prior turn, replayed to the backend so the agent has conversation memory. */
export interface AgentTurn {
  role: "user" | "assistant";
  content: string;
}

export async function POST(request: Request) {
  let body: { message?: string; history?: AgentTurn[] };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const message = (body?.message ?? "").trim();
  if (!message) {
    return NextResponse.json({ error: "Missing message" }, { status: 400 });
  }

  // Forward only well-formed {role, content} turns; drop anything else so a
  // malformed client can't 422 the backend's Pydantic validation.
  const history: AgentTurn[] = Array.isArray(body?.history)
    ? body.history
        .filter(
          (t): t is AgentTurn =>
            !!t &&
            (t.role === "user" || t.role === "assistant") &&
            typeof t.content === "string",
        )
        .map((t) => ({ role: t.role, content: t.content }))
    : [];

  try {
    const res = await fetch(`${BACKEND_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
      // The agent loop may run several tool turns; allow generous time.
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok || !res.body) {
      return NextResponse.json(
        { error: `backend returned ${res.status}` },
        { status: 502 },
      );
    }
    // Pipe the SSE stream straight through to the browser, unbuffered.
    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "TransitRL backend unreachable" },
      { status: 502 },
    );
  }
}
