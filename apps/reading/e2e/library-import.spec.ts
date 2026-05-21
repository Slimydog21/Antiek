// SPR-06 / M6 — End-to-end test scaffolding for the library import
// cycle: log in as a new user → land at /library → paste URL → wait
// for the import to finish → card appears → click → /wrestle/<id>.
//
// =============================================================
// HONESTY NOTE (per rigor #1 + the verification gate caveats):
// =============================================================
//
// The reading app does NOT have a Playwright / Cypress runner wired
// in at SPR-06 closeout — `package.json` exposes `pnpm test`
// (Vitest) and `pnpm storybook` only; there is no `pnpm e2e`
// script and no installed E2E browser driver. The sprint HTML page
// named this file and the `pnpm e2e library-import.spec.ts` command
// in its verification table; the file path is honored here so a
// future sprint that wires the runner has the scenario laid out,
// but the gate is NOT executable as named today.
//
// The file is intentionally Playwright-shaped (the most common
// React/Vite E2E choice and matches Antiek's elsewhere-stated
// conventions). When a runner lands the only change needed is to
// register this file in the runner's config and import the actual
// `@playwright/test` package; the scenario steps below are
// runner-ready.
//
// Surfaced in the handoff packet under "E2E pass: fail (runner
// not present)" — we don't claim a pass we can't demonstrate.
// =============================================================

// Type-only stub so the file compiles in the vite/vitest tree
// without Playwright installed. Replace with:
//   import { test, expect } from "@playwright/test";
// once the runner is added.
type TestFn = (name: string, fn: (ctx: PlaywrightContext) => Promise<void>) => void;
interface Locator {
  click(): Promise<void>;
  fill(value: string): Promise<void>;
  waitFor(opts?: { state?: "visible" | "hidden"; timeout?: number }): Promise<void>;
  textContent(): Promise<string | null>;
}
interface Page {
  goto(url: string): Promise<void>;
  url(): string;
  locator(selector: string): Locator;
  waitForURL(pattern: string | RegExp, opts?: { timeout?: number }): Promise<void>;
  evaluate<R>(fn: () => R): Promise<R>;
}
interface PlaywrightContext {
  page: Page;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const test: TestFn & { describe: (name: string, fn: () => void) => void };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const expect: any;

test.describe("SPR-06 — universal library import cycle", () => {
  test("new user paste → import → card → open", async ({ page }) => {
    // 1. Sign in as a fresh user. The dev server's auth bypass
    //    returns __operator__ with no session cookie required; in
    //    staging we'd POST /auth/request and click the magic link.
    await page.goto("http://localhost:5173/login");

    // 2. With no last-opened doc on this device, RequireAuth +
    //    resolvePostLoginDestination should send us to /library
    //    (the new-user wedge landing).
    await page.evaluate(() => {
      // Ensure a clean device state — no prior last-opened.
      window.localStorage.removeItem("antiek.lastOpenedDocumentId.v1");
      window.localStorage.removeItem("antiek.userSettings.v1");
    });
    await page.goto("http://localhost:5173/");
    await page.waitForURL(/\/library/, { timeout: 5000 });

    // 3. Empty-state should be visible — three suggestions + the
    //    paste bar.
    await page.locator('[data-testid="library-empty-state"]').waitFor({ state: "visible" });

    // 4. Paste a URL into the paste bar and submit.
    await page.locator('[data-testid="url-paste-input"]').fill(
      "https://paulgraham.com/cities.html",
    );
    await page.locator('[data-testid="url-paste-submit"]').click();

    // 5. ImportProgress should appear and run through phases until
    //    it reaches "ready". The pipeline runs in a daemon thread on
    //    the backend; the test waits with a generous timeout.
    await page
      .locator('[data-testid="import-progress"][data-phase="ready"]')
      .waitFor({ state: "visible", timeout: 60_000 });

    // 6. A new card should appear in the grid.
    const card = page.locator('[data-testid="library-card"]').first();
    await card.waitFor({ state: "visible", timeout: 5000 });

    // 7. Click the card → /wrestle/<id>.
    await card.click();
    await page.waitForURL(/\/wrestle\//, { timeout: 5000 });
    expect(page.url()).toMatch(/\/wrestle\/doc-/);
  });

  test("paywalled HTML article surfaces a partial tag (rigor #1)", async ({ page }) => {
    // Use a URL the SPR-03 paywall heuristic recognises (NYT-style
    // content is what html_extractor sets paywalled=true on; staging
    // uses a fixture URL whose paywalled flag is forced).
    await page.goto("http://localhost:5173/library");
    await page.locator('[data-testid="url-paste-input"]').fill(
      // Replace with whichever URL the staging fixture marks
      // paywalled. The component's contract: if metadata.paywalled
      // is true on the listing response, the partial tag renders.
      "https://www.nytimes.com/2024/01/01/example-paywalled",
    );
    await page.locator('[data-testid="url-paste-submit"]').click();
    await page
      .locator('[data-testid="import-progress"][data-phase="ready"]')
      .waitFor({ state: "visible", timeout: 60_000 });

    // The library card for the new doc should carry the paywall tag.
    const paywallTag = page.locator('[data-testid="library-card-paywall-tag"]').first();
    await paywallTag.waitFor({ state: "visible", timeout: 5000 });
  });

  test("folder filter narrows the grid", async ({ page }) => {
    await page.goto("http://localhost:5173/library");

    // Create a folder via the sidebar affordance.
    await page.locator('[data-testid="library-sidebar-new-folder"]').click();
    await page.locator('[data-testid="library-sidebar-folder-input"]').fill("To Read");
    // Press Enter to commit.
    await page.evaluate(() => {
      const el = document.querySelector<HTMLInputElement>(
        '[data-testid="library-sidebar-folder-input"]',
      );
      el?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });

    // Click the new folder to filter the grid.
    const folderBtn = page.locator('[data-testid="library-sidebar-folder"]').first();
    await folderBtn.click();
    // Grid should report the folder filter is active.
    const grid = page.locator('[data-testid="library-grid-root"]');
    expect(await grid.textContent()).toContain("To Read");
  });
});

// Suppress no-unused warnings for the type-only shims above.
void test;
void expect;
