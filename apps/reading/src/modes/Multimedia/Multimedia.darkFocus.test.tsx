/**
 * FFX SPR-04 M6 (F-15) and M7 (F-17, Multimedia half).
 *
 * M6: the "Unsourced claim guard" must be readable in dark mode. jsdom does
 * not evaluate `prefers-color-scheme`, so the dark colours are resolved the
 * way Tailwind (darkMode: "media") resolves them: an element's `dark:text-*`
 * class if it has one, else its static `text-*` class; the background is the
 * guard's `bg-sun/10` veil composited over the nearest ancestor's
 * `dark:bg-*`. Every hex comes from tailwind.config.js, so a token change that
 * breaks the pair reddens here. WCAG AA for this text size is 4.5:1.
 *
 * M7: the Custom duration input must show a focus indicator. The input's real
 * rendered classes are compiled with the project's Tailwind config into a
 * stylesheet, the input is reached with Tab, and getComputedStyle must report
 * a box-shadow or a visible outline.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import postcss from "postcss";
import tailwind from "tailwindcss";
import { afterEach, describe, expect, it, vi } from "vitest";

import { contrastRatio, over, type Rgb } from "../../../e2e/_ams/visible";

// Loaded the way design/type-scale.test.ts loads it (the config is untyped JS).
const APP = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const rawConfig = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));
const tailwindConfig = (rawConfig.default ?? rawConfig) as {
  theme: { extend: { colors: Record<string, string> } };
};

vi.mock("./VoiceSteeringInput", () => ({ VoiceSteeringInput: () => null }));

vi.mock("../../api/multimedia", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/multimedia")>();
  return {
    ...actual,
    listMultimediaAssets: vi.fn().mockResolvedValue({ assets: [], count: 0 }),
    getMultimediaReviewedVisualSet: vi.fn().mockRejectedValue(new Error("unavailable")),
    // A failed create still opens the offline example storyboard, which is
    // where the guard renders without a persisted plan (F-15's repro state).
    createMultimediaDraft: vi.fn().mockRejectedValue(new Error("offline")),
  };
});

import Multimedia from "./index";

const COLORS = tailwindConfig.theme.extend.colors;

function hex(token: string): Rgb {
  const value = COLORS[token];
  expect(value, `token ${token}`).toMatch(/^#[0-9A-Fa-f]{6}$/);
  return {
    r: parseInt(value.slice(1, 3), 16),
    g: parseInt(value.slice(3, 5), 16),
    b: parseInt(value.slice(5, 7), 16),
  };
}

/** The text colour token Tailwind applies to `el` under prefers-color-scheme: dark. */
function darkTextToken(el: Element): string {
  const cls = Array.from(el.classList);
  const dark = cls.find((c) => c.startsWith("dark:text-") && c.slice(10) in COLORS);
  if (dark) return dark.slice("dark:text-".length);
  const light = cls.find((c) => c.startsWith("text-") && c.slice(5) in COLORS);
  expect(light, `a text colour class on <${el.tagName.toLowerCase()} class="${el.className}">`).toBeTruthy();
  return light!.slice("text-".length);
}

/** The opaque dark background token of the nearest ancestor that paints one. */
function darkPanelToken(el: Element): string {
  for (let n = el.parentElement; n; n = n.parentElement) {
    const dark = Array.from(n.classList).find((c) => c.startsWith("dark:bg-") && c.slice(8) in COLORS);
    if (dark) return dark.slice("dark:bg-".length);
  }
  throw new Error("no ancestor paints a dark background");
}

async function compiledCssFor(el: Element): Promise<string> {
  const result = await postcss([
    tailwind({
      ...(tailwindConfig as object),
      content: [{ raw: el.outerHTML, extension: "html" }],
      corePlugins: { preflight: false },
    } as Parameters<typeof tailwind>[0]),
  ]).process("@tailwind utilities;", { from: undefined });
  return result.css;
}

function hasVisibleFocus(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  const shadow = cs.boxShadow.trim();
  const twShadow = cs.getPropertyValue("--tw-shadow").trim();
  const shadowShown = shadow !== "" && shadow !== "none" && (!shadow.includes("var(") || twShadow !== "");
  const outlineShown =
    cs.outlineStyle !== "none" && cs.outlineStyle !== "" && !/transparent/.test(cs.outline) && cs.outline !== "";
  return shadowShown || outlineShown;
}

afterEach(() => {
  cleanup();
  document.head.querySelectorAll("style[data-test-tailwind]").forEach((s) => s.remove());
});

describe("Multimedia unsourced-claim guard in dark mode (F-15)", () => {
  it("label and body text clear 4.5:1 against the guard's own dark background", async () => {
    render(<Multimedia />);
    const review = screen.getByRole("button", { name: "Review plan" });
    await waitFor(() => expect(review.getAttribute("disabled")).toBeNull());
    fireEvent.click(review);
    const label = await screen.findByText("Unsourced claim guard");
    const guard = label.parentElement as HTMLElement;
    expect(guard.className).toContain("bg-sun/10");
    const body = guard.querySelector("ul, p:not(:first-child)") as HTMLElement;
    expect(body).toBeTruthy();

    const panel = darkPanelToken(guard);
    const bg = over({ ...hex("sun"), a: 0.1 }, hex(panel));
    for (const el of [label, body]) {
      const token = darkTextToken(el);
      const fg = hex(token);
      const ratio = contrastRatio(fg, bg);
      expect(fg, `${token} differs from the panel`).not.toEqual(bg);
      expect(ratio, `${token} on sun/10 over ${panel}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("Multimedia custom-duration input focus (F-17)", () => {
  it("shows a focus indicator after Tab reaches it", async () => {
    render(<Multimedia />);
    const input = await screen.findByRole("spinbutton", { name: "Custom duration" });
    const style = document.createElement("style");
    style.setAttribute("data-test-tailwind", "");
    style.textContent = await compiledCssFor(input);
    document.head.appendChild(style);

    const user = userEvent.setup();
    for (let i = 0; i < 200 && document.activeElement !== input; i++) await user.tab();
    expect(document.activeElement).toBe(input);
    expect(hasVisibleFocus(input)).toBe(true);
  });
});
