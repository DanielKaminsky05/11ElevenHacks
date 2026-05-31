// Screenshot each tab of the unified control panel.
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
await page.waitForTimeout(4500);

async function shot(tab, file) {
  await page.locator("button", { hasText: new RegExp("^" + tab + "$") }).first().click().catch(() => {});
  await page.waitForTimeout(1200);
  await page.screenshot({ path: file });
  log.push(`${tab}: saved ${file}`);
}

await shot("Network", ".screenshots/panel-network.png");
await shot("Data", ".screenshots/panel-data.png");
await shot("Alerts", ".screenshots/panel-alerts.png");

log.push("panel present: " + (await page.locator("text=TransitRL").count()));
writeFileSync(".screenshots/panel-log.txt", log.join("\n") + "\n");
await browser.close();
