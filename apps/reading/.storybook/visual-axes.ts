/**
 * The axes story verdicts are rendered on, shared by the tools that render
 * stories to judge them (lostpixel.config.ts first).
 *
 * Theme. The preview's `theme` global (preview.tsx) writes `data-theme` on the
 * preview <html>, the same attribute the app's boot script sets, so a story
 * rendered with `globals=theme:dark` is the night product, not a day story on
 * a dark page. Every tool forces the theme explicitly (URL global or emulated
 * colour scheme) and then checks `data-theme` before it judges anything: an
 * axis that silently fell back to day would be a gate that cannot see night.
 *
 * This file has no imports on purpose: it is loaded by esbuild (lost-pixel),
 * tsx and the Storybook test-runner's own transpiler.
 */

export const AXIS_THEMES = ["light", "dark"] as const;
export type AxisTheme = (typeof AXIS_THEMES)[number];

/**
 * The lost-pixel extra shot that re-takes every story at night. preview.tsx
 * declares it as a project-level `lostpixel.extraShots` parameter, so every
 * story inherits it; lost-pixel names the file `<kind>--<story>--dark__[wN].png`
 * and gives the shot the id `<story-id>__[wN]-dark-axis`.
 */
export const DARK_SHOT = { name: "dark-axis", suffix: "dark" } as const;

export function isDarkShot(shotId: string): boolean {
  return shotId.endsWith(`-${DARK_SHOT.name}`);
}

/**
 * Set the preview's theme global through the story URL, keeping any other
 * globals the URL already carries. Storybook reads `globals=key:value;...`.
 */
export function withThemeGlobal(url: string, theme: AxisTheme): string {
  const u = new URL(url);
  const kept = (u.searchParams.get("globals") ?? "")
    .split(";")
    .filter((pair) => pair && !pair.startsWith("theme:"));
  u.searchParams.set("globals", [...kept, `theme:${theme}`].join(";"));
  return u.toString();
}

/** The iframe URL of one story in one theme. */
export function storyUrl(storybook: string, storyId: string, theme: AxisTheme): string {
  const base = storybook.replace(/\/+$/, "");
  return withThemeGlobal(`${base}/iframe.html?id=${storyId}&viewMode=story`, theme);
}

/** The structural slice of a Playwright page these helpers use. */
export type AxisPage = {
  evaluate<R, A>(fn: (arg: A) => R | Promise<R>, arg: A): Promise<R>;
  waitForFunction<A>(
    fn: (arg: A) => unknown,
    arg: A,
    options?: { timeout?: number },
  ): Promise<unknown>;
};

/**
 * Wait until the preview has rendered the story in `theme`. Storybook's own
 * error and no-preview screens also end the wait: a story that cannot render
 * shows the same screen in both themes. Anything else throws, because a shot
 * or an audit taken in the wrong theme would pass for the wrong reason.
 */
export async function expectTheme(
  page: AxisPage,
  theme: AxisTheme,
  timeout = 15_000,
): Promise<"rendered" | "storybook-error"> {
  try {
    await page.waitForFunction(
      (want) =>
        document.documentElement.getAttribute("data-theme") === want ||
        document.body?.classList.contains("sb-show-errordisplay") ||
        document.body?.classList.contains("sb-show-nopreview"),
      theme,
      { timeout },
    );
  } catch {
    const found = await page.evaluate(
      () => document.documentElement.getAttribute("data-theme"),
      undefined,
    );
    throw new Error(
      `visual axes: expected <html data-theme="${theme}">, found ${JSON.stringify(found)}. ` +
        "The preview's theme global did not apply, so this render would not show the " +
        `${theme} theme. Check .storybook/preview.tsx.`,
    );
  }
  const seen = await page.evaluate(
    () => document.documentElement.getAttribute("data-theme"),
    undefined,
  );
  return seen === theme ? "rendered" : "storybook-error";
}
