/**
 * navrail-labels.spec.ts — the SPR-07 EXPERIENCE GATE (RULE 2: the proof is the
 * REAL bottom rail in a browser, not a green vitest).
 *
 * Belongs to the `ams-real` Playwright project: it loads the REAL authed SPA
 * via loginAndGotoApp (mocked /auth/me at the network layer — no app-code auth
 * bypass) and asserts the operator's headline ask on the real bar:
 *
 *   (1) the igloo home control shows a VISIBLE "Home" caption (the same fact
 *       ams-shell.spec.ts anchor[igloo] flips green — duplicated here as the
 *       dedicated NavRail gate so a regression reddens close to the cause);
 *   (2) all SEVEN bar controls (Home, Search, Research, Read, Write, Speak,
 *       More) carry BOTH a visible text label AND an on-bar ⌘ hotkey chip;
 *   (3) each chip is a single ⌘+key combo (no chord "then" — proves the chips
 *       came from the post-SPR-08 uniform scheme, never the stale "g h" chord);
 *   (4) the bar keeps its yellow identity — the rail still carries border-sun
 *       (→ --bar-accent / --sun), so SPR-09 can re-tune the token without
 *       re-touching NavRail.
 *
 * On a sandbox with no served SPA the `ams-real` project skips cleanly per the
 * harness RULE 3; a real run with a built SPA + AMS_APP_URL (or the vite-preview
 * webServer) makes these genuinely red/green.
 */

import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import { assertLabeled } from "./_ams/visible";

/** The default authed route the operator lands on. */
const DEFAULT_ROUTE = "/";

/** The bottom rail (NavRail.tsx: aria-label="Primary navigation"). */
const RAIL = 'aside[aria-label="Primary navigation"]';

/** The seven bar controls, each by its accessible name. Home is the igloo
 *  (aria-label "Antiek home"); the rest are the visible/sr-only labels. */
const CONTROLS: ReadonlyArray<{ name: string; visible: string }> = [
  { name: "Antiek home", visible: "Home" },
  { name: "Search", visible: "Search" },
  { name: "Research", visible: "Research" },
  { name: "Read", visible: "Read" },
  { name: "Write", visible: "Write" },
  { name: "Speak", visible: "Speak" },
  { name: "More", visible: "More" },
];

test.describe("SPR-07 — every bar control is a named, ⌘-chipped button (real browser)", () => {
  test('(1) the igloo home control shows a visible "Home" caption', async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await assertLabeled(page, 'button[aria-label="Antiek home"]', "Home");
  });

  test("(2) all seven bar controls carry a visible label AND an on-bar ⌘ chip", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const rail = page.locator(RAIL).first();
    await expect(rail, "the bottom rail must be on screen").toBeVisible({ timeout: 5_000 });

    for (const c of CONTROLS) {
      const button = rail.getByRole("button", { name: c.name }).first();
      await expect(button, `the "${c.name}" control must be on the bar`).toBeVisible();
      // A VISIBLE text caption (not merely an aria-label, and not the hidden
      // `.sr-only` announcer). The visible caption is the aria-hidden text node
      // that is NOT `.sr-only`; scope past the sr-only span so strict mode sees
      // exactly the on-screen caption, then assert it is actually visible.
      const visibleCaption = button
        .locator("span:not(.sr-only)")
        .filter({ hasText: c.visible })
        .last();
      await expect(
        visibleCaption,
        `the "${c.name}" control must show a VISIBLE "${c.visible}" caption`,
      ).toBeVisible();
      // An on-bar ⌘ hotkey chip (the reused KeyChip → .antiek-keychip).
      await expect(
        button.locator(".antiek-keychip"),
        `the "${c.name}" control must show an on-bar ⌘ hotkey chip`,
      ).toHaveCount(1);
    }
    // Durable proof artifact: the real bottom rail, every control named + chipped.
    await rail.screenshot({ path: "test-results/navrail-labels-bottom-rail.png" });
  });

  test("(3) every chip is a single ⌘+key combo (no chord 'then')", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const rail = page.locator(RAIL).first();
    await expect(rail).toBeVisible({ timeout: 5_000 });
    // No chip on the bar renders a chord sequence — the post-SPR-08 scheme is
    // uniform ⌘+key, so the stale "g h"/"g m" chord (which would render a
    // "then" separator) is provably absent.
    await expect(rail.locator(".antiek-keychip__then")).toHaveCount(0);
    await expect(rail.locator(".antiek-keychip__seq")).toHaveCount(0);
  });

  test("(4) the bar keeps its yellow identity (border-sun → --bar-accent, unchanged)", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const rail = page.locator(RAIL).first();
    await expect(rail).toBeVisible({ timeout: 5_000 });
    const klass = (await rail.getAttribute("class")) ?? "";
    // The rail still references the sun token via Tailwind border-sun (the
    // bottom rail's accent edge). SPR-09 re-tunes --bar-accent/--sun's VALUE;
    // SPR-07 must not change which token the bar binds to.
    expect(klass, `the bar must keep its border-sun accent (got: ${klass})`).toContain("border-sun");
  });
});
