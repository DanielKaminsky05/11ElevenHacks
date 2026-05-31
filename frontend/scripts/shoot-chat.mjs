// Screenshot the planner chat after sending a goal. Usage:
//   node scripts/shoot-chat.mjs <outfile>
import { chromium } from "playwright";

const out = process.argv[2] ?? ".screenshots/chat.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(3500);

// Click the first example-goal chip.
const chip = page.locator("button", { hasText: "low-income neighbourhoods in Scarborough" }).first();
await chip.click();
await page.waitForTimeout(2500);

await page.screenshot({ path: out });
console.log("saved", out);
await browser.close();
