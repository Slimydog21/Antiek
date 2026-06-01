/**
 * hotkeys-command-scheme.spec.ts — the SPR-08 EXPERIENCE GATE (RULE 2: the
 * proof is pressing the keys in a REAL browser, not a green vitest).
 *
 * Belongs to the `ams-real` Playwright project: it loads the REAL authed SPA
 * via loginAndGotoApp (mocked /auth/me at the network layer — no app-code
 * auth bypass) and exercises the uniform ⌘+key scheme exactly as the operator
 * would. Four assertions, each a real keypress against the real page:
 *
 *   (a) press ⌘+<key> for a product  → the URL/route changes to that product;
 *   (b) the old vim chord is DEAD     → type "g" then "i": the route is unchanged;
 *   (c) press "?"                     → the ⌘ HUD opens, ⌘-only, NO "then" and
 *                                       NO "Go to (chords)" group;
 *   (d) assign a custom ⌘+key, RELOAD, press it → still navigates (the
 *                                       persisted binding survives a reload).
 *
 * On a sandbox with no served SPA the `ams-real` project skips cleanly per the
 * harness RULE 3; SPR runs with a built SPA + AMS_APP_URL (or the vite-preview
 * webServer) make these genuinely red/green.
 *
 * NOTE on the modifier in Playwright: `page.keyboard.press("Meta+e")` sends
 * the Cmd modifier; the app's `isMod` matches metaKey OR ctrlKey, so this
 * drives the real ⌘E path. We use one product (Read → /library) for (a) and a
 * custom ⌥-combo (Alt+;) for (d) so it can't collide with a built-in/product.
 */

import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

/** The default authed route the operator lands on. */
const DEFAULT_ROUTE = "/";

/** The custom-hotkeys localStorage key (workspace/persistence.ts). */
const CUSTOM_HOTKEYS_KEY = "antiek.workspace.custom-hotkeys";

test.describe("SPR-08 — uniform ⌘+key command scheme (real browser)", () => {
  // (a) A product ⌘+key changes the route to that product. ⌘E → Read (/library).
  test("(a) ⌘E navigates to the Read product route", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // Take focus off any field so the global handler (not an input) sees it.
    await page.locator("body").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("Meta+e");
    await expect(page).toHaveURL(/\/library(\/|$|\?)/, { timeout: 5_000 });
  });

  // (b) The old vim chord is dead: "g" then "i" must NOT navigate anywhere.
  test("(b) the old g-chord does nothing (g then i → route unchanged)", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await page.locator("body").click({ position: { x: 4, y: 4 } });
    const before = new URL(page.url()).pathname;
    await page.keyboard.press("g");
    await page.keyboard.press("i");
    // Give any (defunct) chord window time to elapse — it must still be inert.
    await page.waitForTimeout(900);
    const after = new URL(page.url()).pathname;
    expect(
      after,
      `g then i changed the route from ${before} to ${after} — a chord is still alive`,
    ).toBe(before);
  });

  // (c) Pressing "?" opens the ⌘ HUD; it is ⌘-only (no "then", no chord group).
  test('(c) "?" opens a ⌘-only HUD with no "then" and no "Go to (chords)" group', async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await page.locator("body").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("?");

    const hud = page.locator(".antiek-hud");
    await expect(hud, "the ⌘ HUD did not open on '?'").toBeVisible({ timeout: 5_000 });

    // No chord "then" separator is rendered anywhere in the HUD.
    await expect(hud.locator(".antiek-keychip__then")).toHaveCount(0);
    await expect(hud.locator(".antiek-keychip__seq")).toHaveCount(0);

    // No group heading mentions chords. (Headings render via CSS
    // text-transform, so allInnerTexts() may be upper-cased — match
    // case-insensitively.)
    const headings = await hud.locator(".antiek-hud__heading").allInnerTexts();
    expect(headings.some((h) => /chord/i.test(h)), `a chord group remains: ${headings.join(", ")}`).toBe(false);
    // The Products group IS present (the ⌘+key doors).
    expect(headings.some((h) => /^products$/i.test(h.trim())), `no Products group: ${headings.join(", ")}`).toBe(true);

    // Capture the proof artifact: the chord-free ⌘ HUD on screen (RULE 2 — the
    // proof is the real browser, not a green vitest). Saved unconditionally
    // (not only-on-failure) so a green run still leaves a durable image of the
    // ⌘-only cheat-sheet that a reviewer can eyeball.
    await page.screenshot({ path: "test-results/hotkeys-command-scheme-hud.png" });
  });

  // (d) A persisted custom ⌘+key survives a reload and still navigates.
  test("(d) a persisted custom hotkey still navigates after reload", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);

    // Seed a persisted custom binding (⌥; → /library) the way useCustomHotkeys
    // would, then RELOAD so the live handler hydrates it from localStorage on
    // boot (workspace/shortcuts.ts hydrateCustomFromStorage). ⌥; (alt+";") is a
    // free safe combo — not a built-in/product/reserved combo.
    await page.evaluate(
      ([key]) => {
        window.localStorage.setItem(
          key,
          JSON.stringify({
            schemaVersion: 1,
            bindings: [
              {
                id: "e2e-custom-1",
                spec: "alt+;",
                route: "/library",
                entityId: "e2e-entity",
                entityKind: "investigation",
                label: "E2E pinned research",
              },
            ],
          }),
        );
      },
      [CUSTOM_HOTKEYS_KEY],
    );

    // Reload — the persisted binding must re-read identically and load into
    // the live keydown handler on mount (the M2 reload-survival proof).
    await page.reload({ waitUntil: "domcontentloaded" });
    await page
      .waitForFunction(() => {
        const root = document.getElementById("root");
        return !!root && root.childElementCount > 0;
      }, { timeout: 10_000 })
      .catch(() => {});
    await page.waitForTimeout(600);

    // The persisted blob round-trips identically after reload.
    const persisted = await page.evaluate(
      ([key]) => window.localStorage.getItem(key),
      [CUSTOM_HOTKEYS_KEY],
    );
    expect(persisted, "the custom-hotkeys blob did not survive reload").toContain("alt+;");

    // Press the custom combo (⌥;) → it navigates to the bound route, identical
    // to clicking the entity.
    await page.locator("body").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("Alt+;");
    await expect(page).toHaveURL(/\/library(\/|$|\?)/, { timeout: 5_000 });
  });
});
