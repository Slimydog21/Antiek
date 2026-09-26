/**
 * FFX SPR-04 M7 (F-17): the Library search box shows a focus indicator.
 * The input's real rendered classes are compiled with the project's Tailwind
 * config, the input is reached with Tab, and getComputedStyle must report a
 * box-shadow or a visible outline (jsdom does not resolve var(), so a
 * var()-built shadow also needs its --tw-shadow to be set).
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import postcss from "postcss";
import tailwind from "tailwindcss";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/corpusSearch", async (orig) => ({
  ...(await orig<typeof import("../../api/corpusSearch")>()),
  corpusSearch: vi.fn(),
}));

import CorpusSearch from "./CorpusSearch";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const rawConfig = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));

async function injectTailwindFor(el: Element) {
  const result = await postcss([
    tailwind({
      ...(rawConfig.default ?? rawConfig),
      content: [{ raw: el.outerHTML, extension: "html" }],
      corePlugins: { preflight: false },
    }),
  ]).process("@tailwind utilities;", { from: undefined });
  const style = document.createElement("style");
  style.setAttribute("data-test-tailwind", "");
  style.textContent = result.css;
  document.head.appendChild(style);
}

function hasVisibleFocus(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  const shadow = cs.boxShadow.trim();
  const shadowShown =
    shadow !== "" && shadow !== "none" && (!shadow.includes("var(") || cs.getPropertyValue("--tw-shadow").trim() !== "");
  const outlineShown = cs.outlineStyle !== "none" && cs.outline !== "" && !/transparent/.test(cs.outline);
  return shadowShown || outlineShown;
}

afterEach(() => {
  cleanup();
  document.head.querySelectorAll("style[data-test-tailwind]").forEach((s) => s.remove());
});

describe("CorpusSearch focus (F-17)", () => {
  it("the search input shows a focus indicator after Tab reaches it", async () => {
    render(<CorpusSearch onOpen={vi.fn()} />);
    const input = screen.getByRole("searchbox", { name: "Search the corpus" });
    await injectTailwindFor(input);
    const user = userEvent.setup();
    for (let i = 0; i < 50 && document.activeElement !== input; i++) await user.tab();
    expect(document.activeElement).toBe(input);
    expect(hasVisibleFocus(input)).toBe(true);
  });
});
