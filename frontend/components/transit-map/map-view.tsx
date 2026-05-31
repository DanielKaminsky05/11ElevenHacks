"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, {
  type ExpressionSpecification,
  type FilterSpecification,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  DARK_STYLE_URL,
  MAP_BACKGROUND,
  MODE,
  STOP_COLOR,
  TORONTO_VIEW,
  loadNetwork,
  toGeoJSON,
} from "@/lib/transit";
import { MapLegend, type LayerKey, type LegendState } from "./map-legend";

/** Map layer ids controlled by each legend toggle. */
const LAYERS_BY_KEY: Record<LayerKey, string[]> = {
  subway: ["subway-glow", "subway-line"],
  streetcar: ["streetcar-glow", "streetcar-line"],
  bus: ["bus-glow", "bus-line"],
  busstops: ["busstops-layer", "busstops-labels"],
};

const INITIAL_VISIBILITY: LegendState = {
  subway: true,
  streetcar: true,
  bus: true,
  busstops: true,
};

export function MapView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const [status, setStatus] = useState("Loading network data…");
  const [counts, setCounts] = useState<Record<LayerKey, number>>({
    subway: 0,
    streetcar: 0,
    bus: 0,
    busstops: 0,
  });
  const [visibility, setVisibility] = useState<LegendState>(INITIAL_VISIBILITY);
  const [ready, setReady] = useState(false);

  // Create the map and load the network once on mount.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE_URL,
      center: TORONTO_VIEW.center,
      zoom: TORONTO_VIEW.zoom,
      pitch: TORONTO_VIEW.pitch,
      bearing: TORONTO_VIEW.bearing,
      maxPitch: 80,
      canvasContextAttributes: { antialias: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    let cancelled = false;

    async function addNetwork() {
      let data;
      try {
        data = await loadNetwork();
      } catch (err) {
        if (!cancelled) {
          setStatus(err instanceof Error ? err.message : "Failed to load network");
        }
        return;
      }
      if (cancelled) return;

      const { routes, stops } = toGeoJSON(data);
      map.addSource("routes", { type: "geojson", data: routes });
      map.addSource("stops", { type: "geojson", data: stops });

      // Route lines: a blurred glow halo under a crisp core, one pair per mode.
      for (const [mode, cfg] of Object.entries(MODE)) {
        const filter: FilterSpecification = ["==", ["get", "mode"], mode];
        map.addLayer({
          id: `${mode}-glow`,
          type: "line",
          source: "routes",
          filter,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ["get", "color"],
            "line-width": cfg.width * 3.5,
            "line-blur": cfg.width * 3,
            "line-opacity": 0.5,
          },
        });
        map.addLayer({
          id: `${mode}-line`,
          type: "line",
          source: "routes",
          filter,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ["get", "color"],
            "line-width": cfg.width,
            "line-opacity": 0.95,
          },
        });
      }

      // Bus-stop markers (only the stops served by a bus route).
      map.addLayer({
        id: "busstops-layer",
        type: "circle",
        source: "stops",
        minzoom: 11,
        filter: ["==", ["get", "bus"], 1],
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"], 11, 1.3, 14, 2.8, 17, 5,
          ] as ExpressionSpecification,
          "circle-color": STOP_COLOR,
          "circle-opacity": [
            "interpolate", ["linear"], ["zoom"], 11, 0.5, 14, 0.85,
          ] as ExpressionSpecification,
          "circle-stroke-color": "#3a2c00",
          "circle-stroke-width": [
            "interpolate", ["linear"], ["zoom"], 13, 0, 15, 0.6,
          ] as ExpressionSpecification,
        },
      });

      // Collision-managed stop labels, thinned automatically at low zoom.
      map.addLayer({
        id: "busstops-labels",
        type: "symbol",
        source: "stops",
        minzoom: 13,
        filter: ["==", ["get", "bus"], 1],
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Regular"],
          "text-size": [
            "interpolate", ["linear"], ["zoom"], 13, 9, 17, 13,
          ] as ExpressionSpecification,
          "text-anchor": "top",
          "text-offset": [0, 0.6],
          "text-optional": true,
          "text-padding": 4,
          "text-max-width": 9,
        },
        paint: {
          "text-color": "#ffe9a8",
          "text-halo-color": "#16100a",
          "text-halo-width": 1.4,
        },
      });

      wirePopups(map);

      setCounts({
        subway: data.counts.subway,
        streetcar: data.counts.streetcar,
        bus: data.counts.bus,
        busstops: data.counts.busStops,
      });
      setStatus(`${data.routes.length} routes · ${data.stops.length} stops`);
      setReady(true);
    }

    map.on("load", addNetwork);

    return () => {
      cancelled = true;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Apply layer visibility whenever a toggle changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const [key, layerIds] of Object.entries(LAYERS_BY_KEY)) {
      const value = visibility[key as LayerKey] ? "visible" : "none";
      for (const id of layerIds) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", value);
      }
    }
  }, [visibility, ready]);

  function toggleLayer(key: LayerKey) {
    setVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="relative h-full w-full" style={{ background: MAP_BACKGROUND }}>
      <div ref={containerRef} className="absolute inset-0" />
      <MapLegend
        status={status}
        visibility={visibility}
        counts={counts}
        onToggle={toggleLayer}
      />
    </div>
  );
}

/** Attaches click popups for route lines and bus stops. */
function wirePopups(map: maplibregl.Map) {
  const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true });

  for (const mode of Object.keys(MODE)) {
    map.on("mouseenter", `${mode}-line`, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", `${mode}-line`, () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("click", `${mode}-line`, (e: MapLayerMouseEvent) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      const cfg = MODE[p.mode as keyof typeof MODE];
      popup
        .setLngLat(e.lngLat)
        .setHTML(`<b>${p.name}</b><br>${cfg.label} · ${p.trips} trips/period`)
        .addTo(map);
    });
  }

  map.on("mouseenter", "busstops-layer", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "busstops-layer", () => {
    map.getCanvas().style.cursor = "";
  });
  map.on("click", "busstops-layer", (e: MapLayerMouseEvent) => {
    const p = e.features?.[0]?.properties;
    if (!p) return;
    const modes: string = p.modes ?? "";
    const served = [
      modes.includes("b") && "bus",
      modes.includes("s") && "streetcar",
      modes.includes("u") && "subway",
    ]
      .filter(Boolean)
      .join(", ");
    popup
      .setLngLat(e.lngLat)
      .setHTML(`<b>${p.name}</b><br>Bus stop${served ? ` · ${served}` : ""}`)
      .addTo(map);
  });
}
