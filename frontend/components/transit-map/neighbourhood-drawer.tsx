"use client";

import type { NeighbourhoodProps } from "@/lib/choropleth";

export interface NeighbourhoodDrawerProps {
  /** The clicked neighbourhood's full properties, or null when closed. */
  feature: NeighbourhoodProps | null;
  onClose: () => void;
}

/** Labels for NOC major groups 0–9. */
const NOC_LABELS: Record<number, string> = {
  0: "Management",
  1: "Business / finance / admin",
  2: "Sciences & tech",
  3: "Health",
  4: "Education / law / social / gov",
  5: "Art / culture / rec",
  6: "Sales & service",
  7: "Trades & transport",
  8: "Natural resources & agriculture",
  9: "Manufacturing & utilities",
};

/** ON-Marg dimension labels. */
const MARG_DIMS = [
  { key: "marg_material" as const, label: "Material deprivation" },
  { key: "marg_households" as const, label: "Households & dwellings" },
  { key: "marg_age_labour" as const, label: "Age & labour force" },
  { key: "marg_racialized" as const, label: "Racialized & newcomer" },
];

/** Colors for quintiles 1–5 (index 0 = Q1, index 4 = Q5). */
const QUINTILE_COLORS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"];

/** Format a nullable percent value. */
function pct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(decimals)} %`;
}

/** Format a nullable number with locale separators. */
function num(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString();
}

/** Section header element. */
function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-[10px] uppercase tracking-[1px] text-[#6f86ab]">
      {children}
    </p>
  );
}

/** Labelled stat row. */
function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-[#9fb4d6]">{label}</span>
      <span className="font-medium text-[#e6eefb]">{value}</span>
    </div>
  );
}

/** Quintile chip (Q1–Q5 with color). */
function QuintileChip({ q }: { q: number | null | undefined }) {
  if (q == null) {
    return (
      <span className="inline-flex h-5 w-7 items-center justify-center rounded text-[10px] text-[#6f86ab] bg-white/5">
        —
      </span>
    );
  }
  const idx = Math.max(0, Math.min(4, q - 1));
  const color = QUINTILE_COLORS[idx];
  return (
    <span
      className="inline-flex h-5 w-7 items-center justify-center rounded text-[10px] font-bold"
      style={{ background: color + "33", color, border: `1px solid ${color}66` }}
    >
      Q{q}
    </span>
  );
}

/**
 * Slide-in right-side drawer showing the full profile of a clicked
 * neighbourhood. Returns null when `feature` is null (drawer is closed).
 */
export function NeighbourhoodDrawer({ feature, onClose }: NeighbourhoodDrawerProps) {
  if (feature === null) return null;

  // Compute top-3 occupations by share.
  const nocEntries: { idx: number; val: number }[] = [];
  for (let i = 0; i <= 9; i++) {
    const val = feature[`noc${i}_pct` as keyof NeighbourhoodProps] as number | null;
    if (val != null) {
      nocEntries.push({ idx: i, val });
    }
  }
  nocEntries.sort((a, b) => b.val - a.val);
  const top3 = nocEntries.slice(0, 3);

  return (
    <div className="pointer-events-auto absolute top-0 right-0 h-full w-[340px] z-30 flex flex-col rounded-l-xl border-l border-sky-400/25 bg-[#0c1628]/95 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-none items-start justify-between border-b border-sky-400/15 px-4 py-3.5">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold leading-snug text-white">
            {feature.name}
          </h2>
          {feature.is_nia && (
            <span className="mt-1 inline-block rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[1px] text-amber-400 border border-amber-400/30">
              NIA
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close neighbourhood drawer"
          className="ml-3 flex-none rounded p-1 text-[#6f86ab] hover:bg-white/10 hover:text-white transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Scrollable body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 space-y-5">

        {/* Snapshot */}
        <section>
          <SectionHeader>Snapshot</SectionHeader>
          <div className="space-y-1.5">
            <StatRow label="Population" value={num(feature.pop)} />
            <StatRow label="Density" value={feature.density != null ? `${feature.density.toFixed(0)} /km²` : "—"} />
            <StatRow label="Area" value={`${feature.area_km2.toFixed(2)} km²`} />
          </div>
        </section>

        {/* Income & housing */}
        <section>
          <SectionHeader>Income &amp; housing</SectionHeader>
          <div className="space-y-1.5">
            <StatRow label="Low-income prevalence" value={pct(feature.low_income_pct)} />
            <StatRow label="Renters" value={pct(feature.renter_pct)} />
          </div>
        </section>

        {/* Mobility */}
        <section>
          <SectionHeader>Mobility</SectionHeader>
          <div className="space-y-1.5">
            <StatRow label="Transit commute" value={pct(feature.transit_commute_pct)} />
            <StatRow label="Car" value={pct(feature.car_pct)} />
            <StatRow label="Active (walk / bike)" value={pct(feature.active_pct)} />
          </div>
        </section>

        {/* Age */}
        <section>
          <SectionHeader>Age</SectionHeader>
          <div className="space-y-1.5">
            <StatRow label="Seniors 65+" value={pct(feature.senior_pct)} />
          </div>
        </section>

        {/* ON-Marg quintiles */}
        <section>
          <SectionHeader>Marginalization (ON-Marg)</SectionHeader>
          <p className="mb-2.5 text-[10px] text-[#6f86ab]">Q1 = least · Q5 = most marginalized</p>
          <div className="space-y-2">
            {MARG_DIMS.map(({ key, label }) => (
              <div key={key} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="text-[#9fb4d6] min-w-0 truncate">{label}</span>
                <QuintileChip q={feature[key] as number | null | undefined} />
              </div>
            ))}
          </div>
        </section>

        {/* Top occupations */}
        <section>
          <SectionHeader>Top occupations</SectionHeader>
          {top3.length === 0 ? (
            <p className="text-[12px] text-[#6f86ab]">—</p>
          ) : (
            <div className="space-y-2">
              {top3.map(({ idx, val }) => (
                <div key={idx}>
                  <div className="flex items-center justify-between text-[12px] mb-0.5">
                    <span className="text-[#9fb4d6] truncate min-w-0 pr-2">{NOC_LABELS[idx]}</span>
                    <span className="flex-none font-medium text-[#e6eefb]">{val.toFixed(1)} %</span>
                  </div>
                  <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-sky-400/70"
                      style={{ width: `${Math.min(100, val)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

      </div>
    </div>
  );
}
