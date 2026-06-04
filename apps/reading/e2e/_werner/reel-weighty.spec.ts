/**
 * reel-weighty.spec.ts — the SPR-03 OPERATOR-RUN EXPERIENCE GATE for the reel.
 *
 * ── RULE 2 (operator-run): this spec is NOT run in this sharpen pass. ───────────
 * The full `npm run e2e` (build-storybook + build + a real Chromium) is too heavy
 * for the sharpen sandbox, so it is written to TYPE-CHECK (it is included in
 * tsconfig.ams-e2e.json and passes `tsc -b` via the e2e typecheck project) but is
 * left for the OPERATOR to run in a real browser to confirm SPR-03's *feel*:
 *
 *     npm run build-storybook && npx playwright test e2e/_werner/reel-weighty.spec.ts
 *
 * The unit suite (src/werner/reelPursuit.test.ts) already proves the spring's
 * math AND gates the production router (reelStateStep @ DEFAULT config) to the
 * spring. THIS gate is the pixel-level confirmation in real Chromium that the
 * wired path — PenguinMascot driving reelStateStep on every rAF as the cursor
 * moves — actually *reads* weighty: the close decelerates into the target, never
 * overshoots, and is slower than a snappy baseline. It is the browser analogue of
 * penguin.spec.ts (SPR-06), and follows that file's harness exactly (Storybook
 * iframe URL, [data-testid="penguin-mascot"], boundingBox sampling).
 *
 * HOW THE REEL ENGAGES (so the operator knows what this exercises): on the
 * Roaming story, with the WERNER-ICE flag on (default; VITE_WERNER_ICE_FISHING
 * !== "0") and motion allowed, PenguinMascot calls stage.follow(true) on mount.
 * Any pointermove then makes useMouseFollow.read() return a non-idle lagged
 * target, which flips reelActive true and drives reelStateStep(...) — the spring
 * — on every frame (PenguinMascot.tsx ~436). So MOVING THE POINTER and keeping it
 * within POINTER_IDLE_MS (2000ms) is what we sample. The mascot trails the cursor
 * via el.style.left/top, readable through boundingBox().
 *
 * THREE assertions, one per felt claim:
 *   (a) WEIGHTY SETTLE — closing speed DECREASES as the mascot nears the target
 *       (per-frame displacement falls across the late approach samples).
 *   (b) NO OVERSHOOT — the gap to the target is monotone non-increasing across
 *       the approach (critical damping ⇒ never passes the mark).
 *   (c) SLOWER THAN SNAPPY — in the first window the spring closes FEWER pixels
 *       than a snappy first-order ease (the old 450ms exponential baseline) would
 *       have closed over the same gap + elapsed time. The snappy baseline is
 *       computed analytically (1 − e^(−t/τ), τ=450ms) from the SAME measured gap
 *       and elapsed wall-time, so this compares the felt easing shapes, not a cap.
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

/** The Roaming story id (verified in penguin.spec.ts against the built index). */
const ROAMING = "shell-penguinmascot-spr-06--roaming";

/** The snappy first-order baseline the spring must beat (matches the unit test's
 *  BASELINE_TAU_MS in reelPursuit.test.ts: the old, snappy 450ms exponential). */
const BASELINE_TAU_MS = 450;

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Load the mascot story + wait for the mascot to mount and seed its position. */
async function loadMascot(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
  const mascot = page.locator('[data-testid="penguin-mascot"]');
  await expect(mascot, "penguin mascot not found in the story").toBeVisible({
    timeout: 10_000,
  });
}

/** Read the mascot's current viewport rect (its bounding box). */
async function mascotBox(page: Page): Promise<Box> {
  const box = await page.locator('[data-testid="penguin-mascot"]').boundingBox();
  expect(box, "no mascot bounding box").not.toBeNull();
  return box!;
}

function centerOf(b: Box): { cx: number; cy: number } {
  return { cx: b.x + b.width / 2, cy: b.y + b.height / 2 };
}

interface Sample {
  t: number; // ms since the first sample
  cx: number;
  cy: number;
  dist: number; // distance from mascot center to the target point
}

test.describe("SPR-03 — the reel reads WEIGHTY (real Chromium pixels)", () => {
  // Motion must be allowed for stage.follow(true) to engage (reduced motion
  // freezes the reel). This mirrors penguin.spec.ts's M1 use().
  test.use({ contextOptions: { reducedMotion: "no-preference" } });

  test("the reel decelerates into the target, never overshoots, and is slower than a snappy ease", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);

    // Park the mascot's starting position and pick a far in-viewport target so
    // the reel has a real gap to close (but well inside the screen so the
    // velocity cap — a teleport guard — never engages; that is what the unit
    // test's IN_VIEWPORT_PULL=140 reasoning protects, and what makes this a test
    // of the easing shape, not of a shared cap).
    const start = centerOf(await mascotBox(page));
    const target = { x: start.cx + 220, y: start.cy + 140 };

    // Engage the reel: a first move flips reelActive true (non-idle target).
    await page.mouse.move(target.x, target.y, { steps: 1 });

    // Sample the mascot center over ~1.2s while NUDGING the pointer at the SAME
    // target each tick — the nudge keeps the pointer non-idle (< POINTER_IDLE_MS)
    // so reelActive stays true, while the target itself does not move, so the
    // mascot closes a FIXED gap (a clean settle to measure).
    const samples: Sample[] = [];
    const t0 = Date.now();
    const totalMs = 1200;
    const tickMs = 50;
    while (Date.now() - t0 < totalMs) {
      // Re-assert the pointer at the target (tiny jitter keeps it "moving" so the
      // idle timer never trips, without changing the gap being closed).
      const jitter = samples.length % 2 === 0 ? 0.5 : -0.5;
      await page.mouse.move(target.x + jitter, target.y + jitter, { steps: 1 });
      const b = await mascotBox(page);
      const { cx, cy } = centerOf(b);
      samples.push({
        t: Date.now() - t0,
        cx,
        cy,
        dist: Math.hypot(cx - target.x, cy - target.y),
      });
      await page.waitForTimeout(tickMs);
    }

    expect(
      samples.length,
      "too few samples to characterize the reel — the surface did not animate",
    ).toBeGreaterThan(8);

    // The mascot must have genuinely closed most of the gap (the reel engaged at
    // all). If it never moved, every later assertion is vacuous.
    const firstDist = samples[0].dist;
    const lastDist = samples[samples.length - 1].dist;
    expect(
      lastDist,
      `the mascot did not close the gap (start ${firstDist.toFixed(0)}px → end ` +
        `${lastDist.toFixed(0)}px) — the reel never engaged (check the WERNER-ICE flag)`,
    ).toBeLessThan(firstDist - 40);

    // ── (b) NO OVERSHOOT — gap is monotone non-increasing across the approach. ──
    // Critical damping ⇒ the mascot never passes the target ⇒ dist never grows
    // (allow a couple px of sampling/sub-pixel-rounding noise per step).
    for (let i = 1; i < samples.length; i++) {
      expect(
        samples[i].dist,
        `overshoot/oscillation: gap grew ${samples[i - 1].dist.toFixed(1)}→` +
          `${samples[i].dist.toFixed(1)}px at t=${samples[i].t}ms (a weighty reel never passes the mark)`,
      ).toBeLessThanOrEqual(samples[i - 1].dist + 2.0);
    }

    // ── (a) WEIGHTY SETTLE — closing speed DECREASES as it nears the target. ──
    // Per-sample closing speed (px per ms) = how much gap it ate this tick.
    const closingSpeed = samples
      .slice(1)
      .map((s, i) => ({
        t: s.t,
        dist: s.dist,
        v: Math.max(0, samples[i].dist - s.dist) / (s.t - samples[i].t),
      }));
    // The spring accelerates off the mark then decelerates. Find the peak closing
    // speed; the LATE approach (last third of samples, all post-peak and near the
    // target) must be slower than that peak — the deceleration the operator asked
    // for. We compare the mean of the late window to the peak rather than asserting
    // strict per-step monotonicity, because real-browser sampling has frame jitter.
    let peakV = 0;
    for (const s of closingSpeed) if (s.v > peakV) peakV = s.v;
    const lateWindow = closingSpeed.slice(Math.floor(closingSpeed.length * 0.66));
    const lateMeanV =
      lateWindow.reduce((acc, s) => acc + s.v, 0) / Math.max(1, lateWindow.length);
    expect(peakV, "the reel never built any closing speed").toBeGreaterThan(0);
    expect(
      lateMeanV,
      `the reel did not decelerate: late closing speed (${lateMeanV.toFixed(3)} px/ms) is not ` +
        `clearly under the peak (${peakV.toFixed(3)} px/ms) — it should ease into the target, not snap`,
    ).toBeLessThan(peakV * 0.75);

    // ── (c) SLOWER THAN A SNAPPY EASE — fewer px closed up front than τ=450ms. ──
    // Compare the FIRST window: how far the spring actually closed vs how far a
    // snappy first-order ease (1 − e^(−t/τ), τ=450ms) would have closed over the
    // SAME starting gap and the SAME elapsed wall-time. This is the browser
    // analogue of the unit test's "closes fewer pixels in the first 300ms".
    const windowEnd = samples.find((s) => s.t >= 300) ?? samples[samples.length - 1];
    const springClosed = firstDist - windowEnd.dist;
    const snappyClosed = firstDist * (1 - Math.exp(-windowEnd.t / BASELINE_TAU_MS));
    expect(
      springClosed,
      `the reel is not slower than a snappy ease: it closed ${springClosed.toFixed(0)}px in ` +
        `${windowEnd.t}ms, but a snappy τ=${BASELINE_TAU_MS}ms ease would have closed only ` +
        `${snappyClosed.toFixed(0)}px — the spring should lag the snappy baseline up front (weight)`,
    ).toBeLessThan(snappyClosed);
  });
});
