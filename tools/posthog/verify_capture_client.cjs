#!/usr/bin/env node
/**
 * Local-only client-side capture proof (Antiek — APH SPR-02, secondary).
 *
 * The PRIMARY verifier is verify_capture.py (server-side, bot-filter-immune).
 * This script is the SECONDARY, local-only way to *watch* client capture fire
 * in an automated browser — which normally CANNOT happen, because posthog-js
 * bot-filters Playwright (headless and headed) and drops all /i/v0/e/. The only
 * legitimate way to see client capture in automation is to disable that filter,
 * and that is acceptable ONLY in a LOCAL dev build — NEVER in production
 * (it would pollute real analytics with bot traffic). See INV-1 /
 * docs/decisions/posthog-bot-filter.md.
 *
 * Usage:
 *   1. In a LOCAL dev build only, set `opt_out_useragent_filter: true` in the
 *      posthog.init config (apps/reading/src/lib/posthogClient.ts) — DO NOT
 *      COMMIT this — and start the dev server with the project token in
 *      .env.local.
 *   2. node verify_capture_client.cjs http://localhost:5173/
 *
 * It loads the URL, drives a navigation, and asserts ≥1 POST to
 * eu.i.posthog.com/i/v0/e/ (or /e/). It REFUSES any non-localhost URL — this
 * mode must never run against prod, where the bot filter is correct and the
 * absence of capture is expected, not a defect.
 *
 * Exit: 0 = client capture observed; 2 = refused (non-localhost); 1 = not
 * observed (check that the local opt-out flag is actually set).
 */
const PLAYWRIGHT = "/Users/slimydog/Desktop/Antiek/apps/reading/node_modules/playwright";

function isLocal(u) {
  try {
    const h = new URL(u).hostname;
    return h === "localhost" || h === "127.0.0.1" || h === "[::1]" || h === "::1";
  } catch {
    return false;
  }
}

async function main() {
  const url = process.argv[2];
  if (!url) {
    console.error("usage: node verify_capture_client.cjs http://localhost:5173/");
    return 2;
  }
  if (!isLocal(url)) {
    console.error(
      `[verify_capture_client] REFUSING to run against non-localhost URL: ${url}\n` +
      `This mode requires opt_out_useragent_filter:true, which is LOCAL-ONLY — running it against\n` +
      `prod would pollute real analytics with bot traffic. In prod, zero client capture from an\n` +
      `automated browser is the bot filter working correctly (INV-1), not a defect. Use\n` +
      `verify_capture.py (server-side) to verify prod.`,
    );
    return 2;
  }
  const { chromium } = require(PLAYWRIGHT);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const captures = [];
  page.on("request", (r) => {
    const u = r.url();
    if (u.includes("posthog.com") && /\/(i\/v0\/e|e)\b|\/e\//.test(u.replace(/^https?:\/\/[^/]+/, "").split("?")[0])) {
      captures.push(u.split("?")[0].replace(/^https?:\/\/[^/]+/, ""));
    }
  });
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(4000);
    await page.evaluate(() => history.pushState({}, "", "/read?aph=verify")).catch(() => {});
    await page.waitForTimeout(6000);
  } finally {
    await browser.close();
  }
  if (captures.length > 0) {
    console.log(`[verify_capture_client] PASS — observed ${captures.length} client capture POST(s): ${[...new Set(captures)].join(", ")}`);
    console.log("[verify_capture_client] (only meaningful because the LOCAL build set opt_out_useragent_filter:true)");
    return 0;
  }
  console.log(
    "[verify_capture_client] no client /i/v0/e/ observed. Either the local build did NOT set\n" +
    "opt_out_useragent_filter:true (so posthog bot-filtered this automated browser — expected), or the\n" +
    "token isn't configured locally. This is NOT proof analytics is broken — verify_capture.py (server-side) is.",
  );
  return 1;
}

main().then((c) => process.exit(c));
