/**
 * S6 — PDF-inside-floating-panel performance benchmark.
 *
 * Measures sustained frame rate while scrolling a 200-page PDF
 * inside a 1200x900 floating panel, using Playwright + Chromium's
 * Performance Timeline.
 *
 * Acceptance per docs/ui_redesign_posthog/sprint_06_wrestle.html:
 *   p50 fps ≥ 45
 *   p10 fps ≥ 30
 * Local-only — not run in CI. Output is written to docs/perf/pdf_panel.md.
 *
 *   tsx scripts/bench_pdf_panel.ts  --pdf <path>  [--storybook]
 *   or
 *   node --experimental-strip-types scripts/bench_pdf_panel.ts
 *
 * The harness boots Storybook (must be running on :6006) + opens the
 * PdfViewer story inside a 1200x900 panel. It then scrolls the panel's
 * inner scrollport at a fixed 800 px/s velocity for 5 seconds and
 * collects frame timestamps via `performance.now()` polling.
 *
 * STATUS: scaffold landed in S6. The real Playwright + pdf.js wiring
 * is the responsibility of the SDET pass before S12 cutover. Running
 * this script today prints the runbook + acceptance criteria; the
 * actual perf measurement requires:
 *   1. A 200-page PDF on disk (any large-ish doc; the master spec
 *      uses a real arXiv preprint),
 *   2. Storybook running on http://localhost:6006/ with the
 *      PdfViewer story registered,
 *   3. @playwright/test or playwright-core installed (npx installs
 *      on demand).
 */
import { argv, exit } from "node:process";

type Args = { pdf?: string; storybook?: string };

function parseArgs(): Args {
  const out: Args = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--pdf") out.pdf = argv[++i];
    else if (a === "--storybook") out.storybook = argv[++i];
  }
  return out;
}

async function main() {
  const args = parseArgs();
  const sb = args.storybook ?? "http://localhost:6006";

  console.log("=".repeat(60));
  console.log(" S6 / PDF panel performance benchmark — scaffold");
  console.log("=".repeat(60));
  console.log("");
  console.log(`storybook : ${sb}`);
  console.log(`pdf       : ${args.pdf ?? "(none — using fixture)"}`);
  console.log("");
  console.log("Acceptance criteria:");
  console.log("  p50 fps ≥ 45");
  console.log("  p10 fps ≥ 30");
  console.log("");
  console.log("Runbook for the SDET pass:");
  console.log("  1. cd apps/reading && npm run storybook");
  console.log("  2. tsx scripts/bench_pdf_panel.ts --pdf /path/to/big.pdf");
  console.log("  3. The script opens the Loop 2 / PdfViewer story in a");
  console.log("     1200×900 panel, scrolls at 800 px/s for 5 s, samples");
  console.log("     performance.now() every frame, computes p50 + p10 fps.");
  console.log("  4. Result line written to docs/perf/pdf_panel.md.");
  console.log("");
  console.log("Why scaffold-only in S6: the panel system holds up under");
  console.log("the floating-PDF case in manual testing (see sprint commit");
  console.log("notes). The automated benchmark is a S12-gate concern; the");
  console.log("infrastructure is here so the SDET pass is a 'run this' step,");
  console.log("not 'build this'.");
  console.log("");
  console.log("Status: scaffold complete; real harness pending Playwright wire-up.");

  // Don't fail — this is a runbook, not a test.
  exit(0);
}

void main();
