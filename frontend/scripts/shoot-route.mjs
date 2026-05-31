// Click a route line and screenshot the selection + details panel.
// Writes a diagnostic log to .screenshots/route-log.txt (harness stdout isn't
// always visible to the caller).
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const out = process.argv[2] ?? ".screenshots/route.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";
const log = [];
const say = (...a) => log.push(a.join(" "));

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && say("PAGEERR:", m.text()));
page.on("pageerror", (e) => say("PAGEERR:", String(e)));

await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4500);

const hasMap = await page.evaluate(() => Boolean(window.__transitMap));
say("window.__transitMap present:", hasMap);

await page.evaluate(() => {
  const map = window.__transitMap;
  if (map) map.easeTo({ pitch: 0, bearing: 0, zoom: 14, center: [-79.385, 43.66], duration: 0 });
});
await page.waitForTimeout(2500);

const pt = await page.evaluate(() => {
  const map = window.__transitMap;
  if (!map) return null;
  const center = map.project(map.getCenter());
  for (const layer of ["subway-line", "streetcar-line", "bus-line"]) {
    if (!map.getLayer(layer)) continue;
    const feats = map.queryRenderedFeatures({ layers: [layer] });
    let best = null, bestD = Infinity;
    for (const f of feats) {
      const g = f.geometry;
      const lines = g.type === "LineString" ? [g.coordinates] : g.coordinates;
      for (const ln of lines) for (const co of ln) {
        const p = map.project(co);
        const d = (p.x - center.x) ** 2 + (p.y - center.y) ** 2;
        if (d < bestD) { bestD = d; best = { x: Math.round(p.x), y: Math.round(p.y), layer, short: f.properties.short }; }
      }
    }
    if (best) return best;
  }
  return null;
});
say("target:", JSON.stringify(pt));

if (pt) {
  for (const [dx, dy] of [[0, 0], [2, 0], [-2, 0], [0, 2], [0, -2], [3, 3]]) {
    await page.mouse.click(pt.x + dx, pt.y + dy);
    await page.waitForTimeout(500);
    if (await page.locator("text=isolated").count()) { say("hit at offset", dx, dy); break; }
  }
}

say("details panel present:", await page.locator("text=isolated").count());
await page.screenshot({ path: out });
say("saved:", out);
writeFileSync(".screenshots/route-log.txt", log.join("\n") + "\n");
await browser.close();
