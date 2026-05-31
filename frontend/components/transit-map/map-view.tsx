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
import {
  loadNeighbourhoods,
  type NeighbourhoodFC,
  type NeighbourhoodProps,
} from "@/lib/choropleth";
import { subscribeMapCommand } from "@/lib/map-bus";
import type { OptStep } from "@/lib/optimizer";
import { planToMapAction } from "@/lib/planner-actions";
import { loadEvents, eventsToGeoJSON } from "@/lib/events";
import type { LayerKey, LegendState } from "./map-legend";
import { ControlPanel } from "./control-panel";
import { RouteDetails, type SelectedRoute } from "./route-details";
import { MapControls } from "./map-controls";
import { NeighbourhoodDrawer } from "./neighbourhood-drawer";
import { setChoroplethPopupsEnabled } from "./views/choropleth-helpers";
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

  // Neighbourhood selection (click a polygon to open the detail drawer).
  const [selectedNbhd, setSelectedNbhd] = useState<NeighbourhoodProps | null>(null);
  // Cached neighbourhood FeatureCollection — used for the click hit-layer and
  // for fitting the camera when the planner drives the map.
  const nbhdFcRef = useRef<NeighbourhoodFC | null>(null);

  // Cancel handle for the in-flight optimizer build animation (so a re-solve
  // cancels the previous replay).
  const optAnimRef = useRef<(() => void) | null>(null);

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
        nbhdFcRef.current = hoods;
        if (!cancelled && !map.getSource("nbhd-labels")) {
          map.addSource("nbhd-labels", { type: "geojson", data: hoods });

          // Open the community summary only when the neighbourhood NAME label
          // (the "title") is clicked — clicking anywhere in the polygon felt too
          // aggressive. The label layer is added just below; MapLibre resolves a
          // layer-scoped handler at event time, so registering it first is fine.
          map.on("click", "nbhd-labels-layer", (e: MapLayerMouseEvent) => {
            // Route clicks win over neighbourhood selection.
            const routeHit = map.queryRenderedFeatures(e.point, {
              layers: ["subway-line", "streetcar-line", "bus-line"].filter((l) =>
                map.getLayer(l),
              ),
            });
            if (routeHit.length) return;
            const props = e.features?.[0]?.properties;
            if (props) setSelectedNbhd(props as unknown as NeighbourhoodProps);
          });
          map.on("mouseenter", "nbhd-labels-layer", () => {
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "nbhd-labels-layer", () => {
            map.getCanvas().style.cursor = "";
          });

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

      // City events (road/line closures + big draws). Closures are highlighted
      // distinctly so disruptions stand out; clicking an alert card flies here.
      try {
        const res = await loadEvents();
        if (!cancelled && !map.getSource("events")) {
          map.addSource("events", { type: "geojson", data: eventsToGeoJSON(res.events) });

          // Focus ring — a large halo under the marker, filtered to the event
          // the user clicked in the alert feed (none by default).
          map.addLayer({
            id: "events-focus",
            type: "circle",
            source: "events",
            filter: ["==", ["get", "id"], "__none__"],
            paint: {
              "circle-radius": 22,
              "circle-color": ["get", "color"],
              "circle-opacity": 0.18,
              "circle-stroke-color": ["get", "color"],
              "circle-stroke-width": 2,
              "circle-stroke-opacity": 0.6,
            },
          });

          // Demand surges (matches, festivals): soft filled dot in severity color.
          map.addLayer({
            id: "events-demand",
            type: "circle",
            source: "events",
            filter: ["==", ["get", "isClosure"], false],
            paint: {
              "circle-radius": [
                "interpolate", ["linear"], ["zoom"], 10, 5, 14, 9,
              ] as ExpressionSpecification,
              "circle-color": ["get", "color"],
              "circle-opacity": 0.55,
              "circle-stroke-color": "#0a1628",
              "circle-stroke-width": 1.5,
            },
          });

          // Closures (road/line disruptions): a bold hollow ring so they read
          // as "blocked / no-go" and clearly differ from demand dots.
          map.addLayer({
            id: "events-closure",
            type: "circle",
            source: "events",
            filter: ["==", ["get", "isClosure"], true],
            paint: {
              "circle-radius": [
                "interpolate", ["linear"], ["zoom"], 10, 6, 14, 11,
              ] as ExpressionSpecification,
              "circle-color": "#0a1628",
              "circle-opacity": 0.5,
              "circle-stroke-color": ["get", "color"],
              "circle-stroke-width": 3,
            },
          });

          // A ✕ sits on each closure for unmistakable "blocked" signalling.
          map.addLayer({
            id: "events-closure-icon",
            type: "symbol",
            source: "events",
            filter: ["==", ["get", "isClosure"], true],
            layout: {
              "text-field": "✕",
              "text-font": ["Noto Sans Regular"],
              "text-size": [
                "interpolate", ["linear"], ["zoom"], 10, 8, 14, 12,
              ] as ExpressionSpecification,
              "text-allow-overlap": true,
            },
            paint: {
              "text-color": ["get", "color"],
              "text-halo-color": "#0a1628",
              "text-halo-width": 1,
            },
          });

          wireEventInteractions(map);
        }
      } catch (err) {
        console.warn("events layer unavailable:", err);
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

      // The neighbourhood drawer is the single detail surface, so suppress the
      // smaller per-view click popups to avoid double UI.
      setChoroplethPopupsEnabled(false);

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

  // Keep the click-handler ref pointed at the latest callback (refs must not be
  // assigned during render).
  useEffect(() => {
    onRouteClickRef.current = toggleRoute;
  }, [toggleRoute]);

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

  const selectView = useCallback((id: string | null) => {
    setActiveViewId(id);
    const view = id ? getView(id) : null;
    const firstOption = view?.options?.[0]?.id ?? null;
    setActiveOption(firstOption);
  }, []);

  // Let the planner chat drive the map: when a goal is submitted, switch to the
  // view its weights imply and fit the camera to the highlighted neighbourhoods.
  useEffect(() => {
    if (!ready) return;
    return subscribeMapCommand((cmd) => {
      const map = mapRef.current;
      if (!map) return;

      if (cmd.type === "focusEvent") {
        // Fly to the event and ring it so the user sees where it is.
        map.flyTo({ center: [cmd.lng, cmd.lat], zoom: 13.5, duration: 1100 });
        if (map.getLayer("events-focus")) {
          map.setFilter("events-focus", ["==", ["get", "id"], cmd.eventId]);
        }
        return;
      }

      if (cmd.type === "applyPlan") {
        const fc = nbhdFcRef.current;
        if (!fc) return;
        const action = planToMapAction(cmd.weights, fc);
        selectView(action.viewId);
        const bounds = bboxForNums(fc, action.highlightNums);
        if (bounds) {
          map.fitBounds(bounds, { padding: 90, duration: 900, maxZoom: 13 });
        }
      }
    });
  }, [ready, selectView]);

  // Animate the optimizer's recommended stops landing on the map. Each re-solve
  // (e.g. dragging the equity weight up) replays from scratch, so stops visibly
  // migrate toward the newly-weighted areas.
  useEffect(() => {
    if (!ready) return;
    const unsubscribe = subscribeMapCommand((cmd) => {
      if (cmd.type !== "optimizerResult") return;
      const map = mapRef.current;
      if (!map) return;
      optAnimRef.current?.();
      optAnimRef.current = animateOptimizerStops(map, cmd.steps);
      // Bring the recommended stops into view so the user actually sees them land,
      // rather than leaving them off-screen wherever the map happened to be.
      const finalStops = cmd.steps[cmd.steps.length - 1]?.stops ?? [];
      if (finalStops.length === 1) {
        map.flyTo({ center: [finalStops[0].lon, finalStops[0].lat], zoom: 14, duration: 1200 });
      } else if (finalStops.length > 1) {
        const bounds = new maplibregl.LngLatBounds();
        for (const s of finalStops) bounds.extend([s.lon, s.lat]);
        map.fitBounds(bounds, { padding: 120, maxZoom: 14.5, duration: 1200 });
      }
    });
    return () => {
      unsubscribe();
      optAnimRef.current?.();
      optAnimRef.current = null;
    };
  }, [ready]);

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
      {ready && (
        <ControlPanel
          status={status}
          visibility={visibility}
          counts={counts}
          onToggle={toggleLayer}
          views={VIEWS}
          activeViewId={activeViewId}
          activeOption={activeOption}
          onSelectView={selectView}
          onOption={changeOption}
          viewLegend={viewLegend}
        />
      )}
      <RouteDetails
        selected={selectedRoutes}
        activeId={activeRouteId}
        onSetActive={setActiveRouteId}
        onRemove={removeRoute}
        onClear={clearRoutes}
      />
      {ready && (
        <MapControls
          getMap={() => mapRef.current}
          activeViewId={activeViewId}
          ready={ready}
        />
      )}
      <NeighbourhoodDrawer
        feature={selectedNbhd}
        onClose={() => setSelectedNbhd(null)}
      />
    </div>
  );
}

/**
 * Bounding box `[[west,south],[east,north]]` covering the given neighbourhood
 * numbers, or null if none match. Used to fit the camera when the planner
 * focuses on a set of neighbourhoods.
 */
function bboxForNums(
  fc: NeighbourhoodFC,
  nums: number[],
): [[number, number], [number, number]] | null {
  if (nums.length === 0) return null;
  const want = new Set(nums);
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const f of fc.features) {
    if (!want.has(f.properties.num)) continue;
    const g = f.geometry;
    const polys = g.type === "MultiPolygon" ? g.coordinates : [g.coordinates];
    for (const poly of polys) {
      for (const [x, y] of poly[0]) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  return maxX > minX ? [[minX, minY], [maxX, maxY]] : null;
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

/** Hover cursor + click popup on event markers (closures and demand surges). */
function wireEventInteractions(map: maplibregl.Map) {
  const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true });
  for (const layer of ["events-closure", "events-demand"]) {
    map.on("mouseenter", layer, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layer, () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("click", layer, (e: MapLayerMouseEvent) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      const kind = p.isClosure ? "Closure / disruption" : "Major event";
      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<b>${p.title}</b><br>${kind} · ${String(p.magnitude)}<br>${p.venueName ?? ""}`,
        )
        .addTo(map);
      map.flyTo({ center: e.lngLat, zoom: 13.5, duration: 900 });
    });
  }
}

/** Empty FeatureCollection (used to clear the optimizer layer between re-solves). */
const EMPTY_FC = { type: "FeatureCollection", features: [] } as const;

/**
 * Create the optimizer's recommended-stop layers if they don't exist yet: a soft
 * glow halo under a bright core, sitting on top of everything. The newest stop in
 * a step renders larger so each placement "pops" as the network builds.
 */
function ensureOptimizerStopLayers(map: maplibregl.Map) {
  if (!map.getSource("optimized-stops")) {
    map.addSource("optimized-stops", {
      type: "geojson",
      data: EMPTY_FC as unknown as GeoJSON.FeatureCollection,
    });
  }
  if (!map.getLayer("optimized-stops-glow")) {
    map.addLayer({
      id: "optimized-stops-glow",
      type: "circle",
      source: "optimized-stops",
      paint: {
        "circle-radius": 20,
        "circle-color": "#34d399",
        "circle-blur": 1,
        "circle-opacity": 0.22,
      },
    });
  }
  if (!map.getLayer("optimized-stops-core")) {
    map.addLayer({
      id: "optimized-stops-core",
      type: "circle",
      source: "optimized-stops",
      paint: {
        "circle-radius": [
          "case",
          ["==", ["get", "isNew"], 1],
          10,
          6,
        ] as ExpressionSpecification,
        "circle-color": "#6ee7b7",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
        "circle-opacity": 0.95,
      },
    });
  }
}

/**
 * Replay the optimizer's per-step trajectory: each frame sets the layer to that
 * step's stops (the last one flagged `isNew` so it pops), so the network appears
 * to build itself. Returns a cancel function; a new result cancels the prior run.
 */
function animateOptimizerStops(map: maplibregl.Map, steps: OptStep[]): () => void {
  ensureOptimizerStopLayers(map);
  let cancelled = false;
  const timers: ReturnType<typeof setTimeout>[] = [];

  steps.forEach((step, idx) => {
    const t = setTimeout(() => {
      if (cancelled) return;
      const src = map.getSource("optimized-stops") as
        | maplibregl.GeoJSONSource
        | undefined;
      if (!src) return;
      const last = step.stops.length - 1;
      src.setData({
        type: "FeatureCollection",
        features: step.stops.map((s, i) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [s.lon, s.lat] },
          properties: { isNew: i === last ? 1 : 0 },
        })),
      } as GeoJSON.FeatureCollection);
    }, idx * 280);
    timers.push(t);
  });

  return () => {
    cancelled = true;
    for (const t of timers) clearTimeout(t);
  };
}
