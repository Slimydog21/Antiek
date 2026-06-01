/**
 * scene-living.spec.ts — AMS-v2 SPR-05 EXPERIENCE GATE (the mandatory one).
 *
 * The anti-invisible proof, in real Chromium pixels (rigor #3: every
 * "still animating" / "never blank" claim is a BROWSER pixel-diff assertion, not
 * prose). Runs in the `chromium`/Storybook project against the REAL composed
 * AppShell story (the Scene is mounted there, no fetchScene prop → the real
 * client → typed-503 fallback in the keyless sandbox → procedural-only).
 *
 * HONEST NO-GO context: SPR-02 ruled out a generative stream
 * (docs/ams-v2/stream-spike.md). This gate does NOT prove a stream and makes no
 * cadence claim. It proves the thing that actually ships: the 60fps PROCEDURAL
 * FLOOR (useSceneClock → Clouds/Snow canvases) genuinely MOVES and NEVER goes
 * blank — both when art is present (default) and when art is forcibly ABSENT.
 *
 * THREE tests:
 *   (1) ANIMATING — screenshot scene-root at frame N, wait ~400ms, screenshot
 *       N+Δ; assert the two PNG buffers are NOT byte-identical (clouds/snow
 *       moved). Art is "present" by default but there is NO Krea key in the
 *       sandbox, so it is procedural — the floor is what moves either way.
 *   (2) ART ABSENT — abort **\/krea\/** so no art can ever arrive; assert the
 *       scene STILL animates (same pixel-diff) AND reports data-scene-fallback.
 *   (3) CLICKABILITY — a content control above the scene is clickable, proving
 *       scene-root is pointer-events-none / z-0 (it never eats input).
 *
 * reducedMotion is forced to "no-preference" (PW 1.60 contextOptions) or
 * useSceneClock FREEZES and the diff would be a false RED (zero motion).
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

// Durable visual proof lands here (rigor #5: the pixel-diff is the assertion,
// but a persisted capture is the artifact a later sprint can eyeball when this
// gate re-fails). Path is resolved from this file so it is cwd-independent.
const ARTIFACT_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "_ams",
  ".artifacts",
);

async function saveArtifact(name: string, png: Buffer): Promise<void> {
  await mkdir(ARTIFACT_DIR, { recursive: true });
  await writeFile(join(ARTIFACT_DIR, name), png);
}

// The REAL story id — Storybook slugs "Navigation / AppShell" → "navigation-
// appshell" and the "WithProjectTree" story → "with-project-tree". (The spec
// page wrote "navigation-app-shell", but Storybook collapses "AppShell" to
// "appshell"; verify in storybook-static/index.json.)
const APPSHELL_STORY = "navigation-appshell--with-project-tree";

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

// Force the clock to RUN (not freeze) for the whole file. Without this the
// procedural floor freezes under a reduce preference and the diff is a false RED.
test.use({ contextOptions: { reducedMotion: "no-preference" } });

/** Load the AppShell story and return the scene-root locator once attached. */
async function loadSceneRoot(page: Page): Promise<Locator> {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(storyUrl(APPSHELL_STORY), { waitUntil: "domcontentloaded" });
  const root = page.locator('[data-testid="scene-root"]');
  await expect(root).toBeAttached({ timeout: 10_000 });
  // Sanity: the clock is RUNNING, not frozen — otherwise the diff is vacuous.
  await expect(root).toHaveAttribute("data-scene-frozen", "false", {
    timeout: 10_000,
  });
  return root;
}

/**
 * Screenshot the scene-root at frame N, wait ~400ms (≈24 frames @ 60fps), and
 * screenshot N+Δ. The two PNG buffers must NOT be byte-identical — the canvas
 * painters (Clouds/Snow) repainted new content driven by useSceneClock. A
 * frozen/blank scene would produce two identical buffers and FAIL here.
 */
async function assertSceneAnimates(
  root: Locator,
  page: Page,
  artifactPrefix?: string,
): Promise<void> {
  const a = await root.screenshot();
  await page.waitForTimeout(400);
  const b = await root.screenshot();
  // Persist the N / N+Δ pair as the durable visual proof (when asked).
  if (artifactPrefix) {
    await saveArtifact(`${artifactPrefix}-frameN.png`, a);
    await saveArtifact(`${artifactPrefix}-frameN+delta.png`, b);
  }
  // Byte-identical ⇒ nothing moved ⇒ the floor is not animating ⇒ FAIL.
  expect(
    Buffer.compare(a, b),
    "scene-root must repaint (clouds/snow advance on the clock) — two screenshots 400ms apart must differ",
  ).not.toBe(0);
}

test.describe("AMS-v2 scene is LIVING (procedural floor, no-key sandbox)", () => {
  test("(1) animates with art present (procedural — no Krea key in sandbox)", async ({
    page,
  }) => {
    const root = await loadSceneRoot(page);
    // Art is "present" as a concept (the real client is wired) but the keyless
    // sandbox lands on fallback — so what MOVES is the procedural floor. Either
    // way the assertion is identical: the scene must visibly change.
    await assertSceneAnimates(root, page);
  });

  test("(2) STILL animates when art is forcibly ABSENT (krea aborted) + flags fallback", async ({
    page,
  }) => {
    // Kill every Krea call before navigation so no art can EVER arrive.
    await page.route("**/krea/**", (r) => r.abort());

    const root = await loadSceneRoot(page);
    // The art layer is in fallback (paints nothing); the floor is the picture.
    await expect(root).toHaveAttribute("data-scene-fallback", "true", {
      timeout: 10_000,
    });
    const krea = page.locator('[data-testid="krea-art-layer"]');
    await expect(krea).toHaveAttribute("data-krea", "fallback");

    // The decisive proof: with NO art, the scene STILL moves (never blank).
    // Persist the N / N+Δ pair — this is the honest core capture (procedural
    // floor, fallback, no live Krea), the artifact a regressing sprint reveals.
    await assertSceneAnimates(root, page, "scene-living-art-absent");
  });

  test("(3) a content control above the scene is clickable (scene-root is pointer-events-none, z-0)", async ({
    page,
  }) => {
    await loadSceneRoot(page);
    // The AppShell bottom NavRail is real chrome ABOVE the z-0 scene. The
    // "Antiek home" button is always rendered + visible in this story. If the
    // scene captured pointer events, this click would be intercepted (Playwright
    // throws on an intercepting overlay). pointer-events-none on scene-root +
    // z-0 are what let the click land on the control above it.
    const control = page.getByRole("button", { name: "Antiek home" }).first();
    await expect(control).toBeVisible({ timeout: 10_000 });
    await control.click({ timeout: 5_000 });
  });
});
