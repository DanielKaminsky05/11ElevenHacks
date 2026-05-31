"use client";

import { useEffect, useRef, useState } from "react";
import {
  EXAMPLE_GOALS,
  sendPlannerGoal,
  type ChatMessage,
} from "@/lib/planner";
import { emitMapCommand } from "@/lib/map-bus";

let _idSeq = 0;
const nextId = () => `m${Date.now()}-${_idSeq++}`;

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
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, pending]);

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
      .filter((m) => m.role !== "system")
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setPending(true);

    try {
      const res = await sendPlannerGoal({ goal: text, history });
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: res.reply,
          weights: res.weights,
          createdAt: Date.now(),
        },
      ]);
      // Drive the map: switch to the implied view + focus the priority areas.
      emitMapCommand({ type: "applyPlan", weights: res.weights, goal: text });
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

        {pending && (
          <div className="flex items-center gap-1.5 px-1 text-[12px] text-[#7e93b5]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-300" />
            Planning…
          </div>
        )}

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
        {message.weights && <WeightBars weights={message.weights} />}
      </div>
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
