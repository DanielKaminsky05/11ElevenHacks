// Programmatic verification of the transit map render.
//
// Loads the running app, probes the DOM (status text, legend, canvas), then
// screenshots and analyzes the pixels to confirm the dark basemap plus the
// route network and stops actually drew. Writes a JSON report to stdout and a
// file, and exits non-zero if any check fails. Catches the class of bug where
// the map mounts but renders into a collapsed (0-height) container.
//
// Usage: node scripts/verify-map.mjs [reportfile]
// Env: MAP_URL (default http://localhost:3000)

import { chromium } from "playwright";
import { PNG } from "pngjs";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const URL = process.env.MAP_URL ?? "http://localhost:3000";
const REPORT = resolve(process.argv[2] ?? ".screenshots/report.json");

// Reference colors from lib/transit.ts.
const TARGETS = {
  background: [0x0a, 0x16, 0x28],
  subway: [0xf8, 0xc3, 0x00],
  streetcar: [0xda, 0x25, 0x1d],
  bus: [0x3f, 0xa7, 0xff],
  stop: [0xff, 0xd6, 0x6b],
};

function near([r, g, b], [tr, tg, tb], tol = 38) {
  return (
    Math.abs(r - tr) <= tol &&
    Math.abs(g - tg) <= tol &&
    Math.abs(b - tb) <= tol
  );
}

// Saturation of an RGB pixel (0..1). Route lines and their glow are vivid,
// while the dark basemap is near-gray, so saturation separates "drew a colored
// network" from "empty/basemap" without depending on exact line colors.
function saturation([r, g, b]) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
}

// Cyan/blue route pixel (the bus network dominates the map). Generous enough to
// catch glow-blended and anti-aliased edges.
function isBlueRoute([r, g, b]) {
  return b > 110 && b - r > 40 && g - r > 10;
}

async function main() {
  const browser = await chromium.launch({
    args: [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });

  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  await page.goto(URL, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForSelector(".maplibregl-canvas", { timeout: 60_000 });
  await page
    .waitForFunction(() => !document.body.innerText.includes("Loading map"), {
      timeout: 30_000,
    })
    .catch(() => {});
  await page.waitForTimeout(6000);

  // --- DOM probes ---
  const dom = await page.evaluate(() => {
    const canvas = document.querySelector(".maplibregl-canvas");
    const text = document.body.innerText;
    const legendButtons = Array.from(
      document.querySelectorAll('[aria-pressed]'),
    ).map((b) => ({
      label: b.textContent?.trim().replace(/\s+/g, " "),
      pressed: b.getAttribute("aria-pressed"),
    }));
    return {
      canvasWidth: canvas?.clientWidth ?? 0,
      canvasHeight: canvas?.clientHeight ?? 0,
      statusLine:
        text.split("\n").find((l) => /routes.*stops/i.test(l))?.trim() ?? null,
      legendButtons,
    };
  });

  // --- Pixel analysis on the composited frame ---
  const buf = await page.screenshot();
  const png = PNG.sync.read(buf);
  const counts = { vivid: 0, blueRoute: 0, stop: 0 };
  const total = png.width * png.height;
  let lumSum = 0;
  for (let i = 0; i < png.data.length; i += 4) {
    const px = [png.data[i], png.data[i + 1], png.data[i + 2]];
    lumSum += (px[0] + px[1] + px[2]) / 3;
    if (near(px, TARGETS.stop, 34)) counts.stop++;
    if (isBlueRoute(px)) counts.blueRoute++;
    if (saturation(px) > 0.45) counts.vivid++; // any saturated network pixel
  }
  const meanLuminance = lumSum / total; // 0..255, dark theme should be low

  const pct = (n) => +((n / total) * 100).toFixed(3);
  const report = {
    url: URL,
    dom,
    pixels: {
      total,
      meanLuminance: +meanLuminance.toFixed(1),
      vividPct: pct(counts.vivid),
      blueRoutePct: pct(counts.blueRoute),
      stopPct: pct(counts.stop),
    },
    consoleErrors,
    checks: {
      canvasFillsViewport: dom.canvasWidth >= 1400 && dom.canvasHeight >= 850,
      statusShowsCounts: /232 routes/.test(dom.statusLine ?? ""),
      fourLegendToggles: dom.legendButtons.length === 4,
      // Dark theme: the frame should be dim on average (basemap + background).
      backgroundIsDark: meanLuminance < 90,
      routesDrew: pct(counts.blueRoute) > 0.3,
      // Bus stops are tiny dots (~1.3px) at the default zoom, so even ~9k of
      // them cover little area; a small but non-trivial footprint is expected.
      stopsDrew: pct(counts.stop) > 0.01,
      noConsoleErrors: consoleErrors.length === 0,
    },
  };
  report.pass = Object.values(report.checks).every(Boolean);

  writeFileSync(REPORT, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
  process.exit(report.pass ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
