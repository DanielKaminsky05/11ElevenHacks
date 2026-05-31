"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CATEGORY_META,
  MAGNITUDE_COLOR,
  loadEvents,
  type CityEvent,
} from "@/lib/events";

type FilterKey = "all" | "closure" | "demand";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "closure", label: "Disruptions" },
  { key: "demand", label: "Crowds" },
];

/** Format an ISO datetime as a compact local date (e.g. "Jun 12"). */
function shortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-CA", { month: "short", day: "numeric" });
}

/** "Jun 12" or "Jun 12 – Jul 19" when the window spans multiple days. */
function dateRange(start: string, end: string): string {
  const s = shortDate(start);
  const e = shortDate(end);
  return s === e ? s : `${s} – ${e}`;
}

/**
 * News feed of upcoming city events that perturb transit — road/line closures
 * (supply disruptions) and big draws like matches and festivals (demand
 * surges). Docked top-left as a collapsible panel; filterable.
 */
export function NewsFeed() {
  const [open, setOpen] = useState(true);
  const [events, setEvents] = useState<CityEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    let cancelled = false;
    loadEvents()
      .then((res) => {
        if (!cancelled) setEvents(res.events);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const shown = useMemo(() => {
    if (!events) return [];
    if (filter === "closure")
      return events.filter((e) => e.kind === "supply_disruption");
    if (filter === "demand")
      return events.filter((e) => e.kind === "demand_surge");
    return events;
  }, [events, filter]);

  const disruptions = events?.filter((e) => e.kind === "supply_disruption").length ?? 0;

  // Docked on the left rail, below the map legend (which occupies the top-left
  // corner). The legend is fixed-height, so a fixed top offset stacks cleanly.
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pointer-events-auto absolute left-4 top-[244px] z-10 flex items-center gap-2 rounded-full border border-sky-400/30 bg-[#0c1628]/90 px-3.5 py-2 text-[13px] font-medium text-[#dce6f5] shadow-2xl backdrop-blur-md hover:bg-[#13233f]"
      >
        📰 Service alerts
        {disruptions > 0 && (
          <span className="rounded-full bg-rose-500/80 px-1.5 text-[11px] font-semibold text-white">
            {disruptions}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="pointer-events-auto absolute left-4 top-[244px] z-10 flex max-h-[calc(100vh-264px)] w-[300px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-sky-400/25 bg-[#0c1628]/90 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-none items-center justify-between border-b border-sky-400/15 px-4 py-2.5">
        <div>
          <div className="text-[14px] font-semibold text-white">Service alerts &amp; events</div>
          <div className="text-[11px] text-[#7e93b5]">Upcoming activity affecting transit</div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Minimize news feed"
          className="rounded p-1 text-[#9fb4d6] hover:bg-white/10 hover:text-white"
        >
          ▾
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-none gap-1.5 px-3.5 py-2">
        {FILTERS.map((f) => (
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

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
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
    </div>
  );
}

function EventCard({ event }: { event: CityEvent }) {
  const meta = CATEGORY_META[event.category];
  const color = MAGNITUDE_COLOR[event.impact.magnitude];
  const isDisruption = event.kind === "supply_disruption";
  const lines = event.impact.affected_lines;

  return (
    <li
      className="rounded-lg border-l-2 bg-white/[0.03] px-3 py-2"
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-[14px] leading-none">{meta.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-medium leading-snug text-[#eaf2ff]">
            {event.title}
          </div>
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
                <span
                  key={l}
                  className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-200"
                >
                  {l}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
