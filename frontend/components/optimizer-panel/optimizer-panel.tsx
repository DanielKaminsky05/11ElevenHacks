"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RewardWeights } from "@/lib/planner";
import { runOptimizer, type OptResult } from "@/lib/optimizer";
import { emitMapCommand, subscribeMapCommand } from "@/lib/map-bus";

const DEFAULT_WEIGHTS: RewardWeights = {
  coverage: 0.4,
  travelTime: 0.2,
  equity: 0.3,
  constraints: 0.1,
};

const CHANNELS: [keyof RewardWeights, string, string][] = [
  ["coverage", "Coverage", "#38bdf8"],
  ["travelTime", "Travel time", "#a78bfa"],
  ["equity", "Equity", "#f472b6"],
  ["constraints", "Constraints", "#fbbf24"],
];

const SCORE_ROWS: [keyof OptResult["channel_scores"], string, string][] = [
  ["coverage", "Coverage", "#38bdf8"],
  ["travel", "Travel time", "#a78bfa"],
  ["equity", "Equity", "#f472b6"],
  ["constraint", "Constraints", "#fbbf24"],
];

/**
 * Optimizer panel: drive the stop-placement optimizer live. Sliders set the four
 * reward weights; "Find best layout" (and every slider release) re-runs greedy +
 * local search on the backend and animates the recommended stops onto the map.
 * Seeds itself from the planner chat's inferred weights and runs automatically.
 */
export function OptimizerPanel() {
  const [open, setOpen] = useState(false);
  const [weights, setWeights] = useState<RewardWeights>(DEFAULT_WEIGHTS);
  const [budget, setBudget] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptResult | null>(null);

  // Monotonic request id so a slow earlier run can't overwrite a newer one.
  const runSeq = useRef(0);

  const run = useCallback(
    async (w: RewardWeights, b: number) => {
      const seq = ++runSeq.current;
      setLoading(true);
      setError(null);
      try {
        const res = await runOptimizer({ weights: w, budget: b });
        if (seq !== runSeq.current) return; // superseded by a newer run
        setResult(res);
        emitMapCommand({ type: "optimizerResult", steps: res.steps });
      } catch (err) {
        if (seq !== runSeq.current) return;
        setError(err instanceof Error ? err.message : "Optimizer failed");
      } finally {
        if (seq === runSeq.current) setLoading(false);
      }
    },
    [],
  );

  // When the planner chat infers weights, seed the sliders, open, and auto-run.
  useEffect(() => {
    return subscribeMapCommand((cmd) => {
      if (cmd.type !== "applyPlan") return;
      setWeights(cmd.weights);
      setOpen(true);
      void run(cmd.weights, budget);
    });
  }, [run, budget]);

  function setWeight(key: keyof RewardWeights, value: number) {
    setWeights((prev) => ({ ...prev, [key]: value }));
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pointer-events-auto absolute bottom-4 left-4 z-20 rounded-full border border-sky-400/30 bg-[#0c1628]/90 px-4 py-2.5 text-[13px] font-medium text-[#dce6f5] shadow-2xl backdrop-blur-md hover:bg-[#13233f]"
      >
        🎯 Optimize stops
      </button>
    );
  }

  return (
    <div className="pointer-events-auto absolute bottom-4 left-4 z-20 flex w-[320px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-sky-400/25 bg-[#0c1628]/92 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-sky-400/15 px-4 py-2.5">
        <div>
          <div className="text-[14px] font-semibold text-white">Stop Optimizer</div>
          <div className="text-[11px] text-[#7e93b5]">
            Weight the goals; stops re-solve live
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Minimize optimizer"
          className="rounded p-1 text-[#9fb4d6] hover:bg-white/10 hover:text-white"
        >
          ▾
        </button>
      </div>

      <div className="space-y-3 px-4 py-3">
        {/* Weight sliders */}
        <div className="space-y-2.5">
          {CHANNELS.map(([key, label, color]) => (
            <div key={key} className="flex items-center gap-2.5 text-[11.5px]">
              <span className="w-[68px] flex-none text-[#9fb4d6]">{label}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={weights[key]}
                onChange={(e) => setWeight(key, Number(e.target.value))}
                onPointerUp={() => run(weights, budget)}
                onKeyUp={() => run(weights, budget)}
                className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-white/10 accent-sky-400"
                style={{ accentColor: color }}
                aria-label={`${label} weight`}
              />
              <span className="w-8 flex-none text-right tabular-nums text-[#cdd9ee]">
                {weights[key].toFixed(2)}
              </span>
            </div>
          ))}
        </div>

        {/* Budget */}
        <div className="flex items-center gap-2.5 border-t border-white/10 pt-2.5 text-[11.5px]">
          <span className="w-[68px] flex-none text-[#9fb4d6]">New stops</span>
          <input
            type="range"
            min={1}
            max={15}
            step={1}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            onPointerUp={() => run(weights, budget)}
            onKeyUp={() => run(weights, budget)}
            className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-white/10"
            style={{ accentColor: "#7dd3fc" }}
            aria-label="Stop budget"
          />
          <span className="w-8 flex-none text-right tabular-nums text-[#cdd9ee]">
            {budget}
          </span>
        </div>

        {/* Run button */}
        <button
          type="button"
          onClick={() => run(weights, budget)}
          disabled={loading}
          className="w-full rounded-lg bg-sky-500 px-3 py-2 text-[12.5px] font-medium text-white transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-sky-500/30 disabled:text-white/50"
        >
          {loading ? "Optimizing…" : "Find best layout"}
        </button>

        {error && (
          <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11.5px] text-rose-200">
            {error}
          </div>
        )}

        {result && !error && (
          <div className="space-y-1.5 border-t border-white/10 pt-2.5">
            <div className="flex items-baseline justify-between">
              <span className="text-[10px] uppercase tracking-[0.5px] text-[#9fb4d6]">
                Result
              </span>
              <span className="text-[11px] text-[#cdd9ee]">
                {result.stops.length} stop{result.stops.length === 1 ? "" : "s"}
                {result.stopped_reason === "diminishing_returns" && (
                  <span className="text-[#7e93b5]"> · capped by per-stop cost</span>
                )}
              </span>
            </div>
            {SCORE_ROWS.map(([key, label, color]) => (
              <div key={key} className="flex items-center gap-2 text-[10.5px]">
                <span className="w-[68px] flex-none text-[#9fb4d6]">{label}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                  <span
                    className="block h-full rounded-full"
                    style={{
                      width: `${Math.round(result.channel_scores[key] * 100)}%`,
                      background: color,
                    }}
                  />
                </span>
                <span className="w-8 flex-none text-right tabular-nums text-[#cdd9ee]">
                  {Math.round(result.channel_scores[key] * 100)}%
                </span>
              </div>
            ))}
            <div className="pt-0.5 text-[10px] text-[#7e93b5]">
              % of the best a {result.budget}-stop budget could capture.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
