"use client";

import { useEffect, useRef, useState } from "react";
import {
  EXAMPLE_GOALS,
  sendAgent,
  sendPlannerGoal,
  type ChatMessage,
} from "@/lib/planner";
import { emitMapCommand } from "@/lib/map-bus";

let _idSeq = 0;
const nextId = () => `m${Date.now()}-${_idSeq++}`;

// Human-readable labels for the live "calling <tool>" indicator. Unknown tools
// fall back to their snake_case id with underscores spaced out (toolLabel).
const TOOL_LABELS: Record<string, string> = {
  get_city_grid: "Reading the city grid",
  profile_area: "Profiling the area",
  list_transit: "Listing transit",
  compare_areas: "Comparing areas",
  compute_accessibility: "Computing accessibility",
  equity_gap_report: "Analyzing equity gaps",
  reachability: "Tracing reachability",
  estimate_demand: "Estimating demand",
  reliability_report: "Checking reliability",
  simulate_change: "Simulating the change",
  diff_scenarios: "Diffing scenarios",
  constraint_check: "Checking constraints",
  parse_goal: "Parsing the goal",
  optimize_layout: "Optimizing stop layout",
  propose_candidates: "Proposing stops",
  optimization_status: "Reading optimizer status",
  who_is_affected: "Finding who's affected",
  explain_result: "Explaining the result",
  generate_brief: "Writing the brief",
  find_upcoming_events: "Finding events",
  get_event: "Loading the event",
};

const toolLabel = (tool: string) =>
  TOOL_LABELS[tool] ?? tool.replace(/_/g, " ");

// Tools whose presence in the agent's trace mean the answer is an actual *plan*
// (a stop layout / scenario). Only then are reward weights and the map's
// "apply plan" command relevant — lookups and diagnostic questions shouldn't
// show weight bars or yank the map view/filters around.
const PLAN_TOOLS = new Set([
  "optimize_layout",
  "propose_candidates",
  "simulate_change",
]);

const GREETING: ChatMessage = {
  id: "greeting",
  role: "assistant",
  content:
    "Describe a transit goal in plain language and I'll translate it into a " +
    "plan — which neighbourhoods to prioritize and how to weigh coverage, " +
    "travel time, and equity. Try one of the examples below to start.",
  createdAt: 0,
};

/**
 * Planner chat panel. A docked, collapsible conversation where a planner types
 * a goal in plain English; the /api/chat endpoint returns a reply + inferred
 * reward weights. Designed to sit over the map (bottom-right).
 */
export function PlannerChat() {
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  // The tool the agent is calling right now (shown live with a spinner), or null.
  const [liveTool, setLiveTool] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, pending, liveTool]);

  async function submitGoal(goal: string) {
    const text = goal.trim();
    if (!text || pending) return;

    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    const history = messages
      .filter((m): m is ChatMessage & { role: "user" | "assistant" } =>
        m.role !== "system",
      )
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setPending(true);

    try {
      // Ask the grounded agent (real answer + tool trace) and the planner
      // (reward weights that drive the map) in parallel — neither blocks the other.
      // The agent streams its tool calls; surface the in-flight one live.
      const [agentRes, plannerRes] = await Promise.allSettled([
        sendAgent(text, history, (event) => {
          if (event.type === "tool") setLiveTool(event.tool);
          else if (event.type === "done") setLiveTool(null);
        }),
        sendPlannerGoal({ goal: text, history }),
      ]);

      const weights =
        plannerRes.status === "fulfilled" ? plannerRes.value.weights : undefined;

      let content: string;
      let steps: ChatMessage["steps"];
      // Reward weights + the map "apply plan" command only make sense when the
      // answer is an actual plan; gate on whether a planning tool was run.
      let isPlan = false;
      if (agentRes.status === "fulfilled" && agentRes.value.reply.trim()) {
        // Preferred: the grounded, tool-backed answer.
        content = agentRes.value.reply.trim();
        steps = agentRes.value.steps;
        isPlan = steps.some((s) => PLAN_TOOLS.has(s.tool));
      } else if (plannerRes.status === "fulfilled") {
        // Agent failed — fall back to the planner's reward-weight summary.
        content = plannerRes.value.reply;
        isPlan = true;
      } else {
        throw agentRes.status === "rejected"
          ? agentRes.reason
          : new Error("The planner is unavailable. Try again.");
      }

      // Attach weights only for plans, so lookups/questions don't render bars.
      const planWeights = isPlan ? weights : undefined;
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content,
          weights: planWeights,
          steps,
          createdAt: Date.now(),
        },
      ]);
      // Only drive the map for an actual plan — don't switch the view/filters
      // for ordinary questions.
      if (isPlan && planWeights) {
        emitMapCommand({ type: "applyPlan", weights: planWeights, goal: text });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "system",
          content:
            err instanceof Error ? err.message : "Something went wrong. Try again.",
          createdAt: Date.now(),
        },
      ]);
    } finally {
      setPending(false);
      setLiveTool(null);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    submitGoal(input);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pointer-events-auto absolute bottom-4 right-4 z-20 rounded-full border border-sky-400/30 bg-[#0c1628]/90 px-4 py-2.5 text-[13px] font-medium text-[#dce6f5] shadow-2xl backdrop-blur-md hover:bg-[#13233f]"
      >
        💬 Ask the planner
      </button>
    );
  }

  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 z-20 flex h-[460px] w-[360px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-sky-400/25 bg-[#0c1628]/92 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-sky-400/15 px-4 py-2.5">
        <div>
          <div className="text-[14px] font-semibold text-white">Transit Planner</div>
          <div className="text-[11px] text-[#7e93b5]">Describe a goal in plain language</div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Minimize planner"
          className="rounded p-1 text-[#9fb4d6] hover:bg-white/10 hover:text-white"
        >
          ▾
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-3.5 py-3">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}

        {pending &&
          (liveTool ? (
            <div className="flex items-center gap-2 px-1 text-[12px] text-[#9fb4d6]">
              <span className="h-3.5 w-3.5 flex-none animate-spin rounded-full border-2 border-sky-300/25 border-t-sky-300" />
              <span>
                Calling{" "}
                <span className="font-medium text-sky-200">
                  {toolLabel(liveTool)}
                </span>
                …
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-1 text-[12px] text-[#7e93b5]">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-300" />
              Planning…
            </div>
          ))}

        {messages.length <= 1 && !pending && (
          <div className="space-y-1.5 pt-1">
            {EXAMPLE_GOALS.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => submitGoal(g)}
                className="block w-full rounded-lg border border-sky-400/20 bg-white/[0.03] px-3 py-2 text-left text-[12px] leading-snug text-[#b6c6e0] hover:border-sky-400/40 hover:bg-white/[0.07]"
              >
                {g}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} className="border-t border-sky-400/15 p-2.5">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitGoal(input);
              }
            }}
            rows={1}
            placeholder="e.g. Improve access in Scarborough…"
            className="max-h-24 flex-1 resize-none rounded-lg border border-sky-400/25 bg-[#0a1628] px-3 py-2 text-[12.5px] text-[#e6eefb] placeholder:text-[#52688a] focus:border-sky-400/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={pending || !input.trim()}
            className="rounded-lg bg-sky-500 px-3 py-2 text-[12.5px] font-medium text-white transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-sky-500/30 disabled:text-white/50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "system") {
    return (
      <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
        {message.content}
      </div>
    );
  }

  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-2xl rounded-br-sm bg-sky-500/90 px-3 py-2 text-[12.5px] leading-snug text-white"
            : "max-w-[88%] rounded-2xl rounded-bl-sm bg-white/[0.06] px-3 py-2 text-[12.5px] leading-snug text-[#dce6f5]"
        }
      >
        {message.content}
        {message.steps && message.steps.length > 0 && (
          <ToolTrace steps={message.steps} />
        )}
        {message.weights && <WeightBars weights={message.weights} />}
      </div>
    </div>
  );
}

function ToolTrace({ steps }: { steps: NonNullable<ChatMessage["steps"]> }) {
  const tools = Array.from(new Set(steps.map((s) => s.tool)));
  if (tools.length === 0) return null;
  return (
    <div className="mt-2 border-t border-white/10 pt-1.5 text-[10px] text-[#7e93b5]">
      <span className="uppercase tracking-[0.5px]">grounded via</span>{" "}
      <span className="text-[#9fb4d6]">{tools.join(" · ")}</span>
    </div>
  );
}

function WeightBars({ weights }: { weights: NonNullable<ChatMessage["weights"]> }) {
  const rows: [string, number, string][] = [
    ["Coverage", weights.coverage, "#38bdf8"],
    ["Travel time", weights.travelTime, "#a78bfa"],
    ["Equity", weights.equity, "#f472b6"],
    ["Constraints", weights.constraints, "#fbbf24"],
  ];
  return (
    <div className="mt-2 space-y-1 border-t border-white/10 pt-2">
      <div className="text-[10px] uppercase tracking-[0.5px] text-[#9fb4d6]">
        Reward weights
      </div>
      {rows.map(([label, value, color]) => (
        <div key={label} className="flex items-center gap-2 text-[10.5px]">
          <span className="w-[68px] flex-none text-[#9fb4d6]">{label}</span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
            <span
              className="block h-full rounded-full"
              style={{ width: `${Math.round(value * 100)}%`, background: color }}
            />
          </span>
          <span className="w-7 flex-none text-right tabular-nums text-[#cdd9ee]">
            {value.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
}
