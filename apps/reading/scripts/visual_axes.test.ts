import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { config as lostpixel } from "../lostpixel.config";
import preview from "../.storybook/preview";
import {
  DARK_SHOT,
  FREEZE_STYLE_ID,
  expectTheme,
  freezeMotion,
  isDarkShot,
  storyUrl,
  withThemeGlobal,
  type AxisPage,
} from "../.storybook/visual-axes";

/**
 * A Playwright-shaped page backed by this jsdom document. `goto` plays the
 * preview: the theme global in the URL lands on <html data-theme>, unless the
 * test says the preview is broken.
 */
function fakePage(start: string, opts: { previewApplies?: boolean } = {}) {
  let url = start;
  const calls: string[] = [];
  const page = {
    url: () => url,
    async emulateMedia(o: { colorScheme: string }) {
      calls.push(`emulateMedia:${o.colorScheme}`);
    },
    async goto(next: string) {
      calls.push(`goto:${next}`);
      url = next;
      const theme = new URL(next).searchParams.get("globals")?.match(/theme:(\w+)/)?.[1];
      if (theme && opts.previewApplies !== false) {
        document.documentElement.setAttribute("data-theme", theme);
      }
    },
    async waitForLoadState() {},
    async evaluate<R, A>(fn: (arg: A) => R | Promise<R>, arg: A): Promise<R> {
      return fn(arg);
    },
    async waitForFunction<A>(fn: (arg: A) => unknown, arg: A) {
      if (!fn(arg)) throw new Error("Timeout 15000ms exceeded.");
      return true;
    },
  };
  return { page, calls };
}

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-theme-pref");
  document.body.className = "";
  document.getElementById(FREEZE_STYLE_ID)?.remove();
});

describe("withThemeGlobal / storyUrl", () => {
  it("sets the theme global and keeps the story's other globals", () => {
    const u = new URL(withThemeGlobal("http://h/iframe.html?id=a--b&globals=viewport:m;theme:light", "dark"));
    expect(u.searchParams.get("globals")).toBe("viewport:m;theme:dark");
    expect(u.searchParams.get("id")).toBe("a--b");
  });

  it("builds a story iframe URL in the asked theme", () => {
    const u = new URL(storyUrl("http://127.0.0.1:6006/", "lemon-card--default", "dark"));
    expect(u.pathname).toBe("/iframe.html");
    expect(u.searchParams.get("id")).toBe("lemon-card--default");
    expect(u.searchParams.get("globals")).toBe("theme:dark");
  });
});

describe("isDarkShot", () => {
  it("matches lost-pixel's id for the dark extra shot and nothing else", () => {
    expect(isDarkShot(`lemon-card--default__[w1280px]-${DARK_SHOT.name}`)).toBe(true);
    expect(isDarkShot("lemon-card--default__[w1280px]")).toBe(false);
    expect(isDarkShot("theme-toggle--on-dark__[w1280px]")).toBe(false);
  });
});

describe("expectTheme", () => {
  it("passes when the preview wrote the theme", async () => {
    document.documentElement.setAttribute("data-theme", "dark");
    await expect(expectTheme(fakePage("http://h/").page, "dark")).resolves.toBe("rendered");
  });

  it("throws when the render is in the other theme", async () => {
    document.documentElement.setAttribute("data-theme", "light");
    await expect(expectTheme(fakePage("http://h/").page, "dark")).rejects.toThrow(
      /expected <html data-theme="dark">, found "light"/,
    );
  });

  it("lets Storybook's own error screen through, since it is the same in both themes", async () => {
    document.body.classList.add("sb-show-errordisplay");
    await expect(expectTheme(fakePage("http://h/").page, "dark")).resolves.toBe("storybook-error");
  });
});

describe("freezeMotion", () => {
  it("adds one style that zeroes animation and transition timing", async () => {
    const { page } = fakePage("http://h/");
    await freezeMotion(page as AxisPage);
    await freezeMotion(page as AxisPage);
    const styles = document.querySelectorAll(`#${FREEZE_STYLE_ID}`);
    expect(styles).toHaveLength(1);
    const css = styles[0].textContent ?? "";
    for (const rule of ["animation-duration: 0s", "transition-duration: 0s", "animation-delay: 0s"]) {
      expect(css).toContain(rule);
    }
  });
});

describe("preview: theme global, ground and the dark axis", () => {
  it("offers system, light and dark, defaulting to system", () => {
    const theme = preview.globalTypes?.theme as {
      defaultValue: string;
      toolbar: { items: { value: string }[] };
    };
    expect(theme.defaultValue).toBe("system");
    expect(theme.toolbar.items.map((i) => i.value).sort()).toEqual(["dark", "light", "system"]);
  });

  it("paints story grounds from tokens, never a fixed day hex", () => {
    const bg = preview.parameters?.backgrounds as { default: string; values: { name: string; value: string }[] };
    expect(bg.values.find((v) => v.name === bg.default)?.value).toBe("var(--bg-page)");
    for (const v of bg.values) expect(v.value).toMatch(/^var\(--[a-z-]+\)$/);
  });

  it("writes the chosen theme onto the preview <html>", () => {
    const decorate = preview.decorators as unknown as ((
      story: () => ReactElement | null,
      ctx: { globals: Record<string, unknown>; parameters: Record<string, unknown> },
    ) => unknown)[];
    for (const theme of ["dark", "light"]) {
      for (const d of decorate) d(() => null, { globals: { theme }, parameters: {} });
      expect(document.documentElement.getAttribute("data-theme")).toBe(theme);
    }
  });

  it("gives every story a dark lost-pixel extra shot", () => {
    expect(preview.parameters?.lostpixel).toEqual({
      extraShots: [{ name: DARK_SHOT.name, suffix: DARK_SHOT.suffix }],
    });
  });
});

describe("lostpixel beforeScreenshot", () => {
  const shoot = lostpixel.beforeScreenshot as unknown as (
    page: unknown,
    input: { shotMode: "storybook"; id?: string; shotName?: string },
  ) => Promise<void>;
  const START = "http://127.0.0.1:9/iframe.html?id=lemon-card--default&viewMode=story&args=&width=1280";

  it("reloads the dark shot with the dark theme global and a dark colour scheme", async () => {
    const { page, calls } = fakePage(START);
    await shoot(page, { shotMode: "storybook", id: `lemon-card--default__[w1280px]-${DARK_SHOT.name}` });
    expect(calls[0]).toBe("emulateMedia:dark");
    expect(calls[1]).toMatch(/^goto:/);
    expect(new URL(calls[1].slice(5)).searchParams.get("globals")).toBe("theme:dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("fails the run when the dark shot would really be a day render", async () => {
    const { page } = fakePage(START, { previewApplies: false });
    document.documentElement.setAttribute("data-theme", "light");
    await expect(
      shoot(page, { shotMode: "storybook", id: `lemon-card--default__[w1280px]-${DARK_SHOT.name}` }),
    ).rejects.toThrow(/data-theme="dark"/);
  });

  it("leaves the day shot's navigation alone but checks it is day", async () => {
    const { page, calls } = fakePage(START);
    document.documentElement.setAttribute("data-theme", "light");
    await shoot(page, { shotMode: "storybook", id: "lemon-card--default__[w1280px]" });
    expect(calls).toEqual([]);
    document.documentElement.setAttribute("data-theme", "dark");
    await expect(shoot(page, { shotMode: "storybook", id: "lemon-card--default__[w1280px]" })).rejects.toThrow(
      /data-theme="light"/,
    );
  });

  it("keeps comparing against committed baselines", () => {
    expect((lostpixel as { generateOnly?: boolean }).generateOnly).toBe(false);
    expect(lostpixel.threshold).toBe(0.004);
  });
});
