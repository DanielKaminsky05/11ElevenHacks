// Screenshot the app and verify the news feed rendered its events.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const out = process.argv[2] ?? ".screenshots/news.png";
const URL = process.env.MAP_URL ?? "http://localhost:3000";
const log = [];

const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && log.push("ERR: " + m.text()));

await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
await page.waitForTimeout(4000);

const header = await page.locator("text=/Service alerts/i").count();
log.push("news header present: " + header);
// Click the "Disruptions" filter and count event cards.
await page.locator("button", { hasText: "Disruptions" }).first().click().catch(() => {});
await page.waitForTimeout(800);
const roadCards = await page.locator("text=/Road closure|Gardiner/i").count();
log.push("road-closure cards visible: " + roadCards);

await page.screenshot({ path: out });
log.push("saved " + out);
writeFileSync(".screenshots/news-log.txt", log.join("\n") + "\n");
await browser.close();
