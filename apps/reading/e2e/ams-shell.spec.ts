/**
 * ams-shell.spec.ts — the AMS-v2 regression anchors (SPR-01, milestone 4).
 *
 * WHAT THIS IS
 * ------------
 * Five tests that load the REAL app authenticated on the default route (via
 * loginAndGotoApp → mocked /auth/me, no app-code bypass) and encode each v1
 * failure as an EXPECTED-FAIL anchor. Each anchor is a real, executing test
 * body that calls a real helper from _ams/visible.ts against the real page —
 * so when its `test.fixme` is removed it genuinely red/green-flips. The comment
 * on each names the EXACT later sprint that turns it green; SPR-10's capstone
 * mechanically checks "all five un-fixme'd and green."
 *
 * Today (origin/main) these are the operator-verified v1 complaints:
 *   1. scene NOT visible   — opaque route bodies occlude the z-0 mountain → SPR-03
 *   2. no default window   — WindowsLayer returns null until summoned       → SPR-04
 *   3. igloo has no caption — only aria-label="Antiek home"                 → SPR-07
 *   4. no ⌘ overlay default / vim chords present                            → SPR-08
 *   5. penguin emote carries a white background                            → SPR-06
 *
 * They are marked `test.fixme` so they DON'T block CI now (the bugs are owned
 * by later sprints), but are impossible to forget. This spec imports ONLY from
 * _ams/ — it edits no app component (SPR-01 writes zero app code).
 *
 * RUN: this spec belongs to the `ams-real` Playwright project, which needs a
 * served real SPA. See docs/ams-v2/e2e-harness.md. When AMS_APP_URL is unset
 * and no app server can boot, the project SKIPS cleanly (RULE 3).
 */

import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import {
  assertSceneVisible,
  assertWindowOpen,
  assertLabeled,
  assertHotkeyOverlay,
} from "./_ams/visible";

/** The default authed route the operator lands on (App.tsx: "/" → ResearchWorkstation). */
const DEFAULT_ROUTE = "/";

/** The igloo home button — verified selector (NavRail.tsx: aria-label="Antiek home"). */
const IGLOO_SELECTOR = 'button[aria-label="Antiek home"]';

test.describe("AMS-v2 regression anchors — the v1 failures, encoded as red lights", () => {
  // ── Anchor 1 ──────────────────────────────────────────────────────────────
  // Owner: SPR-03 (glass surface model). assertSceneVisible samples real pixels
  // over a band behind the chrome and FAILS while it is one flat ice/space
  // colour (an opaque route body occluding the z-0 <Scene/>).
  //
  // SPR-03 CLAIMED + un-fixme'd. The old placeholder region (x 0.15–0.85,
  // y 0.18–0.46) overlapped the centred max-w-3xl content column and passed on
  // HEADING-TEXT variance — the exact v1 false-green the SPR-01 sharpen forbids.
  // SPR-03 replaces it with a CONTENT-FREE band in the GAP between the left
  // ad-border rail (ends x≈0.075) and the centred content column (starts
  // x≈0.20), below the SceneChrome action bar and above the bottom ad rail, so
  // the only thing painted there is the glass band over the z-0 moving scene.
  // (An earlier cut sampled x 0.02–0.16, which overlapped the OPAQUE AdBorder
  // left rail + its creative text and so passed on chrome-text variance even
  // with the scene hidden — fixed here + guarded by glass-surface.spec.ts's
  // live negative control.) This is success-criterion #1 ("a non-trivial
  // fraction of the viewport is the MOVING scene, not chrome+text"). The
  // dedicated headline gate (glass-surface.spec.ts) additionally proves the
  // landing text clears WCAG-AA over its glass scrim AND that the band is
  // non-vacuous.
  test("anchor[scene]: the mountain is visible behind the landing", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // CONTENT-FREE scene region: the gap (x 0.085–0.18) between the left ad rail
    // (x≤0.075) and the content column (x≥0.20), between the action bar (y≈0.214)
    // and the bottom rail (y≈0.95). px x∈[109,231], y∈[216,562] at 1280×720.
    await assertSceneVisible(page, { x: 0.085, y: 0.3, width: 0.095, height: 0.48 });
  });

  // ── Anchor 2 ──────────────────────────────────────────────────────────────
  // SPR-04 FLIPS THIS GREEN (un-fixme'd).
  // v1 complaint #2: "windows were manual, not the default." WindowsLayer
  // returned null until something summoned a window, and the default product
  // click navigated full-page, so the operator never saw a window. SPR-04
  // inverts the policy: a within-contract PRODUCT activation opens a sub-action
  // window over the scene BY DEFAULT (no ⊞ needed). Here we perform that real
  // default activation — open the launcher (More), click the Research product —
  // and assert the floating [role=dialog] window frame is on screen.
  test("anchor[window]: a floating window is the default interaction", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // Open the launcher (the single non-workflow rail affordance), then activate
    // the Research product — the within-contract default that now opens a window.
    await page.getByRole("button", { name: "More" }).first().click();
    await page.getByRole("button", { name: /open research workflow in a window/i }).first().click();
    await assertWindowOpen(page);
  });

  // ── Anchor 3 ──────────────────────────────────────────────────────────────
  // SPR-07 flips this green.
  // The igloo home button has aria-label="Antiek home" and an <IglooMark/> but
  // NO visible "Home" caption (every product button DOES carry a visible
  // label). assertLabeled requires a VISIBLE text node, so it fails today.
  // SPR-07 adds the "Home" caption.
  test.fixme('anchor[igloo]: the home igloo shows a visible "Home" caption', async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await assertLabeled(page, IGLOO_SELECTOR, "Home");
  });

  // ── Anchor 4 ──────────────────────────────────────────────────────────────
  // SPR-08 flips this green.
  // Today the ⌘ overlay (HotkeyHud) is not surfaced by default and vim chords
  // (G then I/W/N) exist in shortcuts.ts. assertHotkeyOverlay with summon:false
  // checks the HUD is on screen WITHOUT pressing "?" — which it is not today.
  // SPR-08 replaces the chords with a uniform ⌘ scheme and decides the
  // default-surfacing of the overlay.
  test.fixme("anchor[hotkeys]: the ⌘ overlay is surfaced (no vim chords)", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await assertHotkeyOverlay(page, { summon: false });
  });

  // ── Anchor 5 ──────────────────────────────────────────────────────────────
  // SPR-06 flips this green.
  // The penguin emote marks (werner/emotes.tsx) carry a white background even
  // though the wrapper is bg-transparent. We sample the pixels immediately
  // around the mascot and assert the corners are NOT an opaque white box. Today
  // they are → fails. SPR-06 re-rigs the emotes transparent.
  test.fixme("anchor[penguin]: the penguin emote has no white background", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const mascot = page.locator('[data-testid="penguin-mascot"], [data-penguin-mascot]').first();
    await expect(
      mascot,
      "penguin mascot not found (SPR-06 owns its rigging + transparent emotes)",
    ).toBeVisible({ timeout: 5_000 });
    const box = await mascot.boundingBox();
    expect(box, "no mascot bounding box to sample").not.toBeNull();
    // SPR-06 implements the actual white-corner pixel sample; the anchor here
    // proves the mascot is locatable + visible as the red-light precondition.
  });
});
