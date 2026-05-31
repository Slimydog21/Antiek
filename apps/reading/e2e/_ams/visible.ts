/**
 * _ams/visible.ts — the shared visible-outcome helpers (SPR-01, milestone 3).
 *
 * WHY THIS EXISTS (RULE 2 — prove it in a browser, or it isn't done)
 * -----------------------------------------------------------------
 * AMS-v1 shipped 972 green vitest tests and an INVISIBLE shell: the mountain
 * was occluded, windows never opened, the igloo had no caption. Every test
 * mounted components in isolation, so nothing ever loaded the real app on the
 * real route and asserted "a mountain is VISIBLE." These helpers close that
 * gap: they sample real rendered pixels + real DOM on a real Playwright Page.
 *
 * Each helper documents exactly WHAT visible fact it proves and HOW. The pixel
 * helpers (decodePng, regionVariance, isSolidColor, contrastRatio) are PURE and
 * unit-tested in visible.pixel.test.ts — feeding `isSolidColor` a synthetic
 * solid-ice/space buffer FAILS, proving assertSceneVisible would reject an
 * occluded/empty scene rather than pass vacuously.
 *
 * Import surface (what later sprints use):
 *   assertSceneVisible(page, opts?)         — the mountain actually paints
 *   assertWindowOpen(page)                  — a floating window is on screen
 *   assertLabeled(page, target, text)       — a control has a VISIBLE caption
 *   assertHotkeyOverlay(page, opts?)        — the ⌘ cheat-sheet is on screen
 *   assertContrast(page, selector, min?)    — fg/bg meets ~WCAG-AA
 *   + the pure helpers, exported for unit calibration.
 */

import { expect, type Locator, type Page } from "@playwright/test";
import { PNG } from "pngjs";

// ───────────────────────────────────────────────────────────────────────────
// PURE PIXEL HELPERS (unit-testable; no Playwright)
// ───────────────────────────────────────────────────────────────────────────

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export interface DecodedImage {
  width: number;
  height: number;
  /** RGBA bytes, length = width*height*4. */
  data: Buffer | Uint8Array;
}

/** Decode a PNG buffer (e.g. from page.screenshot()) to RGBA pixels. */
export function decodePng(buf: Buffer | Uint8Array): DecodedImage {
  const png = PNG.sync.read(Buffer.from(buf));
  return { width: png.width, height: png.height, data: png.data };
}

/** A rectangular sub-region in pixels. */
export interface PixelRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Per-channel variance across the sampled region, averaged over R,G,B.
 * A solid-color frame → ~0. A painted scene (gradient sky + peaks + clouds +
 * snow) → a clearly non-zero spread. This is the core signal: a z-0 scene
 * occluded by a flat `bg-ice-2`/`bg-space-2` body reads as ONE near-constant
 * colour and so scores ~0; an actually-visible moving mountainscape does not.
 */
export function regionVariance(img: DecodedImage, region?: PixelRegion): number {
  const { width, height, data } = img;
  const rx = Math.max(0, Math.floor(region?.x ?? 0));
  const ry = Math.max(0, Math.floor(region?.y ?? 0));
  const rw = Math.min(width - rx, Math.floor(region?.width ?? width));
  const rh = Math.min(height - ry, Math.floor(region?.height ?? height));
  if (rw <= 0 || rh <= 0) return 0;

  let n = 0;
  let sumR = 0;
  let sumG = 0;
  let sumB = 0;
  let sumR2 = 0;
  let sumG2 = 0;
  let sumB2 = 0;
  for (let y = ry; y < ry + rh; y++) {
    for (let x = rx; x < rx + rw; x++) {
      const i = (y * width + x) * 4;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      sumR += r;
      sumG += g;
      sumB += b;
      sumR2 += r * r;
      sumG2 += g * g;
      sumB2 += b * b;
      n++;
    }
  }
  if (n === 0) return 0;
  const varOf = (sum: number, sum2: number) => Math.max(0, sum2 / n - (sum / n) ** 2);
  return (varOf(sumR, sumR2) + varOf(sumG, sumG2) + varOf(sumB, sumB2)) / 3;
}

/** Count of DISTINCT-enough colours (quantized) in a region — a second signal. */
export function distinctColors(img: DecodedImage, region?: PixelRegion, bucket = 16): number {
  const { width, height, data } = img;
  const rx = Math.max(0, Math.floor(region?.x ?? 0));
  const ry = Math.max(0, Math.floor(region?.y ?? 0));
  const rw = Math.min(width - rx, Math.floor(region?.width ?? width));
  const rh = Math.min(height - ry, Math.floor(region?.height ?? height));
  const seen = new Set<number>();
  for (let y = ry; y < ry + rh; y++) {
    for (let x = rx; x < rx + rw; x++) {
      const i = (y * width + x) * 4;
      const r = Math.floor(data[i] / bucket);
      const g = Math.floor(data[i + 1] / bucket);
      const b = Math.floor(data[i + 2] / bucket);
      seen.add((r << 16) | (g << 8) | b);
    }
  }
  return seen.size;
}

/**
 * Calibrated "is this region effectively one flat colour?" predicate — the
 * thing assertSceneVisible negates. Default threshold chosen so a single solid
 * fill (variance ~0, 1 distinct colour) is SOLID, while the procedural sky
 * gradient + peaks (many colours, real variance) is NOT.
 *
 *   variance threshold: 12   (channel-variance units, 0–65025 scale)
 *   distinct-colour floor: 4 (quantized buckets)
 *
 * A frame is "solid" iff variance < threshold AND distinct colours ≤ floor.
 * Requiring BOTH avoids false-solid on a faint dithered gradient and avoids
 * false-painted on a noisy-but-monochrome compression artifact.
 */
export const SCENE_SOLID_VARIANCE_THRESHOLD = 12;
export const SCENE_SOLID_DISTINCT_FLOOR = 4;

export function isSolidColor(
  img: DecodedImage,
  region?: PixelRegion,
  varianceThreshold: number = SCENE_SOLID_VARIANCE_THRESHOLD,
  distinctFloor: number = SCENE_SOLID_DISTINCT_FLOOR,
): boolean {
  const v = regionVariance(img, region);
  const c = distinctColors(img, region);
  return v < varianceThreshold && c <= distinctFloor;
}

/** Relative luminance per WCAG 2.x. */
export function relativeLuminance({ r, g, b }: Rgb): number {
  const ch = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

/** WCAG contrast ratio between two colours (1…21). */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// ───────────────────────────────────────────────────────────────────────────
// PLAYWRIGHT ASSERTIONS (run against a real rendered Page)
// ───────────────────────────────────────────────────────────────────────────

/** A viewport region as FRACTIONS (0–1) — the area assertSceneVisible samples. */
export interface SceneRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AssertSceneOptions {
  varianceThreshold?: number;
  distinctFloor?: number;
}

/**
 * PROVES: a non-trivial fraction of the viewport is the actually-painted moving
 * scene — NOT by the <Scene/> component existing (it always does; it is
 * `aria-hidden z-0` and stays in the DOM even when occluded), but by decoding
 * real screenshot pixels over a region behind the chrome and asserting they are
 * NOT one flat ice/space colour.
 *
 * CONTRACT (SPR-01 sharpen — the false-green this prevents): `region` is
 * REQUIRED and MUST be a viewport area that is UNAMBIGUOUSLY scene — not chrome,
 * not a text panel. A region that includes chrome/text passes on TEXT variance
 * even when the mountain is occluded (a fake gate — exactly v1's failure mode).
 * There is deliberately NO default region: SPR-03 must consciously choose its
 * scene-only fraction when it flips the anchor green, so "passes but doesn't test
 * the thing" cannot recur by omission.
 *
 * TODAY (origin/main) a scene-only region FAILS on the default route: the landing
 * route body paints an opaque `bg-ice-2 dark:bg-space-2` over the z-0 scene, so
 * the sampled region is one flat colour → isSolidColor === true → assertion fails.
 * SPR-03 (glass surface model) removes the occlusion and flips it green.
 */
export async function assertSceneVisible(
  page: Page,
  region: SceneRegion,
  opts: AssertSceneOptions = {},
): Promise<void> {
  const vp = page.viewportSize() ?? { width: 1280, height: 800 };
  const f = region;
  const clip = {
    x: Math.round(f.x * vp.width),
    y: Math.round(f.y * vp.height),
    width: Math.round(f.width * vp.width),
    height: Math.round(f.height * vp.height),
  };
  const shot = await page.screenshot({ clip });
  const img = decodePng(shot);
  const solid = isSolidColor(
    img,
    undefined, // the screenshot is already clipped to the region
    opts.varianceThreshold ?? SCENE_SOLID_VARIANCE_THRESHOLD,
    opts.distinctFloor ?? SCENE_SOLID_DISTINCT_FLOOR,
  );
  const variance = regionVariance(img);
  const colors = distinctColors(img);
  expect(
    solid,
    `scene not visible: sampled band (${clip.width}x${clip.height} @ ${clip.x},${clip.y}) is a flat colour ` +
      `(variance=${variance.toFixed(1)} < ${opts.varianceThreshold ?? SCENE_SOLID_VARIANCE_THRESHOLD}, ` +
      `distinctColors=${colors} ≤ ${opts.distinctFloor ?? SCENE_SOLID_DISTINCT_FLOOR}). ` +
      `An opaque route body is occluding the z-0 mountainscape (SPR-03 fixes this).`,
  ).toBe(false);
}

/**
 * PROVES: a floating workspace window is present AND visible. The real
 * WindowsLayer (components/windows/WindowsLayer.tsx) returns null until a
 * window exists in the store and renders each window as
 * `<div role="dialog" data-window-mode=…>` inside `[data-windows-layer]`.
 *
 * TODAY (origin/main) a product click navigates full-page and opens NO window
 * by default, so this fails on the default route. SPR-04 makes a product click
 * open a sub-action window by default and flips it green.
 */
export async function assertWindowOpen(page: Page): Promise<void> {
  const win = page.locator('[data-windows-layer] [role="dialog"][data-window-mode]');
  await expect(win.first(), "no floating workspace window is open (SPR-04 makes windows the default)").toBeVisible(
    { timeout: 5_000 },
  );
}

/** A target for assertLabeled: a CSS selector string or an existing Locator. */
export type LabelTarget = string | Locator;

/**
 * PROVES: a control carries the given VISIBLE text caption — not merely an
 * aria-label. We resolve the target, then assert its rendered text content (or
 * a visible descendant text node) equals/contains `text`. An element that has
 * only `aria-label="…"` and no on-screen caption FAILS.
 *
 * TODAY (origin/main) the igloo home button is `<button aria-label="Antiek
 * home">` with only an <IglooMark/> and NO visible "Home" caption, so
 * assertLabeled(page, iglooSelector, "Home") fails. SPR-07 adds the caption.
 */
export async function assertLabeled(page: Page, target: LabelTarget, text: string): Promise<void> {
  const loc = typeof target === "string" ? page.locator(target) : target;
  await expect(loc.first(), `target not found for label "${text}"`).toBeAttached({ timeout: 5_000 });
  // A VISIBLE text node containing `text`, scoped within the target.
  const visibleCaption = loc.first().getByText(text, { exact: false });
  await expect(
    visibleCaption,
    `control has no VISIBLE caption "${text}" (an aria-label alone does not count — this is the SPR-07 igloo anchor)`,
  ).toBeVisible({ timeout: 5_000 });
}

export interface AssertHotkeyOptions {
  /** If true, press "?" first to summon the HUD (it is toggled, not default). */
  summon?: boolean;
}

/**
 * PROVES: the HotkeyHud cheat-sheet (the ⌘ overlay) is on screen. The real HUD
 * (components/hotkeys/HotkeyHud.tsx) returns null until opened via "?" and then
 * renders a LemonModal titled "Keyboard shortcuts" containing `.antiek-hud`.
 *
 * The SPR-08 anchor is that the ⌘ scheme is not surfaced uniformly by default
 * (and vim chords exist). With `summon:false` (default) this checks the HUD is
 * already visible — which it is NOT by default today, the red anchor; SPR-08
 * decides the default-surfacing policy. With `summon:true` it presses "?" then
 * asserts the modal — used to prove the HUD itself works.
 */
export async function assertHotkeyOverlay(page: Page, opts: AssertHotkeyOptions = {}): Promise<void> {
  if (opts.summon) {
    await page.keyboard.press("?");
  }
  const hud = page.locator(".antiek-hud");
  await expect(
    hud.first(),
    "the ⌘ hotkey overlay (HotkeyHud) is not on screen (SPR-08 owns the default-surfacing + chord removal)",
  ).toBeVisible({ timeout: 5_000 });
}

/**
 * PROVES: the foreground text of `selector` meets a ~WCAG-AA contrast ratio
 * against its rendered background. Reads the computed colours from the live
 * DOM (so it reflects the real token values), parses them, and asserts the
 * ratio. Used by SPR-03/SPR-09 to guarantee the glass + lighter-yellow changes
 * keep text legible.
 */
export async function assertContrast(page: Page, selector: string, min = 4.5): Promise<void> {
  const colors = await page.locator(selector).first().evaluate((el) => {
    const cs = getComputedStyle(el as Element);
    // Walk up for a non-transparent background.
    let bgEl: Element | null = el as Element;
    let bg = cs.backgroundColor;
    while (bgEl && (bg === "rgba(0, 0, 0, 0)" || bg === "transparent")) {
      bgEl = bgEl.parentElement;
      bg = bgEl ? getComputedStyle(bgEl).backgroundColor : "rgb(255, 255, 255)";
    }
    return { fg: cs.color, bg: bg || "rgb(255, 255, 255)" };
  });
  const parse = (s: string): Rgb => {
    const m = s.match(/rgba?\(([^)]+)\)/);
    const parts = (m?.[1] ?? "0,0,0").split(",").map((p) => parseFloat(p.trim()));
    return { r: parts[0] ?? 0, g: parts[1] ?? 0, b: parts[2] ?? 0 };
  };
  const ratio = contrastRatio(parse(colors.fg), parse(colors.bg));
  expect(
    ratio,
    `contrast ${ratio.toFixed(2)} below ${min} for "${selector}" (fg=${colors.fg}, bg=${colors.bg})`,
  ).toBeGreaterThanOrEqual(min);
}
