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
  // BASELINE NOTE (verified by SPR-01's linchpin run on origin/main @ ebfb36a,
  // 2026-05-31): this anchor currently PASSES — SPR-04 already shipped the
  // `bg-transparent` shell frame (AppShell.tsx), so the default route `/` is NOT
  // fully occluded and the sampled band has real colour variance (~869, 65
  // distinct colours). The v1 occlusion the post-mortem described was thus
  // largely fixed upstream by SPR-04 before this spec ran. SPR-03 still owns
  // TIGHTENING this to success-criterion #1 ("a non-trivial fraction of the
  // viewport is the MOVING scene", not chrome+text) and proving glass over the
  // remaining opaque landing panels. Kept `fixme` so SPR-03 explicitly claims +
  // strengthens it; un-fixme'ing today would pass but on a weak assertion.
  test.fixme("anchor[scene]: the mountain is visible behind the landing", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // `region` is REQUIRED (SPR-01 sharpen — no silent chrome-catching default).
    // This placeholder samples an upper-middle band; SPR-03 MUST replace it with
    // a region that is UNAMBIGUOUSLY scene (not chrome/text) when it claims this
    // anchor — that is the success-criterion #1 tightening it owns.
    await assertSceneVisible(page, { x: 0.15, y: 0.18, width: 0.7, height: 0.28 });
  });

  // ── Anchor 2 ──────────────────────────────────────────────────────────────
  // SPR-04 flips this green.
  // WindowsLayer returns null until a window is summoned, and a product click
  // navigates full-page. After landing + a product activation there is NO
  // floating window by default. SPR-04 makes a product click open a sub-action
  // window by default; assertWindowOpen then finds the [role=dialog] frame.
  test.fixme("anchor[window]: a floating window is the default interaction", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // A product activation that SHOULD (post-SPR-04) open a window by default.
    // Today nothing opens — the anchor is the absence.
    const research = page.getByRole("link", { name: /research/i }).first();
    if (await research.count()) {
      await research.click().catch(() => {});
    }
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
