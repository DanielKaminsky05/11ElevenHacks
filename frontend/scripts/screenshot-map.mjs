// Screenshot harness for the transit map.
//
// Launches headless Chromium (WebGL via SwiftShader), loads the running app,
// waits for the MapLibre canvas to settle, and writes a PNG. Used to eyeball
// the map without a manual browser.
//
// Usage:
//   node scripts/screenshot-map.mjs [outfile]
// Env:
//   MAP_URL    target URL (default http://localhost:3000)
//   MAP_WIDTH  viewport width  (default 1440)
//   MAP_HEIGHT viewport height (default 900)
//   MAP_SETTLE extra settle ms after network idle (default 5000)

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const URL = process.env.MAP_URL ?? "http://localhost:3000";
const WIDTH = Number(process.env.MAP_WIDTH ?? 1440);
const HEIGHT = Number(process.env.MAP_HEIGHT ?? 900);
const SETTLE = Number(process.env.MAP_SETTLE ?? 5000);
const SCALE = Number(process.env.MAP_SCALE ?? 1);
const OUT = resolve(process.argv[2] ?? ".screenshots/map.png");

async function main() {
  await mkdir(dirname(OUT), { recursive: true });

  const browser = await chromium.launch({
    // SwiftShader gives software WebGL in headless mode so the map actually
    // renders rather than showing a blank canvas.
    args: [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });

  const page = await browser.newPage({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: SCALE,
  });

  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  console.log(`Loading ${URL} …`);
  await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });

  // The map is lazy-loaded; wait for the canvas to mount, then for the
  // loading fallback to disappear.
  await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
  await page
    .waitForFunction(() => !document.body.innerText.includes("Loading map"), {
      timeout: 30_000,
    })
    .catch(() => {});

  // Let tiles, glyphs and the custom layers finish drawing.
  await page.waitForTimeout(SETTLE);

  await page.screenshot({ path: OUT });
  console.log(`Saved ${OUT}`);
  if (consoleErrors.length) {
    console.log(`Console errors (${consoleErrors.length}):`);
    for (const e of consoleErrors.slice(0, 20)) console.log(`  - ${e}`);
  } else {
    console.log("No console errors.");
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
