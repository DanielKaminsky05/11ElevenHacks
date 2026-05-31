// Unit tests for planToMapAction.
// Uses a small inline fixture so tests are self-contained and deterministic.

import { describe, it, expect } from "vitest";
import { planToMapAction } from "@/lib/planner-actions";
import type { NeighbourhoodFC } from "@/lib/choropleth";
import type { RewardWeights } from "@/lib/planner";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/**
 * Three-neighbourhood fixture.
 *  - N1: most marginalized (marg_material=5), low transit use
 *  - N2: moderately marginalized (marg_material=3), some transit use
 *  - N3: least marginalized (marg_material=1), high transit use
 *
 * All geometry values are dummies (not read by planToMapAction).
 */
const THREE_FEATURES: NeighbourhoodFC["features"] = [
  {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [] },
    properties: {
      num: 1,
      name: "Alpha",
      is_nia: true,
      area_km2: 5,
      pop: 10000,
      density: 2000,
      low_income_pct: 0.35,
      transit_commute_pct: 0.12,
      car_pct: 0.55,
      active_pct: 0.1,
      senior_pct: 0.15,
      renter_pct: 0.6,
      noc0_pct: null,
      noc1_pct: null,
      noc2_pct: null,
      noc3_pct: null,
      noc4_pct: null,
      noc5_pct: null,
      noc6_pct: null,
      noc7_pct: null,
      noc8_pct: null,
      noc9_pct: null,
      marg_material: 5,
      marg_racialized: 4,
    },
  },
  {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [] },
    properties: {
      num: 2,
      name: "Beta",
      is_nia: false,
      area_km2: 8,
      pop: 20000,
      density: 2500,
      low_income_pct: 0.2,
      transit_commute_pct: 0.3,
      car_pct: 0.5,
      active_pct: 0.15,
      senior_pct: 0.1,
      renter_pct: 0.4,
      noc0_pct: null,
      noc1_pct: null,
      noc2_pct: null,
      noc3_pct: null,
      noc4_pct: null,
      noc5_pct: null,
      noc6_pct: null,
      noc7_pct: null,
      noc8_pct: null,
      noc9_pct: null,
      marg_material: 3,
      marg_racialized: 2,
    },
  },
  {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [] },
    properties: {
      num: 3,
      name: "Gamma",
      is_nia: false,
      area_km2: 12,
      pop: 30000,
      density: 2500,
      low_income_pct: 0.05,
      transit_commute_pct: 0.55,
      car_pct: 0.35,
      active_pct: 0.1,
      senior_pct: 0.12,
      renter_pct: 0.3,
      noc0_pct: null,
      noc1_pct: null,
      noc2_pct: null,
      noc3_pct: null,
      noc4_pct: null,
      noc5_pct: null,
      noc6_pct: null,
      noc7_pct: null,
      noc8_pct: null,
      noc9_pct: null,
      marg_material: 1,
      marg_racialized: 1,
    },
  },
];

const FIXTURE_FC: NeighbourhoodFC = {
  type: "FeatureCollection",
  features: THREE_FEATURES,
};

/** Feature with null marg_material and null transit_commute_pct. */
const NULL_FEATURE: NeighbourhoodFC["features"][number] = {
  type: "Feature",
  geometry: { type: "Polygon", coordinates: [] },
  properties: {
    num: 99,
    name: "Null-ville",
    is_nia: false,
    area_km2: 3,
    pop: null,
    density: null,
    low_income_pct: null,
    transit_commute_pct: null,
    car_pct: null,
    active_pct: null,
    senior_pct: null,
    renter_pct: null,
    noc0_pct: null,
    noc1_pct: null,
    noc2_pct: null,
    noc3_pct: null,
    noc4_pct: null,
    noc5_pct: null,
    noc6_pct: null,
    noc7_pct: null,
    noc8_pct: null,
    noc9_pct: null,
    marg_material: null,
    marg_racialized: null,
  },
};

const NULL_ONLY_FC: NeighbourhoodFC = {
  type: "FeatureCollection",
  features: [NULL_FEATURE],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function weights(overrides: Partial<RewardWeights> = {}): RewardWeights {
  return { coverage: 0, travelTime: 0, equity: 0, constraints: 0, ...overrides };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("planToMapAction", () => {
  describe("equity-dominant goal", () => {
    it('returns viewId "equity-gap"', () => {
      const action = planToMapAction(weights({ equity: 0.8 }), FIXTURE_FC);
      expect(action.viewId).toBe("equity-gap");
    });

    it("highlights neighbourhoods ordered by marg_material descending (N1 first)", () => {
      const action = planToMapAction(weights({ equity: 0.8 }), FIXTURE_FC);
      expect(action.highlightNums[0]).toBe(1); // marg_material=5
      expect(action.highlightNums[1]).toBe(2); // marg_material=3
      expect(action.highlightNums[2]).toBe(3); // marg_material=1
    });

    it("returns non-empty highlightNums for valid data", () => {
      const action = planToMapAction(weights({ equity: 1 }), FIXTURE_FC);
      expect(action.highlightNums.length).toBeGreaterThan(0);
    });

    it("highlight nums are all valid neighbourhood numbers from fixture", () => {
      const action = planToMapAction(weights({ equity: 1 }), FIXTURE_FC);
      const validNums = new Set(FIXTURE_FC.features.map((f) => f.properties.num));
      for (const num of action.highlightNums) {
        expect(validNums.has(num)).toBe(true);
      }
    });
  });

  describe("coverage-dominant goal", () => {
    it('returns viewId "coverage"', () => {
      const action = planToMapAction(weights({ coverage: 0.9 }), FIXTURE_FC);
      expect(action.viewId).toBe("coverage");
    });

    it("highlights neighbourhoods with lowest transit_commute_pct first (N1 first)", () => {
      const action = planToMapAction(weights({ coverage: 0.9 }), FIXTURE_FC);
      // N1=0.12 is lowest, N2=0.30 next, N3=0.55 highest
      expect(action.highlightNums[0]).toBe(1);
      expect(action.highlightNums[1]).toBe(2);
      expect(action.highlightNums[2]).toBe(3);
    });

    it("returns non-empty highlightNums for valid data", () => {
      const action = planToMapAction(weights({ coverage: 1 }), FIXTURE_FC);
      expect(action.highlightNums.length).toBeGreaterThan(0);
    });
  });

  describe("travelTime-dominant goal", () => {
    it('returns viewId "demographics"', () => {
      const action = planToMapAction(weights({ travelTime: 0.7 }), FIXTURE_FC);
      expect(action.viewId).toBe("demographics");
    });

    it("returns non-empty highlightNums for valid data", () => {
      const action = planToMapAction(weights({ travelTime: 1 }), FIXTURE_FC);
      expect(action.highlightNums.length).toBeGreaterThan(0);
    });
  });

  describe("constraints-dominant goal (tie-break fallback)", () => {
    it('returns viewId "equity-gap" when constraints is dominant', () => {
      const action = planToMapAction(weights({ constraints: 0.9 }), FIXTURE_FC);
      expect(action.viewId).toBe("equity-gap");
    });
  });

  describe("tie-break ordering: equity > coverage > travelTime > constraints", () => {
    it("equity beats coverage when equal", () => {
      const action = planToMapAction(
        weights({ equity: 0.5, coverage: 0.5 }),
        FIXTURE_FC,
      );
      expect(action.viewId).toBe("equity-gap");
    });

    it("coverage beats travelTime when equal", () => {
      const action = planToMapAction(
        weights({ coverage: 0.5, travelTime: 0.5 }),
        FIXTURE_FC,
      );
      expect(action.viewId).toBe("coverage");
    });

    it("travelTime beats constraints when equal", () => {
      const action = planToMapAction(
        weights({ travelTime: 0.5, constraints: 0.5 }),
        FIXTURE_FC,
      );
      expect(action.viewId).toBe("demographics");
    });
  });

  describe("null field handling", () => {
    it("returns empty highlightNums when all relevant fields are null (equity mode)", () => {
      const action = planToMapAction(weights({ equity: 1 }), NULL_ONLY_FC);
      expect(action.highlightNums).toEqual([]);
    });

    it("returns empty highlightNums when all relevant fields are null (coverage mode)", () => {
      const action = planToMapAction(weights({ coverage: 1 }), NULL_ONLY_FC);
      expect(action.highlightNums).toEqual([]);
    });

    it("skips null-field features but includes valid ones", () => {
      const mixedFC: NeighbourhoodFC = {
        type: "FeatureCollection",
        features: [...THREE_FEATURES, NULL_FEATURE],
      };
      const action = planToMapAction(weights({ equity: 1 }), mixedFC);
      expect(action.highlightNums).not.toContain(99); // null feature excluded
      expect(action.highlightNums.length).toBe(3); // only 3 valid ones
    });

    it("returns valid rationale string in all cases", () => {
      const action = planToMapAction(weights({ equity: 1 }), NULL_ONLY_FC);
      expect(typeof action.rationale).toBe("string");
      expect(action.rationale.length).toBeGreaterThan(0);
    });
  });

  describe("empty feature collection", () => {
    it("returns empty highlightNums and still picks a valid viewId", () => {
      const emptyFC: NeighbourhoodFC = { type: "FeatureCollection", features: [] };
      const action = planToMapAction(weights({ equity: 1 }), emptyFC);
      expect(action.highlightNums).toEqual([]);
      expect(action.viewId).toBe("equity-gap");
    });
  });
});
