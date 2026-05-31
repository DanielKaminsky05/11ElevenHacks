// Open a choropleth view and click a neighbourhood to capture a themed popup.
// Usage: node scripts/shoot-popup.mjs <outfile>
import { chromium } from "playwright";

const out = process.argv[2] ?? ".screenshots/popup.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4000);

// Activate a choropleth view (big click targets).
await page.locator("label", { hasText: "People & need" }).first().click();
await page.waitForTimeout(2000);

// Click near map center to hit a neighbourhood polygon.
await page.mouse.click(720, 460);
await page.waitForTimeout(1500);

const hasPopup = await page.locator(".maplibregl-popup-content").count();
console.log("popup present:", hasPopup);
await page.screenshot({ path: out });
console.log("saved", out);
await browser.close();
