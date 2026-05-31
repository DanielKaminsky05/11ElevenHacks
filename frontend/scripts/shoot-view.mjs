// Screenshot a specific overlay view by clicking its switcher radio, then
// optionally selecting a sub-metric. Usage:
//   node scripts/shoot-view.mjs <viewLabel> <outfile> [optionLabel]
import { chromium } from "playwright";

const [, , viewLabel, outFile, optionLabel] = process.argv;
const URL = process.env.MAP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4000);

// Click the radio whose label text matches viewLabel.
const label = page.locator("label", { hasText: viewLabel }).first();
await label.click();
await page.waitForTimeout(1500);

if (optionLabel) {
  await page.selectOption("select", { label: optionLabel }).catch(() => {});
  await page.waitForTimeout(1200);
}
await page.waitForTimeout(2500);
await page.screenshot({ path: outFile });
console.log("saved", outFile);
await browser.close();
