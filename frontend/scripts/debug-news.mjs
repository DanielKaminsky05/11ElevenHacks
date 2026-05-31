import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = "http://localhost:3000";
const log = [];
const browser = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => log.push(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => log.push("PAGEERROR: " + String(e)));

await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(5000);

// Direct fetch from inside the page to see what /api/events returns.
const apiResult = await page.evaluate(async () => {
  try {
    const r = await fetch("/api/events");
    return { status: r.status, body: (await r.text()).slice(0, 200) };
  } catch (e) {
    return { error: String(e) };
  }
});
log.push("FETCH /api/events: " + JSON.stringify(apiResult));

// Is the news-feed DOM present at all?
const dom = await page.evaluate(() => {
  const all = document.body.innerText;
  return {
    hasServiceAlerts: all.includes("Service alerts"),
    hasLoadingAlerts: all.includes("Loading alerts"),
    bodyTextSample: all.slice(0, 300),
  };
});
log.push("DOM: " + JSON.stringify(dom));

writeFileSync(".screenshots/debug-news.txt", log.join("\n") + "\n");
await browser.close();
