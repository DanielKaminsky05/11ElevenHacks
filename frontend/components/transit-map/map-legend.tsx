"use client";

import { MODE, STOP_COLOR, type TransitMode } from "@/lib/transit";

/** Layer toggle keys: the three route modes plus the bus-stop markers. */
export type LayerKey = TransitMode | "busstops";

export interface LegendState {
  subway: boolean;
  streetcar: boolean;
  bus: boolean;
  busstops: boolean;
}

interface LegendItem {
  key: LayerKey;
  label: string;
  color: string;
  /** Render the swatch as a dot (point) instead of a line. */
  dot?: boolean;
}

const ITEMS: LegendItem[] = [
  { key: "subway", label: MODE.subway.label, color: MODE.subway.color },
  { key: "streetcar", label: MODE.streetcar.label, color: MODE.streetcar.color },
  { key: "bus", label: MODE.bus.label, color: MODE.bus.color },
  { key: "busstops", label: "Bus stops", color: STOP_COLOR, dot: true },
];

interface MapLegendProps {
  status: string;
  visibility: LegendState;
  counts: Record<LayerKey, number>;
  onToggle: (key: LayerKey) => void;
}

export function MapLegend({ status, visibility, counts, onToggle }: MapLegendProps) {
  return (
    <div className="pointer-events-auto absolute left-3.5 top-3.5 z-10 max-w-[260px] rounded-xl border border-sky-400/25 bg-[#0c1628]/85 p-4 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      <div className="text-[15px] tracking-wide text-white">TTC Route Network</div>
      <div className="mt-0.5 mb-2.5 text-[11.5px] text-[#7e93b5]">
        GTFS schedule feed · dark basemap
      </div>
      <div className="mb-1.5 text-xs text-[#9fb4d6]">{status}</div>

      <div className="mb-1.5 mt-3 text-[10px] uppercase tracking-[1px] text-[#6f86ab]">
        Layers
      </div>
      <ul>
        {ITEMS.map((item) => {
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
