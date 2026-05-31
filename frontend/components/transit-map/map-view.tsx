"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
import { loadNeighbourhoods } from "@/lib/choropleth";
import { MapLegend, type LayerKey, type LegendState } from "./map-legend";
import { ViewSwitcher } from "./view-switcher";
import { RouteDetails, type SelectedRoute } from "./route-details";
import { VIEWS, getView } from "./views/registry";
import type { LegendSpec } from "./views/types";

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

  // Overlay-view state (choropleths etc. registered in views/registry.ts).
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [activeOption, setActiveOption] = useState<string | null>(null);
  const [viewLegend, setViewLegend] = useState<LegendSpec | null>(null);

  // Route selection (click a line to isolate it + see its details).
  const [selectedRoutes, setSelectedRoutes] = useState<SelectedRoute[]>([]);
  const [activeRouteId, setActiveRouteId] = useState<string | null>(null);
  // Map click handlers live in the setup closure; route through a ref so they
  // always call the latest React state updater.
  const onRouteClickRef = useRef<(r: SelectedRoute) => void>(() => {});

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
    // Expose for verification scripts (screenshot harness queries rendered features).
    (window as unknown as { __transitMap?: maplibregl.Map }).__transitMap = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    // The map can mount (via next/dynamic) before the container has its final
    // size, leaving MapLibre stuck at its 300px fallback height. Keep the GL
    // canvas in sync with the container.
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(containerRef.current);

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

      // Extruded buildings sit under the routes for the demo's dark 3D look.
      add3DBuildings(map);

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

      // Bright white casing under selected routes; filtered to nothing until a
      // route is clicked. Added above the route lines, then the crisp cores are
      // moved back on top so the selected route's colour still shows.
      map.addLayer({
        id: "routes-highlight",
        type: "line",
        source: "routes",
        filter: ["in", ["get", "id"], ["literal", []]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": [
            "interpolate", ["linear"], ["zoom"], 10, 4, 14, 7,
          ] as ExpressionSpecification,
          "line-opacity": 0.9,
          "line-blur": 0.4,
        },
      });
      for (const mode of Object.keys(MODE)) {
        if (map.getLayer(`${mode}-line`)) map.moveLayer(`${mode}-line`);
      }

      wireInteractions(map, (r) => onRouteClickRef.current(r));

      // Neighbourhood name labels — only appear once you've zoomed in closeish
      // (minzoom 11.5), so the wide city view stays uncluttered. MapLibre places
      // each label at its polygon's centroid automatically.
      try {
        const hoods = await loadNeighbourhoods();
        if (!cancelled && !map.getSource("nbhd-labels")) {
          map.addSource("nbhd-labels", { type: "geojson", data: hoods });
          map.addLayer({
            id: "nbhd-labels-layer",
            type: "symbol",
            source: "nbhd-labels",
            minzoom: 11.5,
            layout: {
              "text-field": ["get", "name"],
              "text-font": ["Noto Sans Regular"],
              "text-size": [
                "interpolate", ["linear"], ["zoom"], 11.5, 11, 13, 15, 15, 19,
              ] as ExpressionSpecification,
              "text-max-width": 8,
              "text-letter-spacing": 0.02,
              "text-padding": 6,
              "text-allow-overlap": false,
            },
            paint: {
              "text-color": "#eaf2ff",
              "text-halo-color": "#0a1628",
              "text-halo-width": 1.6,
              "text-halo-blur": 0.4,
              // Fade the labels in as you zoom past the threshold.
              "text-opacity": [
                "interpolate", ["linear"], ["zoom"], 11.5, 0, 12.2, 0.92,
              ] as ExpressionSpecification,
            },
          });
        }
      } catch (err) {
        console.warn("neighbourhood labels unavailable:", err);
      }

      // Set up every registered overlay view. Each adds its own (hidden)
      // sources/layers; a failure in one view must not break the map.
      for (const view of VIEWS) {
        try {
          await view.setup({ map });
        } catch (err) {
          console.warn(`view "${view.id}" setup failed:`, err);
        }
      }
      if (cancelled) return;

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
      resizeObserver.disconnect();
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

  // Show only the active overlay view's layers; hide all others.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const view of VIEWS) {
      const visible = view.id === activeViewId ? "visible" : "none";
      for (const id of view.layerIds) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible);
      }
    }
    const active = activeViewId ? getView(activeViewId) : null;
    setViewLegend(active ? active.legend() : null);
  }, [activeViewId, ready]);

  // Toggle a route in/out of the selection when its line is clicked.
  const toggleRoute = useCallback((r: SelectedRoute) => {
    setSelectedRoutes((prev) =>
      prev.some((x) => x.id === r.id)
        ? prev.filter((x) => x.id !== r.id)
        : [...prev, r],
    );
    setActiveRouteId((prev) => (prev === r.id ? null : r.id));
  }, []);
  onRouteClickRef.current = toggleRoute;

  // Apply selection styling: dim unselected routes, highlight selected ones.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const ids = selectedRoutes.map((r) => r.id);
    const has = ids.length > 0;

    for (const mode of Object.keys(MODE)) {
      const glow = `${mode}-glow`;
      const line = `${mode}-line`;
      if (!map.getLayer(line)) continue;
      if (!has) {
        map.setPaintProperty(glow, "line-opacity", 0.5);
        map.setPaintProperty(line, "line-opacity", 0.95);
        continue;
      }
      const inSel = ["in", ["get", "id"], ["literal", ids]];
      map.setPaintProperty(glow, "line-opacity", ["case", inSel, 0.5, 0.06]);
      map.setPaintProperty(line, "line-opacity", ["case", inSel, 1, 0.1]);
    }
    if (map.getLayer("routes-highlight")) {
      map.setFilter("routes-highlight", ["in", ["get", "id"], ["literal", ids]]);
    }
  }, [selectedRoutes, ready]);

  function removeRoute(id: string) {
    setSelectedRoutes((prev) => prev.filter((x) => x.id !== id));
    setActiveRouteId((prev) => (prev === id ? null : prev));
  }

  function clearRoutes() {
    setSelectedRoutes([]);
    setActiveRouteId(null);
  }

  function toggleLayer(key: LayerKey) {
    setVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function selectView(id: string | null) {
    setActiveViewId(id);
    const view = id ? getView(id) : null;
    const firstOption = view?.options?.[0]?.id ?? null;
    setActiveOption(firstOption);
  }

  function changeOption(optionId: string) {
    const map = mapRef.current;
    const view = activeViewId ? getView(activeViewId) : null;
    if (!map || !view?.setOption) return;
    view.setOption({ map }, optionId);
    setActiveOption(optionId);
    setViewLegend(view.legend());
  }

  return (
    <div
      className="relative w-full"
      style={{ height: "100%", background: MAP_BACKGROUND }}
    >
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      <MapLegend
        status={status}
        visibility={visibility}
        counts={counts}
        onToggle={toggleLayer}
      />
      {ready && (
        <ViewSwitcher
          views={VIEWS}
          activeId={activeViewId}
          activeOption={activeOption}
          onSelect={selectView}
          onOption={changeOption}
          legend={viewLegend}
        />
      )}
      <RouteDetails
        selected={selectedRoutes}
        activeId={activeRouteId}
        onSetActive={setActiveRouteId}
        onRemove={removeRoute}
        onClear={clearRoutes}
      />
    </div>
  );
}

/**
 * Adds an extruded-building layer if the basemap exposes OpenMapTiles
 * buildings. Drawn before the route layers so routes render on top; only
 * visible once zoomed in (minzoom 13), matching the demo's 3D scene.
 */
function add3DBuildings(map: maplibregl.Map) {
  if (map.getLayer("ttc-3d-buildings")) return;

  let source: string | null = null;
  for (const [id, s] of Object.entries(map.getStyle().sources ?? {})) {
    if (s.type === "vector" && id.toLowerCase().includes("openmaptiles")) {
      source = id;
    }
  }
  if (!source) source = "openmaptiles";

  try {
    map.addLayer({
      id: "ttc-3d-buildings",
      source,
      "source-layer": "building",
      type: "fill-extrusion",
      minzoom: 13,
      paint: {
        "fill-extrusion-color": [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "render_height"], 10],
          0,
          "#1b2a44",
          50,
          "#22416b",
          150,
          "#2e5a93",
        ] as ExpressionSpecification,
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 12],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.78,
      },
    });
  } catch (err) {
    // Some basemaps lack a building layer; the map still works without it.
    console.warn("3D buildings unavailable for this style:", err);
  }
}

/**
 * Wire map interactions: clicking a route line selects it (handled in React via
 * `onRouteClick`); bus stops keep a lightweight popup.
 */
function wireInteractions(
  map: maplibregl.Map,
  onRouteClick: (r: SelectedRoute) => void,
) {
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
      onRouteClick({
        id: String(p.id),
        short: String(p.short),
        long: String(p.long ?? p.name ?? ""),
        mode: p.mode as SelectedRoute["mode"],
        color: String(p.color),
        trips: Number(p.trips) || 0,
      });
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
