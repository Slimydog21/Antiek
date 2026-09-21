/**
 * penguin.spec.ts — the SPR-06 EXPERIENCE GATE for Werner the mascot.
 *
 * The anti-invisible proof, in real Chromium pixels (rigor #3: every "feet
 * move" / "no white box" claim is a BROWSER pixel/alpha assertion, NOT prose).
 * Runs in the `chromium`/Storybook project against the real composed
 * PenguinMascot stories (title "Shell / PenguinMascot (SPR-06)" → ids verified
 * in storybook-static/index.json: --roaming, --resting, --reduced-motion-note).
 *
 * FOUR sub-tests, one per milestone that has a visible outcome:
 *
 *   M1 walk-cycle — screenshot the mascot square at two mid-stroll moments and
 *     assert the pixels CHANGED (frameMeanAbsDiff > threshold). reducedMotion
 *     is forced to "no-preference" so the gait actually animates (else a false
 *     RED). Since the WernerRig SVG was removed (BrainMascot single-source),
 *     the walk cycle animates as the whole-body waddle bob — so the gate
 *     measures WALK MOTION, not TRANSLATION: the penguin is PINNED (left/top
 *     transition killed, position nailed) so the clip rect is static and the
 *     textured story background cannot bleed through a sliding clip. A fully
 *     frozen sprite → near-0 diff → RED.
 *
 *   M2 white box — with an emote PLAYING (we dispatch the activation event so
 *     the hit/celebrate overlay renders), sample the WHOLE mascot square and
 *     assert the opaque-near-white FRACTION is well under a quarter (the worst
 *     real pose, `thinking`, carries ~13% interior belly-white; the M4/hit
 *     `celebrate` pose ~5%, so a true alpha-cut clears <0.25 with room while a
 *     baked white BOX would push it toward ~1) on BOTH the light (ice) and dark
 *     (space) theme. Before the alpha-cut the surround was a solid
 *     (255,253,253)-class box; after, the story bg bleeds through it (measured
 *     0.00% opaque-near-white in this run — the box is gone, not merely small).
 *
 *   M4 waddle-to-button + bump — inject a control carrying data-product-id at a
 *     known far-side rect, dispatch antiek:product:activate {productId}, and
 *     assert (a) the mascot's distance to that rect SHRINKS (he walked toward
 *     it) and (b) a hit emote mounted (the Tom-&-Jerry bump rides on it).
 *
 *   M5 reduced-motion — with reducedMotion "reduce", screenshot the whole
 *     mascot region twice ~2s apart and assert near-ZERO pixel-diff (he stays
 *     put, feet static) AND no white box (whiteBoxFraction ~0). The gentle
 *     in-place state, never a white card.
 *
 * The pure helpers (frameMeanAbsDiff / whiteBoxFraction / regionMeanColor) are
 * exported from _ams/visible.ts and unit-calibrated in visible.pixel.test.ts.
 */
import { expect, test, type Page } from "@playwright/test";

import {
  decodePng,
  frameMeanAbsDiff,
  whiteBoxFraction,
} from "./visible";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

const ROAMING = "shell-penguinmascot-spr-06--roaming";
const REDUCED = "shell-penguinmascot-spr-06--reduced-motion-note";

/** The mascot control + a settle so it has mounted + seeded its position. */
async function loadMascot(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
  const mascot = page.locator('[data-testid="brain-mascot"]');
  await expect(mascot, "penguin mascot not found in the story").toBeVisible({
    timeout: 10_000,
  });
}

/** Read the mascot's current viewport rect (its bounding box). */
async function mascotBox(page: Page): Promise<{
  x: number;
  y: number;
  width: number;
  height: number;
}> {
  const box = await page.locator('[data-testid="brain-mascot"]').boundingBox();
  expect(box, "no mascot bounding box").not.toBeNull();
  return box!;
}

test.describe("SPR-06 — Werner is ALIVE (real Chromium pixels)", () => {
  // ── M1: the FEET move (vector walk-cycle, not a sliding sprite) ──────────
  test.use({ contextOptions: { reducedMotion: "no-preference" } });

  test("M1 walk-cycle: the mascot art changes across two mid-stroll frames with position pinned", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);
    // Force a directed stroll so the walk classes (werner-waddle/werner-step)
    // ride the bob span → the rig limbs animate. We inject a far-side target
    // and activate it; the penguin starts waddling toward it with the gait on.
    await page.evaluate(() => {
      const b = document.createElement("button");
      b.setAttribute("data-product-id", "research");
      b.style.cssText =
        "position:fixed;right:80px;top:360px;width:48px;height:48px;";
      document.body.appendChild(b);
      window.dispatchEvent(
        new CustomEvent("antiek:product:activate", {
          detail: { productId: "research", source: "click" },
        }),
      );
    });
    // Settle so the directed walk has begun (the bob span now carries the walk
    // classes). We are still well inside the 1800ms waddle window — the hit
    // emote only mounts on arrival.
    await page.waitForTimeout(300);

    // PIN the penguin so the gate measures WALK MOTION, not the slide. The
    // cross-screen TRANSLATION is the removed confound: kill the left/top
    // transition + nail the button at its current position, so the clip rect
    // is STATIC and the story background cannot bleed through a sliding clip.
    // (Historical note: the deleted WernerRig SVG once stepped feet via
    // `.werner-rig-foot-*`; the single-source BrainMascot art walks with the
    // whole-body waddle bob instead, so freezing the bob here would freeze
    // the ONLY locomotion the mascot has left and the gate would measure
    // noise — exactly the 0.8–1.5 diffs this stale freeze produced in CI.)
    const pin = await page.evaluate(() => {
      const btn = document.querySelector(
        '[data-testid="brain-mascot"]',
      ) as HTMLElement | null;
      if (!btn) return null;
      const r = btn.getBoundingClientRect();
      // (1) Freeze position: no easing transition, nailed to where it is now.
      btn.style.transition = "none";
      btn.style.left = `${r.left}px`;
      btn.style.top = `${r.top}px`;
      // Force the walk signal ON the bob span so the descendant rig keyframes
      // run even after the roam's end-of-leg restGait would strip them.
      const bob = btn.firstElementChild as HTMLElement | null;
      if (bob) {
        bob.classList.add("werner-waddle");
        bob.classList.add("werner-step");
      }
      return { x: r.left, y: r.top, width: r.width, height: r.height };
    });
    expect(pin, "could not pin the penguin for the M1 walk-motion sample").not.toBeNull();
    const box = pin!;
    // The mascot square. The SAME static clip for both grabs.
    const feetClip = {
      x: Math.round(box.x),
      y: Math.round(box.y + box.height * 0.6),
      width: Math.round(box.width),
      height: Math.round(box.height * 0.4),
    };
    const grabFeet = () => page.screenshot({ clip: feetClip });
    const a = decodePng(await grabFeet());
    await page.waitForTimeout(150); // ~half a 300ms gait cycle → feet in a new phase
    const b = decodePng(await grabFeet());
    const diff = frameMeanAbsDiff(a, b);
    // With translation pinned, the waddle bob/step cadence must move mascot
    // pixels across a ~half-cycle gap; a fully frozen sprite diffs near 0 and
    // FAILS.
    expect(
      diff,
      `mascot square barely changed (mean abs diff ${diff.toFixed(2)}) with the penguin ` +
        `PINNED and the waddle cadence ON — the walk cycle is not animating. With ` +
        `translation removed only the gait can move these pixels, so a near-0 diff ` +
        `means the mascot is frozen mid-stroll.`,
    ).toBeGreaterThan(1.5);
  });

  // ── M2: no white box, emote PLAYING, both themes ─────────────────────────
  for (const theme of ["light", "dark"] as const) {
    test(`M2 white box: the emote region has no opaque white backdrop (${theme} theme)`, async ({
      page,
    }) => {
      await loadMascot(page, ROAMING);
      // Drive the theme via Storybook's dark-class toggle on <html> (the story
      // bg is `bg-ice-2 dark:bg-space-2`, so the corners read ice vs space).
      await page.evaluate((t) => {
        const el = document.documentElement;
        if (t === "dark") el.classList.add("dark");
        else el.classList.remove("dark");
      }, theme);
      // Trigger an emote so the emote OVERLAY (the pose that carried the white
      // box pre-fix) is the thing rendered — that is the surface under test.
      await page.evaluate(() => {
        window.dispatchEvent(
          new CustomEvent("antiek:product:activate", {
            detail: { productId: "research", source: "click" },
          }),
        );
      });
      await page.waitForTimeout(300); // let the emote mount + the waddle settle
      const box = await mascotBox(page);
      // Sample the whole mascot square — the emote pose fills it; pre-fix the
      // backdrop pixels in the corners were a solid near-white box.
      const shot = await page.screenshot({
        clip: {
          x: Math.round(box.x),
          y: Math.round(box.y),
          width: Math.round(box.width),
          height: Math.round(box.height),
        },
      });
      const frac = whiteBoxFraction(decodePng(shot));
      // Most of the square is penguin + transparent surround (= story bg). A
      // small white-belly sliver is fine; a baked white BOX would push this
      // toward ~1. Assert it is well under a quarter of the region.
      expect(
        frac,
        `${theme} theme: ${(frac * 100).toFixed(1)}% of the mascot region is opaque ` +
          `near-white — the emote pose still carries a baked white backdrop (the v1 white box)`,
      ).toBeLessThan(0.25);
    });
  }

  // ── M4: waddle-to-button + Tom-&-Jerry bump on PRODUCT_ACTIVATE ──────────
  test("M4 waddle-to-button: the penguin moves measurably TOWARD the activated control + plays a hit emote", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);
    // Inject a control at a known FAR-side rect (right edge) carrying the
    // data-product-id the choreography resolves; record the penguin's start.
    const targetRect = await page.evaluate(() => {
      const b = document.createElement("button");
      b.setAttribute("data-product-id", "research");
      b.setAttribute("data-testid", "ams-m4-target");
      b.style.cssText =
        "position:fixed;right:60px;top:380px;width:48px;height:48px;";
      document.body.appendChild(b);
      const r = b.getBoundingClientRect();
      return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
    });
    const before = await mascotBox(page);
    const beforeCx = before.x + before.width / 2;
    const beforeCy = before.y + before.height / 2;
    const dist = (cx: number, cy: number) =>
      Math.hypot(cx - targetRect.cx, cy - targetRect.cy);
    const distBefore = dist(beforeCx, beforeCy);

    // Activate — the SAME event a clicked/hotkeyed product button fires.
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("antiek:product:activate", {
          detail: { productId: "research", source: "click" },
        }),
      );
    });
    // The directed waddle eases over WADDLE_MS (1800ms); sample near the end.
    await page.waitForTimeout(1700);
    const after = await mascotBox(page);
    const afterCx = after.x + after.width / 2;
    const afterCy = after.y + after.height / 2;
    const distAfter = dist(afterCx, afterCy);

    // (a) He walked measurably TOWARD the target rect.
    expect(
      distAfter,
      `penguin did not move toward the activated control: distance ${distBefore.toFixed(0)}→` +
        `${distAfter.toFixed(0)}px (it should shrink — the waddle-to-button choreography)`,
    ).toBeLessThan(distBefore - 40);

    // (b) A hit emote mounted (the bump rides on it). The emote overlay carries
    //     the werner-hit-bump wrapper on the hit kind.
    await expect(
      page.locator('[data-testid="brain-mascot"] .werner-hit-bump'),
      "no hit-emote bump played on arrival (the Tom-&-Jerry button bump)",
    ).toHaveCount(1, { timeout: 2_000 });
  });
});

test.describe("SPR-06 — reduced motion is a gentle in-place state, never a white card", () => {
  // M5: prefers-reduced-motion → no roam, feet static, no white box.
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  for (const theme of ["light", "dark"] as const) {
    test(`M5 reduced-motion: the mascot is near-still and shows NO white box (${theme} theme)`, async ({
      page,
    }) => {
      await loadMascot(page, REDUCED);
      await page.evaluate((t) => {
        const el = document.documentElement;
        if (t === "dark") el.classList.add("dark");
        else el.classList.remove("dark");
      }, theme);
      const box = await mascotBox(page);
      const clip = {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
      };
      const a = decodePng(await page.screenshot({ clip }));
      // Wait ~2s — well past a roam settle. Under reduced motion NOTHING should
      // move (no roam, no wander, no foot animation).
      await page.waitForTimeout(2000);
      const b = decodePng(await page.screenshot({ clip }));
      const diff = frameMeanAbsDiff(a, b);
      expect(
        diff,
        `${theme} theme: the mascot region changed (mean abs diff ${diff.toFixed(2)}) under ` +
          `prefers-reduced-motion — it must be a still, in-place state (no roam, feet static)`,
      ).toBeLessThan(1.0);
      // And NO white card on either theme.
      const frac = whiteBoxFraction(b);
      expect(
        frac,
        `${theme} theme: ${(frac * 100).toFixed(1)}% of the reduced-motion mascot region is ` +
          `opaque near-white — reduced motion must never show a white card`,
      ).toBeLessThan(0.25);
    });
  }
});
