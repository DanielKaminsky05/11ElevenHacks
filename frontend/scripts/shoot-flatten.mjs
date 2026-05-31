// Activate a choropleth view and verify the camera auto-flattens to 2D.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const out = process.argv[2] ?? ".screenshots/flatten.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";
const log = [];

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4500);

const pitchBefore = await page.evaluate(() => window.__transitMap?.getPitch() ?? -1);
log.push("pitch before (expect ~58): " + pitchBefore.toFixed(1));

// Activate a choropleth via the view switcher.
await page.locator("label", { hasText: "Marginalization" }).first().click();
await page.waitForTimeout(1800);

const pitchAfter = await page.evaluate(() => window.__transitMap?.getPitch() ?? -1);
log.push("pitch after view active (expect ~0): " + pitchAfter.toFixed(1));
log.push("auto-flattened: " + (pitchBefore > 30 && pitchAfter < 5));

await page.screenshot({ path: out });
log.push("saved " + out);
writeFileSync(".screenshots/flatten-log.txt", log.join("\n") + "\n");
await browser.close();
