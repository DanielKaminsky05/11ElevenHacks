"use client";

import type { NeighbourhoodProps } from "@/lib/choropleth";

export interface NeighbourhoodDrawerProps {
  /** The clicked neighbourhood's full properties, or null when closed. */
  feature: NeighbourhoodProps | null;
  onClose: () => void;
}

/**
 * NEIGHBOURHOOD DETAIL DRAWER.
 *
 * STATUS: STUB — implemented by the `neighbourhood-drawer` agent.
 * See .claude/agents/feat-neighbourhood-drawer.md.
 *
 * Goal: a slide-in side panel showing the full profile of a clicked
 * neighbourhood (population, density, income, tenure, the four marginalization
 * quintiles, transit-commute share, top occupations, NIA status). Returns null
 * when `feature` is null. The whole `NeighbourhoodProps` object is provided —
 * every field is already loaded, no fetching needed.
 */
export function NeighbourhoodDrawer({ feature, onClose }: NeighbourhoodDrawerProps) {
  void feature;
  void onClose;
  return null;
}
