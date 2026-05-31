// Zoom in and screenshot to verify neighbourhood labels appear closeish.
import { chromium } from "playwright";

const out = process.argv[2] ?? ".screenshots/zoom.png";
const zoom = Number(process.argv[3] ?? 13);
const URL = process.env.MAP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4000);

await page.evaluate((z) => {
  const map = window.__transitMap;
  if (map) map.easeTo({ center: [-79.39, 43.66], zoom: z, pitch: 0, duration: 0 });
}, zoom);
await page.waitForTimeout(4000);

const labels = await page.evaluate(() => {
  const map = window.__transitMap;
  return map ? map.queryRenderedFeatures({ layers: ["nbhd-labels-layer"] }).length : -1;
});
console.log(`zoom ${zoom}: rendered labels =`, labels);
await page.screenshot({ path: out });
console.log("saved", out);
await browser.close();
