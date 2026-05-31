// Submit a planner goal and verify the map reacts (view switches + camera flies).
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const out = process.argv[2] ?? ".screenshots/planner.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";
const log = [];

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && log.push("ERR: " + m.text()));
page.on("pageerror", (e) => log.push("ERR: " + e));

await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4500);

const before = await page.evaluate(() => {
  const m = window.__transitMap;
  return m ? { zoom: +m.getZoom().toFixed(2), center: m.getCenter() } : null;
});
log.push("before: " + JSON.stringify(before));

// Click an equity example-goal chip in the planner.
const chip = page.locator("button", { hasText: "most marginalized neighbourhoods" }).first();
await chip.click();
await page.waitForTimeout(3500); // allow API + fitBounds animation

const after = await page.evaluate(() => {
  const m = window.__transitMap;
  return m ? { zoom: +m.getZoom().toFixed(2), center: m.getCenter() } : null;
});
log.push("after: " + JSON.stringify(after));

// Is a choropleth view now active? The equity legend title should appear.
const equityActive = await page.locator("text=/Equity-weighted coverage gap/i").count();
log.push("equity legend visible: " + equityActive);
const moved = before && after && (before.zoom !== after.zoom ||
  Math.abs(before.center.lng - after.center.lng) > 0.001 ||
  Math.abs(before.center.lat - after.center.lat) > 0.001);
log.push("camera moved: " + moved);

await page.screenshot({ path: out });
log.push("saved " + out);
writeFileSync(".screenshots/planner-log.txt", log.join("\n") + "\n");
await browser.close();
