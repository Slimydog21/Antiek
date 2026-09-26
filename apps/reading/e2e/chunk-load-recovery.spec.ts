/**
 * FFX SPR-01 M2 — P-05 against the production build (`vite preview`).
 *
 * Scenario: a tab loaded before a deploy navigates to /settings, but the
 * Settings chunk it references is gone. On antiek.ai the edge answers a
 * missing /assets/*.js with the SPA HTML (200, text/html, cached immutable),
 * so the browser refuses it as a module; a plain network failure behaves the
 * same way. Before SPR-01 either case unmounted the root: a blank page.
 *
 * Expected: exactly ONE automatic reload (the per-URL sessionStorage guard),
 * then — because the chunk is still unavailable after the reload — the root
 * boundary's new-version copy with a Reload action. Never a blank page (the
 * crawl's predicate: interactive elements > 0).
 *
 * Which file to block: the spec page suggested `**\/assets/Settings-*.js`,
 * but Vite names this chunk `index-<hash>.js` (it is modes/Settings/index.tsx),
 * so that glob would block NOTHING and the test would pass vacuously. The
 * chunk is found instead by a string only the Settings mode renders, and the
 * test fails loudly if that lookup does not find exactly one file.
 *
 * Runs in the `chromium` project with its own baseURL: the default config
 * already boots `vite preview` on :4173 (AMS_BOOTS_PREVIEW) from `dist/`.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { installAuthMock } from "./_ams/auth";

const APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
test.use({ baseURL: APP_BASE });

const DIST_ASSETS = join(dirname(fileURLToPath(import.meta.url)), "..", "dist", "assets");
/** Rendered only by modes/Settings/index.tsx. */
const SETTINGS_MARKER = "Recursive Antiek-bench evolution from usage outcomes";
const STALE_DEPLOY_COPY = "A new version of Antiek was deployed. Reload to continue.";

function settingsChunk(): string {
  const hits = readdirSync(DIST_ASSETS).filter(
    (name) => name.endsWith(".js") && readFileSync(join(DIST_ASSETS, name), "utf8").includes(SETTINGS_MARKER),
  );
  if (hits.length !== 1) {
    throw new Error(
      `expected exactly one Settings chunk in ${DIST_ASSETS}, found ${hits.length} (${hits.join(", ")}); ` +
        "run `npm run build` first",
    );
  }
  return hits[0];
}

async function interactiveCount(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      document.querySelectorAll(
        "a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])",
      ).length,
  );
}

type Breakage = "network-abort" | "html-for-js (P-05)";

for (const breakage of ["network-abort", "html-for-js (P-05)"] as Breakage[]) {
  test(`stale Settings chunk (${breakage}): one reload, then the new-version copy, never a blank page`, async ({ page }) => {
    const chunk = settingsChunk();
    await installAuthMock(page);

    let blocked = 0;
    await page.route(`**/assets/${chunk}`, async (route) => {
      blocked += 1;
      if (breakage === "network-abort") return route.abort("failed");
      // What the Cloudflare Pages edge returns for a missing asset (P-05).
      return route.fulfill({
        status: 200,
        contentType: "text/html",
        headers: { "cache-control": "public, max-age=31536000, immutable" },
        body: "<!doctype html><html><body><div id=\"root\"></div></body></html>",
      });
    });

    let documentLoads = 0;
    page.on("request", (req) => {
      if (req.resourceType() === "document" && req.frame() === page.mainFrame()) documentLoads += 1;
    });

    await page.goto("/settings", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(STALE_DEPLOY_COPY)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Go to Home" })).toHaveAttribute("href", "/home");

    // The guard allowed exactly one automatic reload: goto + 1 reload.
    expect(documentLoads).toBe(2);
    // The chunk was requested before and after that reload.
    expect(blocked).toBeGreaterThanOrEqual(2);
    // The crawl's blank-page predicate.
    expect(await interactiveCount(page)).toBeGreaterThan(0);

    // And it stays put: no further reload loop.
    await page.waitForTimeout(1_500);
    expect(documentLoads).toBe(2);
  });
}

test("a fresh chunk after the reload recovers the page with no message", async ({ page }) => {
  const chunk = settingsChunk();
  await installAuthMock(page);

  // Only the FIRST request fails — the reload fetches it successfully, as it
  // would once the edge stops serving the stale miss.
  let failedOnce = false;
  await page.route(`**/assets/${chunk}`, async (route) => {
    if (!failedOnce) {
      failedOnce = true;
      return route.abort("failed");
    }
    return route.continue();
  });

  let documentLoads = 0;
  page.on("request", (req) => {
    if (req.resourceType() === "document" && req.frame() === page.mainFrame()) documentLoads += 1;
  });

  await page.goto("/settings", { waitUntil: "domcontentloaded" });
  await expect.poll(() => documentLoads, { timeout: 15_000 }).toBe(2);
  await expect(page.getByText(STALE_DEPLOY_COPY)).toHaveCount(0);
  await expect(page.getByText("Something broke on this page.")).toHaveCount(0);
  await expect.poll(() => interactiveCount(page), { timeout: 15_000 }).toBeGreaterThan(0);
});
