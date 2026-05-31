"use client";

import {
  MODE,
  SERVICE_PERIOD,
  deriveSchedule,
  type TransitMode,
} from "@/lib/transit";

/** A route the user has clicked/selected on the map. */
export interface SelectedRoute {
  id: string;
  short: string;
  long: string;
  mode: TransitMode;
  color: string;
  trips: number;
}

interface RouteDetailsProps {
  selected: SelectedRoute[];
  activeId: string | null;
  onSetActive: (id: string) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

const LEVEL_COLOR: Record<string, string> = {
  Frequent: "#34d399",
  Standard: "#38bdf8",
  Infrequent: "#fbbf24",
  Limited: "#f87171",
};

/**
 * Bottom-left panel showing the routes the planner has isolated by clicking
 * lines on the map. Lists each as a removable chip and shows GTFS-derived
 * schedule details for the active one. Hidden entirely when nothing is selected.
 */
export function RouteDetails({
  selected,
  activeId,
  onSetActive,
  onRemove,
  onClear,
}: RouteDetailsProps) {
  if (selected.length === 0) return null;

  const active = selected.find((r) => r.id === activeId) ?? selected[0];
  const sched = deriveSchedule(active.trips);
  const headway =
    sched.headwayMin > 0 && sched.headwayMin <= 90
      ? `≈ every ${sched.headwayMin} min`
      : `≈ ${sched.tripsPerDay}/day`;

  return (
    <div className="pointer-events-auto absolute bottom-4 left-4 z-10 w-[290px] max-w-[calc(100vw-2rem)] rounded-xl border border-sky-400/25 bg-[#0c1628]/90 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Header: count + clear */}
      <div className="flex items-center justify-between border-b border-sky-400/15 px-3.5 py-2">
        <span className="text-[11px] uppercase tracking-[1px] text-[#6f86ab]">
          {selected.length} route{selected.length > 1 ? "s" : ""} isolated
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-[11px] text-[#9fb4d6] hover:text-white"
        >
          Clear
        </button>
      </div>

      {/* Selected chips */}
      {selected.length > 1 && (
        <div className="flex flex-wrap gap-1.5 px-3.5 pt-2.5">
          {selected.map((r) => {
            const on = r.id === active.id;
            return (
              <span
                key={r.id}
                className={`group inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
                  on
                    ? "border-white/40 bg-white/10 text-white"
                    : "border-sky-400/20 bg-white/[0.04] text-[#b6c6e0]"
                }`}
              >
                <button type="button" onClick={() => onSetActive(r.id)} className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: r.color }} />
                  {r.short}
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(r.id)}
                  aria-label={`Remove route ${r.short}`}
                  className="text-[#7e93b5] hover:text-white"
                >
                  ×
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Active route details */}
      <div className="px-3.5 py-3">
        <div className="flex items-start gap-2.5">
          <span
            className="mt-0.5 flex-none rounded-md px-2 py-1 text-[13px] font-bold text-white"
            style={{ background: active.color }}
          >
            {active.short}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-white">{active.long}</div>
            <div className="text-[11.5px] text-[#7e93b5]">{MODE[active.mode].label}</div>
          </div>
        </div>

        <dl className="mt-3 space-y-1.5 text-[12px]">
          <Row label="Service level">
            <span style={{ color: LEVEL_COLOR[sched.level] }}>{sched.level}</span>
          </Row>
          <Row label="Frequency">{headway}</Row>
          <Row label="Trips / day">≈ {sched.tripsPerDay.toLocaleString()}</Row>
          <Row label="Trips in period">{active.trips.toLocaleString()}</Row>
        </dl>

        <p className="mt-2.5 text-[10px] leading-snug text-[#6f86ab]">
          GTFS-derived estimate over {SERVICE_PERIOD.label} ({SERVICE_PERIOD.days} days) — not a published timetable.
        </p>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[#9fb4d6]">{label}</dt>
      <dd className="font-medium text-[#e6eefb]">{children}</dd>
    </div>
  );
}
