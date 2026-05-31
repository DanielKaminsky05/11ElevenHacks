"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MODE, STOP_COLOR } from "@/lib/transit";
import {
  CATEGORY_META,
  MAGNITUDE_COLOR,
  loadEvents,
  type CityEvent,
} from "@/lib/events";
<<<<<<< HEAD
import { emitMapCommand } from "@/lib/map-bus";
=======
import type { RewardWeights } from "@/lib/planner";
import { runOptimizer, type OptResult } from "@/lib/optimizer";
import { emitMapCommand, subscribeMapCommand } from "@/lib/map-bus";
>>>>>>> origin/main
import type { LayerKey, LegendState } from "./map-legend";
import type { ViewModule, LegendSpec } from "./views/types";

type TabId = "network" | "data" | "alerts" | "optimize";

const DEFAULT_WEIGHTS: RewardWeights = {
  coverage: 0.4,
  travelTime: 0.2,
  equity: 0.3,
  constraints: 0.1,
};

const OPT_CHANNELS: [keyof RewardWeights, string, string][] = [
  ["coverage", "Coverage", "#38bdf8"],
  ["travelTime", "Travel time", "#a78bfa"],
  ["equity", "Equity", "#f472b6"],
  ["constraints", "Constraints", "#fbbf24"],
];

const OPT_SCORE_ROWS: [keyof OptResult["channel_scores"], string, string][] = [
  ["coverage", "Coverage", "#38bdf8"],
  ["travel", "Travel time", "#a78bfa"],
  ["equity", "Equity", "#f472b6"],
  ["constraint", "Constraints", "#fbbf24"],
];

interface ControlPanelProps {
  // Network tab
  status: string;
  visibility: LegendState;
  counts: Record<LayerKey, number>;
  onToggle: (key: LayerKey) => void;
  // Data tab
  views: ViewModule[];
  activeViewId: string | null;
  activeOption: string | null;
  onSelectView: (id: string | null) => void;
  onOption: (optionId: string) => void;
  viewLegend: LegendSpec | null;
}

/**
 * Unified top-right control modal. One panel with an icon tab rail that switches
 * between three sections — Network layers, Data views, and Service alerts —
 * replacing the three separate floating panels. Collapses to a single button.
 */
export function ControlPanel(props: ControlPanelProps) {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<TabId>("network");

  // Alerts are loaded once here so the badge shows even on other tabs.
  const [events, setEvents] = useState<CityEvent[] | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadEvents()
      .then((res) => !cancelled && setEvents(res.events))
      .catch((e) => !cancelled && setEventsError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      cancelled = true;
    };
  }, []);

  const disruptions = useMemo(
    () => events?.filter((e) => e.kind === "supply_disruption").length ?? 0,
    [events],
  );

  // --- Optimize tab state: drive the stop-placement optimizer live. ---
  const [weights, setWeights] = useState<RewardWeights>(DEFAULT_WEIGHTS);
  const [budget, setBudget] = useState(8);
  const [optLoading, setOptLoading] = useState(false);
  const [optError, setOptError] = useState<string | null>(null);
  const [optResult, setOptResult] = useState<OptResult | null>(null);
  // Monotonic id so a slow earlier run can't overwrite a newer one.
  const runSeq = useRef(0);

  const runOpt = useCallback(async (w: RewardWeights, b: number) => {
    const seq = ++runSeq.current;
    setOptLoading(true);
    setOptError(null);
    try {
      const res = await runOptimizer({ weights: w, budget: b });
      if (seq !== runSeq.current) return; // superseded by a newer run
      setOptResult(res);
      emitMapCommand({ type: "optimizerResult", steps: res.steps });
    } catch (err) {
      if (seq !== runSeq.current) return;
      setOptError(err instanceof Error ? err.message : "Optimizer failed");
    } finally {
      if (seq === runSeq.current) setOptLoading(false);
    }
  }, []);

  // When the planner chat infers weights, open the Optimize tab, seed the
  // sliders, and auto-run so the recommended stops animate onto the map.
  useEffect(() => {
    return subscribeMapCommand((cmd) => {
      if (cmd.type !== "applyPlan") return;
      setWeights(cmd.weights);
      setOpen(true);
      setTab("optimize");
      void runOpt(cmd.weights, budget);
    });
  }, [runOpt, budget]);

  function setWeight(key: keyof RewardWeights, value: number) {
    setWeights((prev) => ({ ...prev, [key]: value }));
  }

  const TABS: { id: TabId; label: string; icon: React.ReactNode; badge?: number }[] = [
    { id: "network", label: "Network", icon: <NetworkIcon /> },
    { id: "data", label: "Data", icon: <DataIcon /> },
    { id: "optimize", label: "Optimize", icon: <OptimizeIcon /> },
    { id: "alerts", label: "Alerts", icon: <AlertIcon />, badge: disruptions },
  ];

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open controls"
        className="pointer-events-auto absolute right-3.5 top-3.5 z-10 flex h-10 w-10 items-center justify-center rounded-xl border border-sky-400/30 bg-[#0c1628]/90 text-[#dce6f5] shadow-2xl backdrop-blur-md hover:bg-[#13233f]"
      >
        <DataIcon />
        {disruptions > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
            {disruptions}
          </span>
        )}
      </button>
    );
  }

  const activeLabel = TABS.find((t) => t.id === tab)?.label ?? "";

  return (
    <div className="pointer-events-auto absolute right-3.5 top-3.5 z-10 flex max-h-[calc(100vh-2rem)] w-[300px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-sky-400/25 bg-[#0c1628]/90 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Title bar */}
      <div className="flex flex-none items-center justify-between border-b border-sky-400/15 px-4 pb-2 pt-3">
        <div>
          <div className="text-[14px] font-semibold leading-none text-white">TransitRL</div>
          <div className="mt-1 text-[11px] text-[#7e93b5]">{activeLabel}</div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Collapse panel"
          className="rounded p-1 text-[#9fb4d6] hover:bg-white/10 hover:text-white"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* Icon tab rail */}
      <div className="flex flex-none gap-1 border-b border-sky-400/15 px-2 py-2">
        {TABS.map((t) => {
          const on = t.id === tab;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              aria-pressed={on}
              title={t.label}
              className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] font-medium transition-colors ${
                on
                  ? "bg-sky-500/25 text-white"
                  : "text-[#9fb4d6] hover:bg-white/[0.06] hover:text-white"
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
              {t.badge ? (
                <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500/90 px-1 text-[10px] font-semibold text-white">
                  {t.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "network" && <NetworkTab {...props} />}
        {tab === "data" && <DataTab {...props} />}
        {tab === "optimize" && (
          <OptimizeTab
            weights={weights}
            budget={budget}
            loading={optLoading}
            error={optError}
            result={optResult}
            onWeight={setWeight}
            onBudget={setBudget}
            onRun={() => runOpt(weights, budget)}
          />
        )}
        {tab === "alerts" && (
          <AlertsTab events={events} error={eventsError} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network tab — route layer toggles + status
// ---------------------------------------------------------------------------

const LAYER_ITEMS: { key: LayerKey; label: string; color: string; dot?: boolean }[] = [
  { key: "subway", label: MODE.subway.label, color: MODE.subway.color },
  { key: "streetcar", label: MODE.streetcar.label, color: MODE.streetcar.color },
  { key: "bus", label: MODE.bus.label, color: MODE.bus.color },
  { key: "busstops", label: "Bus stops", color: STOP_COLOR, dot: true },
];

function NetworkTab({
  status,
  visibility,
  counts,
  onToggle,
}: Pick<ControlPanelProps, "status" | "visibility" | "counts" | "onToggle">) {
  return (
    <div>
      <div className="mb-3 text-[12px] text-[#9fb4d6]">{status}</div>
      <div className="mb-1.5 text-[10px] uppercase tracking-[1px] text-[#6f86ab]">Layers</div>
      <ul>
        {LAYER_ITEMS.map((item) => {
          const on = visibility[item.key];
          return (
            <li key={item.key}>
              <button
                type="button"
                onClick={() => onToggle(item.key)}
                aria-pressed={on}
                className={`flex w-full items-center gap-2.5 py-1 text-[13px] transition-opacity ${
                  on ? "opacity-100" : "opacity-35"
                }`}
              >
                <span
                  aria-hidden
                  className={
                    item.dot
                      ? "h-2.5 w-2.5 flex-none rounded-full"
                      : "h-1 w-[22px] flex-none rounded-sm"
                  }
                  style={{ background: item.color, boxShadow: `0 0 7px ${item.color}` }}
                />
                <span>{item.label}</span>
                <span className="ml-auto text-[11px] text-[#6f86ab]">
                  {counts[item.key].toLocaleString()}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data tab — view switcher (choropleths) + sub-metric + legend
// ---------------------------------------------------------------------------

function DataTab({
  views,
  activeViewId,
  activeOption,
  onSelectView,
  onOption,
  viewLegend,
}: Pick<
  ControlPanelProps,
  "views" | "activeViewId" | "activeOption" | "onSelectView" | "onOption" | "viewLegend"
>) {
  const groups = Array.from(new Set(views.map((v) => v.group)));
  const active = views.find((v) => v.id === activeViewId) ?? null;

  return (
    <div>
      <label className="flex items-center gap-2 py-1 text-[13px]">
        <input
          type="radio"
          name="view"
          checked={activeViewId === null}
          onChange={() => onSelectView(null)}
        />
        Network only
      </label>

      {groups.map((group) => (
        <div key={group} className="mt-2">
          <div className="mb-0.5 text-[10px] uppercase tracking-[1px] text-[#52688a]">
            {group}
          </div>
          {views
            .filter((v) => v.group === group)
            .map((v) => (
              <label
                key={v.id}
                className="flex items-center gap-2 py-1 text-[13px]"
                title={v.description}
              >
                <input
                  type="radio"
                  name="view"
                  checked={activeViewId === v.id}
                  onChange={() => onSelectView(v.id)}
                />
                {v.label}
              </label>
            ))}
        </div>
      ))}

      {active && (
        <div className="mt-3 border-t border-sky-400/15 pt-3">
          <div className="mb-2 text-[11.5px] leading-snug text-[#9fb4d6]">
            {active.description}
          </div>

          {active.options && active.options.length > 0 && (
            <>
              <select
                value={activeOption ?? active.options[0].id}
                onChange={(e) => onOption(e.target.value)}
                className="w-full rounded-md border border-sky-400/25 bg-[#0a1628] px-2 py-1 text-[12.5px] text-[#dce6f5]"
              >
                {active.options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
              {(() => {
                const current =
                  active.options.find((o) => o.id === activeOption) ?? active.options[0];
                return current.description ? (
                  <p className="mt-1.5 mb-2 text-[11px] leading-snug text-[#8aa0c4]">
                    {current.description}
                  </p>
                ) : (
                  <div className="mb-2" />
                );
              })()}
            </>
          )}

          {viewLegend && <LegendView spec={viewLegend} />}
        </div>
      )}
    </div>
  );
}

function LegendView({ spec }: { spec: LegendSpec }) {
  return (
    <div className="text-[12px]">
      <div className="mb-1 font-medium text-[#cdd9ee]">{spec.title}</div>

      {spec.ramp && (
        <div>
          <div
            className="h-2.5 w-full rounded-sm"
            style={{
              background: `linear-gradient(90deg, ${spec.ramp.colors.join(", ")})`,
            }}
          />
          <div className="mt-0.5 flex justify-between text-[10px] text-[#7e93b5]">
            <span>{spec.ramp.lowLabel}</span>
            <span>{spec.ramp.highLabel}</span>
          </div>
        </div>
      )}

      {spec.rows && (
        <ul className="mt-1 space-y-1">
          {spec.rows.map((r, i) => (
            <li key={i} className="flex items-center gap-2 text-[11.5px]">
              <span
                aria-hidden
                className={
                  r.shape === "line"
                    ? "h-1 w-5 flex-none rounded-sm"
                    : r.shape === "dot"
                      ? "h-2.5 w-2.5 flex-none rounded-full"
                      : "h-3 w-3 flex-none rounded-sm"
                }
                style={{ background: r.color }}
              />
              {r.label}
            </li>
          ))}
        </ul>
      )}

      {spec.note && (
        <div className="mt-1.5 text-[10px] leading-snug text-[#6f86ab]">{spec.note}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alerts tab — service alerts & events feed
// ---------------------------------------------------------------------------

type AlertFilter = "all" | "closure" | "demand";
const ALERT_FILTERS: { key: AlertFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "closure", label: "Disruptions" },
  { key: "demand", label: "Crowds" },
];

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" });
}
function dateRange(start: string, end: string): string {
  const s = shortDate(start);
  const e = shortDate(end);
  return s === e ? s : `${s} – ${e}`;
}

function AlertsTab({
  events,
  error,
}: {
  events: CityEvent[] | null;
  error: string | null;
}) {
  const [filter, setFilter] = useState<AlertFilter>("all");
  const shown = useMemo(() => {
    if (!events) return [];
    if (filter === "closure") return events.filter((e) => e.kind === "supply_disruption");
    if (filter === "demand") return events.filter((e) => e.kind === "demand_surge");
    return events;
  }, [events, filter]);

  return (
    <div>
      <div className="mb-2.5 flex gap-1.5">
        {ALERT_FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`rounded-md px-2.5 py-1 text-[11.5px] transition-colors ${
              filter === f.key
                ? "bg-sky-500/30 text-white"
                : "bg-white/[0.04] text-[#9fb4d6] hover:bg-white/[0.08]"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
          {error}
        </div>
      )}
      {!events && !error && (
        <div className="px-1 py-3 text-[12px] text-[#7e93b5]">Loading alerts…</div>
      )}
      {events && shown.length === 0 && (
        <div className="px-1 py-3 text-[12px] text-[#7e93b5]">No events in this filter.</div>
      )}
      <ul className="space-y-2">
        {shown.map((ev) => (
          <EventCard key={ev.id} event={ev} />
        ))}
      </ul>
    </div>
  );
}

function EventCard({ event }: { event: CityEvent }) {
  const meta = CATEGORY_META[event.category];
  const color = MAGNITUDE_COLOR[event.impact.magnitude];
  const isDisruption = event.kind === "supply_disruption";
  const lines = event.impact.affected_lines;
  const hasLocation = event.venue.lat != null && event.venue.lon != null;

  // Clicking a located event flies the map to it and highlights it.
  function focus() {
    if (!hasLocation) return;
    emitMapCommand({
      type: "focusEvent",
      eventId: event.id,
      lng: event.venue.lon as number,
      lat: event.venue.lat as number,
    });
  }

  return (
    <li
      className={`rounded-lg border-l-2 bg-white/[0.03] px-3 py-2 ${
        hasLocation ? "cursor-pointer hover:bg-white/[0.07]" : ""
      }`}
      style={{ borderLeftColor: color }}
      onClick={focus}
      role={hasLocation ? "button" : undefined}
      tabIndex={hasLocation ? 0 : undefined}
      onKeyDown={(e) => {
        if (hasLocation && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          focus();
        }
      }}
      title={hasLocation ? "Show on map" : undefined}
    >
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-[14px] leading-none">{meta.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-medium leading-snug text-[#eaf2ff]">{event.title}</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[#7e93b5]">
            <span>{dateRange(event.start, event.end)}</span>
            <span>·</span>
            <span className="capitalize">{event.impact.magnitude}</span>
            {event.venue.name && (
              <>
                <span>·</span>
                <span className="truncate">{event.venue.name}</span>
              </>
            )}
          </div>
          {isDisruption && lines.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {lines.slice(0, 4).map((l) => (
                <span key={l} className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-200">
                  {l}
                </span>
              ))}
            </div>
          )}
          {hasLocation && (
            <div className="mt-1 text-[10px] text-sky-300/70">Click to show on map →</div>
          )}
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Optimize tab — reward-weight sliders + budget that re-solve stop placement
// ---------------------------------------------------------------------------

function OptimizeTab({
  weights,
  budget,
  loading,
  error,
  result,
  onWeight,
  onBudget,
  onRun,
}: {
  weights: RewardWeights;
  budget: number;
  loading: boolean;
  error: string | null;
  result: OptResult | null;
  onWeight: (key: keyof RewardWeights, value: number) => void;
  onBudget: (value: number) => void;
  onRun: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="text-[11.5px] leading-snug text-[#9fb4d6]">
        Weight the goals; the optimizer re-solves and animates the recommended
        stops onto the map.
      </div>

      {/* Weight sliders */}
      <div className="space-y-2.5">
        {OPT_CHANNELS.map(([key, label, color]) => (
          <div key={key} className="flex items-center gap-2.5 text-[11.5px]">
            <span className="w-[68px] flex-none text-[#9fb4d6]">{label}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={weights[key]}
              onChange={(e) => onWeight(key, Number(e.target.value))}
              onPointerUp={onRun}
              onKeyUp={onRun}
              className="h-1 flex-1 cursor-pointer"
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
          onChange={(e) => onBudget(Number(e.target.value))}
          onPointerUp={onRun}
          onKeyUp={onRun}
          className="h-1 flex-1 cursor-pointer"
          style={{ accentColor: "#7dd3fc" }}
          aria-label="Stop budget"
        />
        <span className="w-8 flex-none text-right tabular-nums text-[#cdd9ee]">
          {budget}
        </span>
      </div>

      <button
        type="button"
        onClick={onRun}
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
          {OPT_SCORE_ROWS.map(([key, label, color]) => (
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
  );
}

// ---------------------------------------------------------------------------
// Tab icons (inline SVG, 16px)
// ---------------------------------------------------------------------------

function OptimizeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="2" fill="currentColor" />
      <circle cx="8" cy="8" r="5.4" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 .8v2.2M8 13v2.2M.8 8h2.2M13 8h2.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function NetworkIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="3.5" cy="12.5" r="1.6" fill="currentColor" />
      <circle cx="12.5" cy="3.5" r="1.6" fill="currentColor" />
      <path d="M4.6 11.4L11.4 4.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="12.5" cy="12.5" r="1.6" fill="currentColor" />
      <path d="M5 12.5h5.9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function DataIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 1.6L14.4 5 8 8.4 1.6 5 8 1.6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M2.2 8L8 11 13.8 8" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M2.2 11L8 14 13.8 11" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 2a3.2 3.2 0 0 0-3.2 3.2c0 3.4-1.3 4.6-1.3 4.6h9c0 0-1.3-1.2-1.3-4.6A3.2 3.2 0 0 0 8 2z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M6.7 12.2a1.4 1.4 0 0 0 2.6 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}
