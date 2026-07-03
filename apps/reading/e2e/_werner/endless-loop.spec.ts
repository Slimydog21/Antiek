/**
 * endless-loop.spec.ts — the SPR-05 OPERATOR-RUN EXPERIENCE GATE for the
 * endless fishing loop (the Scrat / Tom-&-Jerry never-catch gag).
 *
 * ── RULE 2 (operator-run): this spec is NOT run in the builder sandbox. ─────────
 * The full `npm run e2e` (build-storybook + build + a real Chromium) is too heavy
 * for the sandbox, so this is written to TYPE-CHECK (it is included via
 * tsconfig.ams-e2e.json's e2e/_werner glob and passes
 * `npm run e2e:ams:typecheck`) and is left for the OPERATOR to run in a real
 * browser to confirm SPR-05's *feel*:
 *
 *     npm run build-storybook && npx playwright test e2e/_werner/endless-loop.spec.ts
 *
 * WHAT THE UNIT SUITE ALREADY PROVES (necessary, not sufficient):
 *   src/werner/wernerState.test.ts proves the GATING logic (shouldFish: idle +
 *   pointer-idle → loop; pointer move / frozen → no loop) AND the CYCLE
 *   STRUCTURE (FISHING_BEATS order, that it loops, the never-caught invariant).
 *   THIS gate is the pixel-level confirmation in real Chromium that the wired
 *   CSS cartoon (waddle.css on the SPR-04 rod <g> + the fish + the idle line,
 *   toggled by the `werner-fishing` class in PenguinMascot's station gag rAF)
 *   actually *reads*: distinct animated phases, a never-static (never "caught")
 *   loop, and — the FIXED-STATION guarantee — that a pointer move drops the gag
 *   WITHOUT Werner chasing the cursor (he stays put; the cursor is his bait).
 *
 * HOW THE LOOP ENGAGES (so the operator knows what this exercises): on the
 * station story, with the WERNER-ICE flag on (default; VITE_WERNER_ICE_FISHING
 * !== "0") and motion allowed, PenguinMascot's station gag rAF runs every frame.
 * While the pointer is IDLE (no move for POINTER_IDLE_MS = 2000ms) it adds
 * `werner-fishing` to the bob span and the CSS keyframe cartoon (period 6400ms)
 * plays — rod swings, his own fish drifts in + escapes, his own line extends +
 * snaps up empty, forever. The moment the pointer MOVES (and stays non-idle) the
 * class is removed and the fishing line to the cursor-bait takes over — but
 * Werner does NOT move: he is fixed at his station. So LEAVING THE POINTER STILL
 * is what we sample; MOVING IT is the hand-off, and the assertion is that the
 * gag drops AND Werner stays put (the reel that used to chase is gone).
 *
 * Mirrors the harness of reel-weighty.spec.ts / _ams/penguin.spec.ts exactly:
 * Storybook iframe URL, [data-testid="penguin-mascot"], boundingBox sampling,
 * and the _ams/visible.ts pure pixel helpers (frameMeanAbsDiff / whiteBoxFraction).
 */
import { expect, test, type Page } from "@playwright/test";

import { decodePng, frameMeanAbsDiff, whiteBoxFraction } from "../_ams/visible";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

/** The Roaming story id (verified in penguin.spec.ts against the built index). */
const ROAMING = "shell-penguinmascot-spr-06--roaming";

/** The loop's full comic period (ms) — must match FISHING_CYCLE_MS in
 *  wernerState.ts (sum of FISHING_BEATS holdMs = 6400). */
const FISHING_CYCLE_MS = 6400;
/** useMouseFollow.POINTER_IDLE_MS — after this still, the loop engages. */
const POINTER_IDLE_MS = 2000;

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

/** Is the loop class currently on the bob span? (the JS gate's visible state). */
async function fishingClassOn(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.querySelector('[data-testid="penguin-mascot"]');
    return !!el?.querySelector(".werner-fishing");
  });
}

/**
 * PIN the mascot in place (kill its left/top transition + freeze its position)
 * so the screenshot clip is STATIC across grabs and only the rod/fish/line
 * keyframes can change pixels — the same articulation-not-translation discipline
 * penguin.spec.ts uses for the walk-cycle gate. Without this, the autonomous
 * wander would slide the clip and the textured story bg would dominate the diff.
 */
async function pinMascot(page: Page): Promise<void> {
  await page.evaluate(() => {
    const el = document.querySelector(
      '[data-testid="penguin-mascot"]',
    ) as HTMLElement | null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.transition = "none";
    el.style.left = `${r.left}px`;
    el.style.top = `${r.top}px`;
  });
}

test.describe("SPR-05 — the endless never-catch loop (real Chromium pixels)", () => {
  // Motion must be allowed for the loop to run (reduced motion freezes it).
  test.use({ contextOptions: { reducedMotion: "no-preference" } });

  test("idle → the loop animates through DISTINCT phases, never a static 'caught' frame, then a pointer move drops the gag while Werner stays put", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);

    // ── Leave the pointer IDLE so the loop engages. ──
    // Park it once, far from the mascot, then DO NOT move it. After
    // POINTER_IDLE_MS the own-hole gag class goes on.
    await page.mouse.move(40, 40);
    await page.waitForTimeout(POINTER_IDLE_MS + 400);
    expect(
      await fishingClassOn(page),
      "the loop did not engage on idle — werner-fishing class is absent (check the WERNER-ICE flag + POINTER_IDLE_MS)",
    ).toBe(true);

    // Pin the mascot so the clip is static (articulation, not translation).
    await pinMascot(page);
    const box = await mascotBox(page);
    // The rod + line + fish live around/above the rod tip (local (66,5) in the
    // 64-viewBox), which sits at the mascot's top-right and OVERFLOWS upward
    // (overflow:visible). Clip a generous region covering the rod arc, the line,
    // and the fish below the tip so every track's motion is captured.
    const clip = {
      x: Math.max(0, box.x - 8),
      y: Math.max(0, box.y - 24),
      width: box.width + 48,
      height: box.height + 48,
    };

    // ── Sample across a FULL cycle: distinct phases + never-static. ──
    // Grab the clip at ~8 evenly-spaced moments across one 6400ms period. The
    // beats (cast/wait/bob/nibble/yank/miss/slump/reset) move the rod, fish, and
    // line differently, so consecutive grabs must DIFFER (the gag animates), and
    // the loop must NEVER settle into a single repeated frame (no "caught"
    // terminal — it always keeps moving).
    const STEPS = 8;
    const stepMs = Math.floor(FISHING_CYCLE_MS / STEPS);
    const frames = [];
    for (let i = 0; i < STEPS + 1; i++) {
      frames.push(decodePng(await page.screenshot({ clip })));
      // No white card at any beat, in any theme — the fish/line/rod are all
      // token-coloured marks over the transparent surround, never a box.
      expect(
        whiteBoxFraction(frames[frames.length - 1]),
        `a white card appeared at loop step ${i} (the gag must never flash a white box)`,
      ).toBeLessThan(0.25);
      if (i < STEPS) await page.waitForTimeout(stepMs);
    }

    // DISTINCT PHASES: the mean adjacent-frame diff must clear a real threshold
    // (the cartoon is moving), and at least most adjacent pairs must differ (it
    // is not a single held pose with one twitch). frameMeanAbsDiff of two
    // byte-identical frames is 0; a moving rod/fish/line clears a few units.
    const diffs: number[] = [];
    for (let i = 1; i < frames.length; i++) {
      diffs.push(frameMeanAbsDiff(frames[i - 1], frames[i]));
    }
    const movingPairs = diffs.filter((d) => d > 0.5).length;
    expect(
      movingPairs,
      `the loop did not animate through distinct phases: only ${movingPairs}/${diffs.length} ` +
        `adjacent frame pairs changed (diffs=${diffs.map((d) => d.toFixed(2)).join(",")}) — ` +
        "a static (caught/terminal) loop would show ~0 moving pairs",
    ).toBeGreaterThanOrEqual(Math.ceil(diffs.length / 2));

    // NEVER A STATIC "CAUGHT" TERMINAL: the loop must keep moving across the
    // WHOLE window — the LAST stretch must animate just as much as the first
    // (it never settles into a frozen success pose). Compare the late-window
    // mean diff to the early-window mean diff; both must be clearly non-zero.
    const half = Math.floor(diffs.length / 2);
    const early = diffs.slice(0, half);
    const late = diffs.slice(half);
    const mean = (xs: number[]) =>
      xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length);
    expect(
      mean(late),
      `the loop went static in its later phases (late mean diff ${mean(late).toFixed(2)}) — ` +
        "it must keep trying forever, never settle into a caught/terminal frame",
    ).toBeGreaterThan(0.5);
    expect(mean(early), "the loop never started animating").toBeGreaterThan(0.5);

    // ── FIXED-STATION HAND-OFF: a pointer move drops the gag, and Werner STAYS
    //    PUT (the reel that used to chase the cursor is gone). ──
    // Move the pointer to a far in-viewport point and keep NUDGING it so it stays
    // non-idle (< POINTER_IDLE_MS). The gag class must drop within one rAF leg,
    // and — the whole point of the 2026-07-02 rework — the mascot's position must
    // NOT move toward the cursor: the cursor is the bait, not a lure Werner
    // chases. Un-pin first so that IF a stray reel regression returned, it could
    // move him (making this a real, non-vacuous guard).
    const startCenter = {
      cx: box.x + box.width / 2,
      cy: box.y + box.height / 2,
    };
    const target = { x: startCenter.cx + 300, y: startCenter.cy + 180 };
    const home = await mascotBox(page);
    await page.evaluate(() => {
      const el = document.querySelector(
        '[data-testid="penguin-mascot"]',
      ) as HTMLElement | null;
      if (el) el.style.transition = "";
    });
    await page.mouse.move(target.x, target.y, { steps: 4 });

    // The gag must stop essentially immediately (the station rAF removes the
    // class the same frame it sees a non-idle pointer).
    await expect
      .poll(async () => fishingClassOn(page), {
        message:
          "the gag did not hand off: werner-fishing class is still on after the pointer moved",
        timeout: 1000,
      })
      .toBe(false);

    // FIXED STATION: keep the pointer non-idle and confirm the mascot does NOT
    // drift toward the cursor. A tolerance a few px wide absorbs sub-pixel layout
    // noise; a returned reel would close ~300px, so this is a genuine guard.
    const t0 = Date.now();
    while (Date.now() - t0 < 900) {
      const jitter = (Date.now() - t0) % 2 === 0 ? 0.5 : -0.5;
      await page.mouse.move(target.x + jitter, target.y + jitter, { steps: 1 });
      await page.waitForTimeout(50);
    }
    const after = await mascotBox(page);
    const drift = Math.hypot(
      after.x + after.width / 2 - (home.x + home.width / 2),
      after.y + after.height / 2 - (home.y + home.height / 2),
    );
    expect(
      drift,
      `Werner CHASED the cursor after the gag handed off (moved ${drift.toFixed(0)}px ` +
        `from his station) — the fixed-station rework requires he stay put; the reel is gone`,
    ).toBeLessThan(8);
  });
});

test.describe("SPR-05 — reduced motion: the loop NEVER runs (static neutral)", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("under reduced motion the loop class is never added and the mascot is static (no gag, no white card)", async ({
    page,
  }) => {
    await loadMascot(page, ROAMING);
    // Leave the pointer idle well past POINTER_IDLE_MS — under reduced motion the
    // reel effect early-returns, so the loop class is NEVER added.
    await page.mouse.move(40, 40);
    await page.waitForTimeout(POINTER_IDLE_MS + 600);
    expect(
      await fishingClassOn(page),
      "reduced motion must NOT run the fishing loop (the werner-fishing class must stay off)",
    ).toBe(false);

    // And the penguin region is visually static across ~2s (no involuntary gag)
    // and shows no white card — the still neutral pose.
    const box = await mascotBox(page);
    const clip = {
      x: Math.max(0, box.x - 8),
      y: Math.max(0, box.y - 24),
      width: box.width + 48,
      height: box.height + 48,
    };
    const a = decodePng(await page.screenshot({ clip }));
    await page.waitForTimeout(2000);
    const b = decodePng(await page.screenshot({ clip }));
    expect(
      frameMeanAbsDiff(a, b),
      "reduced motion must be static — the penguin region changed over 2s",
    ).toBeLessThan(0.5);
    expect(
      whiteBoxFraction(a),
      "reduced motion must not show a white card",
    ).toBeLessThan(0.25);
  });
});
