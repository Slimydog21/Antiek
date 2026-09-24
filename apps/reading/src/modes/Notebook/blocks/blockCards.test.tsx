/**
 * blockCards.test.tsx — the notebook's embedded blocks are flat, bounded cards.
 *
 * Design spec §4: cards are FLAT and bounded (surface + 1px border, no
 * shadow), and the sun is spent only on the dock key, the one primary action
 * and the reading mark. Before this, the LaTeX, image and synthesis-section
 * blocks each drew a 2.5px sun edge plus a 3px hard shadow (a sun shadow at
 * night), with a second sun rule inside the LaTeX and image cards.
 *
 * The blocks mount through the real TipTap editor (their node views only
 * render inside one), hydrated from a mocked substrate GET.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";

const { getNotebookContentMock, apiFetchMock } = vi.hoisted(() => ({
  getNotebookContentMock: vi.fn(),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../../lib/api")>()),
  getNotebookContent: getNotebookContentMock,
  apiFetch: apiFetchMock,
}));

import { NotebookEditor } from "../Editor";

afterEach(() => {
  cleanup();
  getNotebookContentMock.mockReset();
  apiFetchMock.mockReset();
  window.localStorage.clear();
});

const SUN = /\bborder-sun\b/;
const RESTING_SHADOW = /(^|\s)(dark:)?shadow-z\d/;

describe("notebook block cards", () => {
  it("draws the LaTeX, image and synthesis blocks flat on a rule border", async () => {
    getNotebookContentMock.mockResolvedValue({
      notebook_id: "nb-cards",
      doc: {
        type: "doc",
        content: [
          { type: "latexBlock", attrs: { source: "E = mc^2" } },
          { type: "imageBlock", attrs: { src: "data:image/gif;base64,R0lGODlhAQABAAAAACw=", alt: "A figure", caption: "Figure 1" } },
          { type: "masterSection", attrs: { synthesis_id: "syn-1", section: "Findings" } },
        ],
      },
    });
    const { container } = render(<NotebookEditor notebookId="nb-cards" />);

    for (const kind of ["latex", "image", "master-section"]) {
      await waitFor(() => expect(container.querySelector(`[data-block="${kind}"]`)).toBeTruthy());
      const block = container.querySelector(`[data-block="${kind}"]`) as HTMLElement;
      const card = block.firstElementChild as HTMLElement;
      expect(card.className, kind).not.toMatch(SUN);
      expect(card.className, kind).not.toMatch(RESTING_SHADOW);
      expect(card.className, kind).toMatch(/\bborder-rule\b/);
      // No sun rule inside the card either (the LaTeX header, the caption).
      for (const inner of block.querySelectorAll<HTMLElement>("[class*='border-sun']")) {
        throw new Error(`${kind}: inner sun rule on <${inner.tagName.toLowerCase()} class="${inner.className}">`);
      }
    }
  });
});
