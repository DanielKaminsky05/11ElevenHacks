// Verify event markers on the map + click-to-focus from the Alerts tab.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = process.env.MAP_URL ?? "http://localhost:3000";
const log = [];
const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && log.push("ERR: " + m.text()));

await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(5000);

// Count event markers rendered on the map.
const counts = await page.evaluate(() => {
  const m = window.__transitMap;
  if (!m) return null;
  const q = (layer) => (m.getLayer(layer) ? m.queryRenderedFeatures({ layers: [layer] }).length : -1);
  return { closures: q("events-closure"), demand: q("events-demand"), icons: q("events-closure-icon") };
});
log.push("markers: " + JSON.stringify(counts));

await page.screenshot({ path: ".screenshots/events-overview.png" });

// Open the Alerts tab and click the first road-closure card.
await page.locator("button", { hasText: /^Alerts$/ }).first().click().catch(() => {});
await page.waitForTimeout(800);
await page.locator("button", { hasText: /^Disruptions$/ }).first().click().catch(() => {});
await page.waitForTimeout(800);

const beforeZoom = await page.evaluate(() => window.__transitMap?.getZoom() ?? -1);
const card = page.locator("text=/Gardiner Expressway|Road closure/i").first();
await card.click().catch(() => {});
await page.waitForTimeout(2500);
const afterZoom = await page.evaluate(() => window.__transitMap?.getZoom() ?? -1);
const focused = await page.evaluate(() => {
  const m = window.__transitMap;
  if (!m || !m.getLayer("events-focus")) return -1;
  return m.queryRenderedFeatures({ layers: ["events-focus"] }).length;
});
log.push(`zoom ${beforeZoom.toFixed(1)} -> ${afterZoom.toFixed(1)} (flew=${afterZoom > beforeZoom})`);
log.push("focus ring features: " + focused);

await page.screenshot({ path: ".screenshots/events-focused.png" });
log.push("errors: " + (log.filter((l) => l.startsWith("ERR")).length || "none"));
writeFileSync(".screenshots/events-log.txt", log.join("\n") + "\n");
await browser.close();
