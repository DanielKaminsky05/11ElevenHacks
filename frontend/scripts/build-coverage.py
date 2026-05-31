"""Transit coverage analyzer: what share of each neighbourhood's population is
within walking distance of a transit stop, and where are the gaps?

Method:
  - lay a fine grid (STEP_M) over the city
  - assign each cell to the neighbourhood polygon it falls in
  - distribute neighbourhood population uniformly across its cells
  - a cell is "covered" if a transit stop is within WALK_M (great-circle)
  - coverage_i = covered_cells_i / total_cells_i  (=> served_pop = pop * coverage)

Inputs : frontend/public/neighbourhoods.json, frontend/public/network.json
Output : frontend/public/coverage.json  { byNum, grid, meta }

Run:  python frontend/scripts/build-coverage.py
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "public")
HOODS = os.path.join(PUB, "neighbourhoods.json")
NET = os.path.join(PUB, "network.json")
OUT = os.path.join(PUB, "coverage.json")

WALK_M = 400      # walking distance to a stop (m) — standard bus catchment
STEP_M = 200      # grid resolution (m)
LAT0 = 43.72

MX = 111320.0 * math.cos(math.radians(LAT0))  # m per degree lon (local)
MY = 110574.0                                  # m per degree lat


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def pip_ring(x, y, ring):
    inside = False
    n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_in_poly(x, y, polygons):
    for rings in polygons:
        if pip_ring(x, y, rings[0]) and not any(pip_ring(x, y, h) for h in rings[1:]):
            return True
    return False


# --- load neighbourhoods, normalize to list-of-polygons + bbox ---
with open(HOODS, encoding="utf-8") as f:
    gj = json.load(f)
hoods = []
for feat in gj["features"]:
    p = feat["properties"]
    if not p.get("pop"):
        continue
    g = feat["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    xs = [pt[0] for poly in polys for pt in poly[0]]
    ys = [pt[1] for poly in polys for pt in poly[0]]
    hoods.append({
        "num": p["num"], "name": p["name"], "pop": p["pop"],
        "polys": polys, "bbox": (min(xs), min(ys), max(xs), max(ys)),
        "total": 0, "covered": 0,
    })
print(f"neighbourhoods: {len(hoods)}")

# --- transit stops (any mode) -> spatial hash ---
# Use ALL transit stops: a rider served by streetcar/subway is not in a desert.
with open(NET, encoding="utf-8") as f:
    net = json.load(f)
transit_stops = [(lo, la) for (la, lo, nm, m, *_) in net["stops"] if m]
print(f"transit stops (any mode): {len(transit_stops)}")

stop_bins = {}
for lo, la in transit_stops:
    key = (int(lo * MX / WALK_M), int(la * MY / WALK_M))
    stop_bins.setdefault(key, []).append((lo, la))


def has_stop_within(lo, la):
    bx, by = int(lo * MX / WALK_M), int(la * MY / WALK_M)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for slo, sla in stop_bins.get((bx + dx, by + dy), ()):
                if haversine_m(lo, la, slo, sla) <= WALK_M:
                    return True
    return False


# --- grid sweep over the city bounding box ---
gminx = min(h["bbox"][0] for h in hoods); gmaxx = max(h["bbox"][2] for h in hoods)
gminy = min(h["bbox"][1] for h in hoods); gmaxy = max(h["bbox"][3] for h in hoods)
dlon = STEP_M / MX; dlat = STEP_M / MY

grid = []
ncells = 0
lat = gminy
while lat <= gmaxy:
    lon = gminx
    while lon <= gmaxx:
        host = None
        for h in hoods:
            bb = h["bbox"]
            if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and point_in_poly(lon, lat, h["polys"]):
                host = h
                break
        if host is not None:
            ncells += 1
            cov = 1 if has_stop_within(lon, lat) else 0
            host["total"] += 1
            host["covered"] += cov
            grid.append([round(lon, 5), round(lat, 5), cov])
        lon += dlon
    lat += dlat
print(f"in-city grid cells: {ncells}")

# --- aggregate ---
by_num = {}
served_total = pop_total = gap_total = 0
for h in hoods:
    cov = (h["covered"] / h["total"]) if h["total"] else 0.0
    served = h["pop"] * cov
    gap = h["pop"] - served
    by_num[str(h["num"])] = {
        "cov": round(cov * 100, 1),
        "served": round(served),
        "gap": round(gap),
    }
    served_total += served; pop_total += h["pop"]; gap_total += gap

meta = {
    "walkM": WALK_M, "stepM": STEP_M,
    "citywideCoverage": round(100 * served_total / pop_total, 1),
    "gapPopulation": round(gap_total),
    "gridCells": ncells,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"byNum": by_num, "grid": grid, "meta": meta}, f, separators=(",", ":"))

worst = sorted(by_num.items(), key=lambda kv: kv[1]["cov"])[:8]
name_by_num = {str(h["num"]): h["name"] for h in hoods}
print(f"wrote {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
print(f"  citywide coverage: {meta['citywideCoverage']}%  (gap: {meta['gapPopulation']:,} people)")
print("  least-covered neighbourhoods:")
for num, v in worst:
    print(f"    {v['cov']:5.1f}%  {name_by_num[num]}  (gap {v['gap']:,})")
