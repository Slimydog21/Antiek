/**
 * S6 — PDF-inside-floating-panel performance benchmark.
 *
 * Real Playwright harness. Launches Chromium, opens the
 * `pdf-perf-target` Storybook story (sibling file added in this
 * commit), simulates panel-resize drag + page-scroll, samples
 * `requestAnimationFrame` timestamps to compute fps percentiles.
 *
 * Acceptance per `docs/ui_redesign_posthog/sprint_06_wrestle.html`:
 *   p50 fps ≥ 45
 *   p10 fps ≥ 30
 *
 * Local-only — not run in CI (Playwright + Chromium aren't installed
 * in the sandboxed lint/test image). One-shot operator run:
 *
 *   cd apps/reading
 *   npx playwright install chromium  # ~200 MB; once
 *   npm run storybook                 # other terminal
 *   tsx scripts/bench_pdf_panel.ts
 *
 * Writes a single row to `docs/perf/pdf_panel.md` summarising the
 * run + appending to history.
 */
import { appendFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { argv, exit } from "node:process";

type Args = {
  storybook: string;
  story: string;
  duration_ms: number;
  panel_width: number;
  panel_height: number;
  out: string;
};

const DEFAULTS: Args = {
  storybook: "http://localhost:6006",
  story:
    "/iframe.html?args=&id=loop-2-pdfviewer--pdf-perf-target&viewMode=story",
  duration_ms: 5_000,
  panel_width: 1200,
  panel_height: 900,
  out: "../../docs/perf/pdf_panel.md",
};

function parseArgs(): Args {
  const out = { ...DEFAULTS };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--storybook") out.storybook = argv[++i];
    else if (a === "--story") out.story = argv[++i];
    else if (a === "--duration") out.duration_ms = parseInt(argv[++i], 10);
    else if (a === "--width") out.panel_width = parseInt(argv[++i], 10);
    else if (a === "--height") out.panel_height = parseInt(argv[++i], 10);
    else if (a === "--out") out.out = argv[++i];
  }
  return out;
}

/** Compute the p-th percentile of a numeric array (0 ≤ p ≤ 1). */
function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
  return sorted[idx];
}

async function main() {
  const args = parseArgs();
  const url = args.storybook + args.story;
  console.log("=".repeat(60));
  console.log(" S6 / PDF panel performance benchmark");
  console.log("=".repeat(60));
  console.log(`  storybook : ${args.storybook}`);
  console.log(`  story     : ${args.story}`);
  console.log(`  duration  : ${args.duration_ms} ms`);
  console.log(`  size      : ${args.panel_width}×${args.panel_height}`);
  console.log("");

  // Playwright is required but not installed in CI; the script
  // bootstraps gracefully — if missing, prints the install command +
  // exits 0 so a fresh checkout doesn't fail on `npm test`.
  let chromium: typeof import("playwright").chromium;
  try {
    // dynamic import so missing module doesn't kill the file at parse
    const playwright = await import("playwright");
    chromium = playwright.chromium;
  } catch {
    console.warn(
      "[!] playwright not installed. Run `npm i -D playwright && " +
        "npx playwright install chromium`, then re-run this benchmark.",
    );
    exit(0);
  }

  const browser = await chromium.launch({
    headless: true,
    // GPU compositing on so rAF aligns with real vsync — without
    // this, headless Chromium can falsely report 60 fps because
    // there's no display swap.
    args: ["--enable-gpu-rasterization", "--enable-features=VaapiVideoDecoder"],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "networkidle" });

  // Wait for the story's canvas + the floating panel to mount.
  await page.waitForSelector('[role="region"][aria-label="PDF perf target"]', {
    timeout: 10_000,
  });

  // ── Sampling ─────────────────────────────────────────────
  console.log("[*] sampling rAF frame intervals…");
  // tsx compiles arrow functions + classes to forms that emit `__name`
  // helper references — those don't exist in the browser page context
  // + cause `ReferenceError: __name is not defined` when we pass the
  // function as a closure to page.evaluate. Workaround: pass the
  // sampler as a stringified function so Playwright wraps it itself.
  const SAMPLER_SOURCE = `
    (duration_ms) => {
      var frames = [];
      var start = performance.now();
      var last = start;
      return new Promise(function (resolve) {
        function tick(t) {
          var delta = t - last;
          last = t;
          frames.push(delta);
          if (t - start < duration_ms) {
            requestAnimationFrame(tick);
          } else {
            resolve(frames);
          }
        }
        requestAnimationFrame(tick);
        var panel = document.querySelector(
          '[role="region"][aria-label="PDF perf target"]'
        );
        var scroller = panel && panel.querySelector('.overflow-auto');
        if (scroller) {
          var y = 0;
          var iv = setInterval(function () {
            y += 24;
            scroller.scrollTop = y % scroller.scrollHeight;
          }, 16);
          setTimeout(function () { clearInterval(iv); }, duration_ms);
        }
      });
    }
  `;
  const samples: number[] = await page.evaluate(
    new Function("duration_ms", "return (" + SAMPLER_SOURCE + ")(duration_ms);") as never,
    args.duration_ms,
  );

  await browser.close();

  // ── Analysis ─────────────────────────────────────────────
  // First sample is always huge (cold-start); drop it.
  const intervals = samples.slice(1).filter((d) => d > 0);
  const fps = intervals.map((d) => 1000 / d);
  const p50 = percentile(fps, 0.5);
  const p10 = percentile(fps, 0.1);
  const p99 = percentile(fps, 0.99);
  const min = Math.min(...fps);
  const max = Math.max(...fps);
  const mean = fps.reduce((s, f) => s + f, 0) / fps.length;

  const verdict =
    p50 >= 45 && p10 >= 30 ? "PASS" : "FAIL (acceptance: p50 ≥ 45, p10 ≥ 30)";

  console.log("");
  console.log("=".repeat(60));
  console.log(" Results");
  console.log("=".repeat(60));
  console.log(`  samples : ${fps.length}`);
  console.log(`  p10 fps : ${p10.toFixed(2)}`);
  console.log(`  p50 fps : ${p50.toFixed(2)}`);
  console.log(`  p99 fps : ${p99.toFixed(2)}`);
  console.log(`  mean    : ${mean.toFixed(2)}`);
  console.log(`  min/max : ${min.toFixed(2)} / ${max.toFixed(2)}`);
  console.log(`  verdict : ${verdict}`);

  // Append to the perf log.
  const outPath = join(process.cwd(), args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  const ts = new Date().toISOString();
  const row =
    `| ${ts} | ${args.panel_width}×${args.panel_height} | ` +
    `${p10.toFixed(1)} | ${p50.toFixed(1)} | ${p99.toFixed(1)} | ` +
    `${verdict} |\n`;
  if (!existsSync(outPath)) {
    writeFileSync(
      outPath,
      "# PDF panel benchmark history\n\n" +
        "| timestamp | panel | p10 fps | p50 fps | p99 fps | verdict |\n" +
        "|---|---|---|---|---|---|\n" +
        row,
    );
  } else {
    appendFileSync(outPath, row);
  }
  console.log(`  log     : ${outPath}`);
  exit(verdict.startsWith("PASS") ? 0 : 1);
}

void main();
