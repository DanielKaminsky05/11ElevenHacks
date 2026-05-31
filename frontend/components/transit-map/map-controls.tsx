"use client";

import { useEffect, useState } from "react";
import type maplibregl from "maplibre-gl";
import { TORONTO_VIEW } from "@/lib/transit";

export interface MapControlsProps {
  /** Returns the live map instance (or null before it's ready). */
  getMap: () => maplibregl.Map | null;
  /** The active data view id, or null for "Network only". Non-null = a
   *  choropleth is showing, which reads best flattened to 2D. */
  activeViewId: string | null;
  /** True once the map has loaded. */
  ready: boolean;
}

/**
 * VIEW CONTROLS — 2D/3D camera toggle + reset.
 *
 * A small floating control cluster at the bottom-center. When a choropleth data
 * view is active it auto-flattens the camera to 2D (pitch 0, bearing 0) so the
 * fill map isn't distorted by perspective; when back to Network-only it eases
 * back to the 3D demo camera. The user can manually override at any time.
 *
 * Design:
 *   - `manualIs3D` is set ONLY from event handlers (never inside an effect).
 *     null = "follow auto"; true/false = user override for this view session.
 *   - `overrideForViewId` records which `activeViewId` was current when the
 *     override was set, so the override clears automatically on view change
 *     without needing any setState inside an effect.
 *   - A single `useEffect` reads both pieces of state to decide the desired
 *     camera posture and calls `map.easeTo()` — the only side-effect.
 */
export function MapControls({ getMap, activeViewId, ready }: MapControlsProps) {
  /** User-chosen 2D/3D preference for the current view (null = auto). */
  const [manualIs3D, setManualIs3D] = useState<boolean | null>(null);
  /** The `activeViewId` that was active when `manualIs3D` was last set. */
  const [overrideForViewId, setOverrideForViewId] = useState<string | null | undefined>(
    undefined,
  );

  // Derived: is the manual override still valid for the current view?
  const overrideValid = manualIs3D !== null && overrideForViewId === activeViewId;
  // What the camera should actually show.
  const effectiveIs3D = overrideValid ? manualIs3D : activeViewId === null;

  // Drive the external camera system (map.easeTo) whenever the desired posture changes.
  // This effect only touches an external system — it never calls setState.
  useEffect(() => {
    if (!ready) return;
    const map = getMap();
    if (!map) return;

    if (effectiveIs3D) {
      map.easeTo({
        pitch: TORONTO_VIEW.pitch,
        bearing: TORONTO_VIEW.bearing,
        duration: 600,
      });
    } else {
      map.easeTo({ pitch: 0, bearing: 0, duration: 600 });
    }
  }, [effectiveIs3D, ready, getMap]);

  function handleSet3D(want3D: boolean) {
    if (!ready) return;
    setManualIs3D(want3D);
    setOverrideForViewId(activeViewId);
  }

  function handleReset() {
    if (!ready) return;
    const map = getMap();
    if (!map) return;

    // Clear manual override so auto-flatten resumes.
    setManualIs3D(null);
    setOverrideForViewId(undefined);

    // Jump directly to the full default view (center + zoom + angles).
    map.easeTo({
      center: TORONTO_VIEW.center,
      zoom: TORONTO_VIEW.zoom,
      pitch: TORONTO_VIEW.pitch,
      bearing: TORONTO_VIEW.bearing,
      duration: 600,
    });
  }

  const btnBase = "rounded-md border px-3 py-1 text-[12px] transition-colors";
  const btnActive = "bg-sky-500/30 border-sky-400/60 text-white";
  const btnInactive =
    "bg-white/[0.04] hover:bg-white/[0.08] border-transparent text-[#dce6f5]";

  return (
    <div className="pointer-events-auto absolute bottom-4 left-1/2 z-10 -translate-x-1/2 flex items-center gap-2 rounded-xl border border-sky-400/25 bg-[#0c1628]/90 px-3 py-2 text-[#dce6f5] shadow-2xl backdrop-blur-md">
      {/* 2D / 3D segmented toggle */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => handleSet3D(false)}
          className={`${btnBase} ${!effectiveIs3D ? btnActive : btnInactive}`}
          aria-pressed={!effectiveIs3D}
        >
          2D
        </button>
        <button
          type="button"
          onClick={() => handleSet3D(true)}
          className={`${btnBase} ${effectiveIs3D ? btnActive : btnInactive}`}
          aria-pressed={effectiveIs3D}
        >
          3D
        </button>
      </div>

      {/* Divider */}
      <div className="h-4 w-px bg-sky-400/20" aria-hidden />

      {/* Reset button */}
      <button
        type="button"
        onClick={handleReset}
        className={`${btnBase} ${btnInactive}`}
        title="Reset camera to default view"
      >
        Reset
      </button>
    </div>
  );
}
