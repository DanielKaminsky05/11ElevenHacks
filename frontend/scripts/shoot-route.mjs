// Click route lines on the map and screenshot the selection + details panel.
import { chromium } from "playwright";

const out = process.argv[2] ?? ".screenshots/route.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(5000);

// Click a few spots likely to hit subway/streetcar lines near the core.
const spots = [[720, 360], [700, 470], [760, 430], [680, 420]];
for (const [x, y] of spots) {
  await page.mouse.click(x, y);
  await page.waitForTimeout(700);
}
await page.waitForTimeout(1500);
const hasPanel = await page.locator("text=isolated").count();
console.log("details panel present:", hasPanel);
await page.screenshot({ path: out });
console.log("saved", out);
await browser.close();
