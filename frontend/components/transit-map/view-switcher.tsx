"use client";

import type { ViewModule, LegendSpec } from "./views/types";

interface ViewSwitcherProps {
  views: ViewModule[];
  activeId: string | null;
  activeOption: string | null;
  onSelect: (id: string | null) => void;
  onOption: (optionId: string) => void;
  legend: LegendSpec | null;
}

/**
 * Overlay-view picker. Renders a "Network only" option plus one radio per
 * registered view, grouped by `view.group`, and — when a view is active — its
 * sub-metric dropdown and legend. Purely shell UI; views provide their content.
 */
export function ViewSwitcher({
  views,
  activeId,
  activeOption,
  onSelect,
  onOption,
  legend,
}: ViewSwitcherProps) {
  const groups = Array.from(new Set(views.map((v) => v.group)));
  const active = views.find((v) => v.id === activeId) ?? null;

  return (
    <div className="pointer-events-auto absolute right-3.5 top-3.5 z-10 max-w-[280px] rounded-xl border border-sky-400/25 bg-[#0c1628]/85 p-4 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      <div className="mb-1.5 text-[10px] uppercase tracking-[1px] text-[#6f86ab]">
        Data view
      </div>

      <label className="flex items-center gap-2 py-1 text-[13px]">
        <input
          type="radio"
          name="view"
          checked={activeId === null}
          onChange={() => onSelect(null)}
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
                  checked={activeId === v.id}
                  onChange={() => onSelect(v.id)}
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
                  active.options.find((o) => o.id === activeOption) ??
                  active.options[0];
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

          {legend && <LegendView spec={legend} />}
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
