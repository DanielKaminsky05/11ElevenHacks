"use client";

import dynamic from "next/dynamic";
import { MAP_BACKGROUND } from "@/lib/transit";

// MapLibre is browser-only, so render the map with SSR disabled. `ssr: false`
// is only allowed inside a Client Component, which is why this wrapper exists.
const MapView = dynamic(() => import("./map-view").then((m) => m.MapView), {
  ssr: false,
  loading: () => (
    <div
      className="flex w-full items-center justify-center text-sm text-[#9fb4d6]"
      style={{ height: "100%", background: MAP_BACKGROUND }}
    >
      Loading map…
    </div>
  ),
});

export function TransitMap() {
  return <MapView />;
}
