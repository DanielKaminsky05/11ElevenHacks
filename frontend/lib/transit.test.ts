import { afterEach, describe, expect, it, vi } from "vitest";
import { loadNetwork, toGeoJSON, type NetworkData } from "./transit";

/** Minimal network fixture: one bus route + two stops (one bus, one not). */
function makeNetwork(): NetworkData {
  return {
    routes: [
      {
        id: "10",
        short: "10",
        long: "Van Horne",
        mode: "bus",
        color: "#ED1C24",
        trips: 38,
        pts: [
          [43.787, -79.334],
          [43.788, -79.335],
        ],
      },
    ],
    stops: [
      [43.714, -79.26, "Danforth Rd at Kennedy Rd", "b", ["300"]],
      [43.674, -79.39, "Union Station", "us", ["1"]],
    ],
    counts: { subway: 3, streetcar: 18, bus: 211, busStops: 8673 },
  };
}

describe("toGeoJSON", () => {
  it("flips route points from [lat, lon] to GeoJSON [lon, lat]", () => {
    // Arrange
    const data = makeNetwork();

    // Act
    const { routes } = toGeoJSON(data);

    // Assert — input [43.787, -79.334] must become [-79.334, 43.787].
    expect(routes.features[0].geometry.coordinates).toEqual([
      [-79.334, 43.787],
      [-79.335, 43.788],
    ]);
  });

  it("composes the route name from its short and long names", () => {
    const data = makeNetwork();

    const { routes } = toGeoJSON(data);

    expect(routes.features[0].properties.name).toBe("10 Van Horne");
  });

  it("carries route id, mode, color and trips through unchanged", () => {
    const data = makeNetwork();

    const { routes } = toGeoJSON(data);

    expect(routes.features[0].properties).toMatchObject({
      id: "10",
      mode: "bus",
      color: "#ED1C24",
      trips: 38,
    });
  });

  it("flips stop points from [lat, lon] to GeoJSON [lon, lat]", () => {
    const data = makeNetwork();

    const { stops } = toGeoJSON(data);

    expect(stops.features[0].geometry.coordinates).toEqual([-79.26, 43.714]);
  });

  it("marks a stop served by a bus route with bus = 1", () => {
    const data = makeNetwork();

    const { stops } = toGeoJSON(data);

    expect(stops.features[0].properties.bus).toBe(1);
  });

  it("marks a stop not served by any bus route with bus = 0", () => {
    const data = makeNetwork();

    const { stops } = toGeoJSON(data);

    // Second stop's mode flags are "us" (subway) — no bus.
    expect(stops.features[1].properties.bus).toBe(0);
  });

  it("returns empty feature collections when the network is empty", () => {
    const data: NetworkData = {
      routes: [],
      stops: [],
      counts: { subway: 0, streetcar: 0, bus: 0, busStops: 0 },
    };

    const { routes, stops } = toGeoJSON(data);

    expect(routes).toEqual({ type: "FeatureCollection", features: [] });
    expect(stops).toEqual({ type: "FeatureCollection", features: [] });
  });
});

describe("loadNetwork", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the parsed network on a successful fetch", async () => {
    // Arrange
    const data = makeNetwork();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(data), { status: 200 })),
    );

    // Act
    const result = await loadNetwork();

    // Assert
    expect(result.routes).toHaveLength(1);
    expect(result.counts.bus).toBe(211);
  });

  it("throws with the status code when the fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("not found", { status: 404 })),
    );

    await expect(loadNetwork()).rejects.toThrow("404");
  });
});
