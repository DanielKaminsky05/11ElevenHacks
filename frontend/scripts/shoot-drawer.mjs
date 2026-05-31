// Click a neighbourhood polygon and screenshot the detail drawer.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const out = process.argv[2] ?? ".screenshots/drawer.png";
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
await page.waitForTimeout(5000);

// Click the centre of the viewport (a neighbourhood polygon, away from a line).
const target = await page.evaluate(() => {
  const map = window.__transitMap;
  if (!map) return null;
  // pick a spot offset from center to avoid a route line
  const c = map.project(map.getCenter());
  return { x: Math.round(c.x) - 120, y: Math.round(c.y) + 90 };
});
log.push("clicking " + JSON.stringify(target));
if (target) {
  await page.mouse.click(target.x, target.y);
  await page.waitForTimeout(1200);
}

// Look for the drawer (a heading that is a neighbourhood name + a known section label).
const hasDrawer = await page.locator("text=/Marginalization|Snapshot|Mobility|Top occupations/i").count();
log.push("drawer sections found: " + hasDrawer);
await page.screenshot({ path: out });
log.push("saved " + out);
writeFileSync(".screenshots/drawer-log.txt", log.join("\n") + "\n");
await browser.close();
