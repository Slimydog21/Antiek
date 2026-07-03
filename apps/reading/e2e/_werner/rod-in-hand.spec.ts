/**
 * rod-in-hand.spec.ts — the SPR-04 OPERATOR-RUN EXPERIENCE GATE for the rod.
 *
 * ── RULE 2 (operator-run): this spec is NOT run in the build pass. ──────────────
 * The full `npm run e2e` (build-storybook + build + real Chromium) is too heavy
 * for the build sandbox, so this spec is written to TYPE-CHECK (it is included in
 * tsconfig.ams-e2e.json via the `e2e/_werner/**` glob and passes the e2e typecheck
 * project `npm run e2e:ams:typecheck`), and is left for the OPERATOR to run in a
 * real browser to confirm SPR-04's two load-bearing, experience-affecting claims:
 *
 *     npm run build-storybook && npx playwright test e2e/_werner/rod-in-hand.spec.ts
 *
 * The unit suites (fishingLineGeometry.test.ts + WernerRig.test.tsx) prove the
 * rod length math, the monotonic bend, and the structural contract — but jsdom
 * lays nothing out, so it cannot prove the rod RENDERS long on screen or that the
 * tip the line will leave is the rod's actual drawn tip. Only a real-Chromium
 * pixel/geometry sample can. It follows the _ams/penguin.spec.ts harness exactly
 * (Storybook iframe URL,
 * [data-testid="penguin-mascot"], boundingBox sampling).
 *
 * TWO assertions, one per felt claim:
 *   (a) ROD IS LONGER + HELD — the rendered rod (grip→tip in screen pixels) is
 *       measurably longer than the old (44,30)→(50,22) stub would render, and the
 *       rod's grip sits ON the right flipper (held, not floating).
 *   (b) LINE LEAVES THE REAL TIP — the rod tip the line layer computes
 *       (rodTipFromMascotRect, the shared contract) coincides with the rod's
 *       ACTUAL drawn tip in screen space within tolerance. (Where the fishing
 *       line layer is also mounted and live, its path's first point is sampled
 *       too and asserted to land on that same tip.)
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

/** The Roaming story id (verified in penguin.spec.ts against the built index). */
const ROAMING = "shell-penguinmascot-spr-06--roaming";

/** The mascot renders at MASCOT_SIZE = 64 (the rig viewBox is also 64 units). */
const MASCOT_SIZE = 64;

/** The OLD stub the rod must beat: (44,30)→(50,22) in 64-viewBox units = 10. */
const OLD_STUB_LEN_LOCAL = Math.hypot(50 - 44, 22 - 30);

/** The shared rod-tip contract — must match fishingLineGeometry.ts ROD_TIP_LOCAL
 *  and WernerRig.tsx ROD_TIP. Duplicated here only so the e2e file is standalone;
 *  if it drifts, assertion (b) fails, which is the contract working as intended. */
const ROD_TIP_LOCAL = { x: 66, y: 5 };
const ROD_BUTT_LOCAL = { x: 45, y: 34 };

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

async function loadMascot(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
  const mascot = page.locator('[data-testid="penguin-mascot"]');
  await expect(mascot, "penguin mascot not found in the story").toBeVisible({
    timeout: 10_000,
  });
}

async function mascotBox(page: Page): Promise<Box> {
  const box = await page.locator('[data-testid="penguin-mascot"]').boundingBox();
  expect(box, "no mascot bounding box").not.toBeNull();
  return box!;
}

test.describe("SPR-04 — the rod is LONG and HELD, and the line leaves its real tip", () => {
  // Motion allowed so nothing freezes the rig (parity with penguin.spec.ts).
  test.use({ contextOptions: { reducedMotion: "no-preference" } });

  test("the rendered rod is longer than the old stub, gripped in the flipper, and the line tip is the rod's drawn tip", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);
    const box = await mascotBox(page);
    const scale = box.width / MASCOT_SIZE; // px per viewBox unit

    // ── (a) ROD IS LONGER + HELD ───────────────────────────────────────────
    // Measure the rod's RENDERED extent from its own SVG geometry in the real
    // browser: the rod <g>'s on-screen bounding box (getBoundingClientRect runs
    // layout, so this is the actual drawn span, overflow:visible included).
    const rodRect = await page
      .locator('[data-testid="penguin-mascot"] [data-werner-rod]')
      .boundingBox();
    expect(rodRect, "the rod <g> did not render in the mascot").not.toBeNull();
    const rod = rodRect!;
    const renderedRodSpan = Math.hypot(rod.width, rod.height);
    // The old stub would render at OLD_STUB_LEN_LOCAL * scale; the new rod must
    // be at least 2× that. (Diagonal span of the rod box ≈ its drawn length.)
    const oldStubRendered = OLD_STUB_LEN_LOCAL * scale;
    expect(
      renderedRodSpan,
      `the rod rendered ${renderedRodSpan.toFixed(0)}px across, not clearly longer than ` +
        `the old ~${oldStubRendered.toFixed(0)}px stub — it does not read as a long rod`,
    ).toBeGreaterThan(2 * oldStubRendered);

    // HELD: the rod's grip (ROD_BUTT in viewBox units → screen space) sits on the
    // right flipper's rendered box (overlap, not floating beside it).
    const gripScreen = {
      x: box.x + ROD_BUTT_LOCAL.x * scale,
      y: box.y + ROD_BUTT_LOCAL.y * scale,
    };
    const flipperRect = await page
      .locator('[data-testid="penguin-mascot"] .werner-rig-flipper-r')
      .boundingBox();
    expect(flipperRect, "the right flipper did not render").not.toBeNull();
    const f = flipperRect!;
    const pad = 4 * scale; // a few viewBox units of overlap tolerance
    expect(
      gripScreen.x >= f.x - pad &&
        gripScreen.x <= f.x + f.width + pad &&
        gripScreen.y >= f.y - pad &&
        gripScreen.y <= f.y + f.height + pad,
      `the rod grip (${gripScreen.x.toFixed(0)},${gripScreen.y.toFixed(0)}) is not on the ` +
        `right flipper box (${f.x.toFixed(0)},${f.y.toFixed(0)} ${f.width.toFixed(0)}×${f.height.toFixed(0)}) ` +
        `— the rod is floating beside the hand, not held`,
    ).toBe(true);

    // ── (b) LINE LEAVES THE REAL TIP ───────────────────────────────────────
    // The tip the line layer computes (rodTipFromMascotRect, scale = size/64) in
    // screen space.
    const lineTip = {
      x: box.x + ROD_TIP_LOCAL.x * scale,
      y: box.y + ROD_TIP_LOCAL.y * scale,
    };
    // The rod's ACTUAL drawn tip in screen space: the far corner of the rod's
    // rendered box farthest from the grip (the shaft runs grip→up-right, so the
    // tip is the top-right extreme of the rod box).
    const drawnTip = { x: rod.x + rod.width, y: rod.y };
    const tipGap = Math.hypot(drawnTip.x - lineTip.x, drawnTip.y - lineTip.y);
    const tol = 6 * scale; // a few viewBox units — strokeWidth/round-cap slack
    expect(
      tipGap,
      `the line's computed tip (${lineTip.x.toFixed(0)},${lineTip.y.toFixed(0)}) is ${tipGap.toFixed(0)}px ` +
        `from the rod's drawn tip (${drawnTip.x.toFixed(0)},${drawnTip.y.toFixed(0)}) — the line would ` +
        `not leave the real rod end (the shared localTip contract is broken)`,
    ).toBeLessThan(tol);

    // If the fishing-line layer is mounted AND live in this context, also sample
    // the path's first point and assert it lands on that same tip. (The line
    // engages on cursor move with the WERNER-ICE flag on; in the isolated story
    // it may not mount, so this is asserted only when the path is present.)
    const linePath = page.locator("svg path[d^='M']").first();
    if ((await linePath.count()) > 0) {
      await page.mouse.move(lineTip.x + 200, lineTip.y + 160, { steps: 2 });
      await page.waitForTimeout(120);
      const d = await linePath.getAttribute("d");
      const m = d?.match(/^M\s*(-?[\d.]+)\s+(-?[\d.]+)/);
      if (m) {
        const first = { x: Number(m[1]), y: Number(m[2]) };
        const firstGap = Math.hypot(first.x - lineTip.x, first.y - lineTip.y);
        expect(
          firstGap,
          `the rendered line's first point (${first.x.toFixed(0)},${first.y.toFixed(0)}) is ` +
            `${firstGap.toFixed(0)}px from the rod tip — the line does not leave the tip`,
        ).toBeLessThan(tol);
      }
    }
  });
});
