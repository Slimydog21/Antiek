/**
 * writeHomePane.test.tsx — lane A stage B3, defect 6.
 *
 * Write mode lives in a cockpit pane, so it answers to the PANE's width,
 * never the viewport's (the reader's container-reader fix, made for Write):
 * at a 1024 px viewport the inset left pane is ~668 px, and the viewport
 * `lg:flex` put a 320 px block repository beside the piece and crushed the
 * piece header's title to 0 px (render probe, 1024x768 and 390x844).
 *
 *   - the open piece is an inline-size container (`container-write`);
 *   - the header stacks until the container is wide enough for one row;
 *   - the block repository column shows at the container's `write-lg:` width
 *     and otherwise opens from a Blocks toggle as a drawer over the piece.
 * The Tailwind side (the variants compile to container queries) is guarded
 * in src/design/containerVariants.test.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { getDeliverableMock } = vi.hoisted(() => ({ getDeliverableMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getDeliverable: getDeliverableMock,
  listDeliverables: vi.fn(async () => ({ count: 0, deliverables: [] })),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
}));
vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: vi.fn(async () => []),
  searchRepository: vi.fn(async () => []),
  listFolders: vi.fn(async () => ({ folders: [] })),
}));

import WriteHome from "./WriteHome";

const DETAIL = {
  deliverable_id: "d-1",
  title: "Why the finches matter",
  deliverable_kind: "general_essay",
  status: "draft",
  investigation_root_id: "inv-1",
  sections: [
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "The question", prose_text: "p", prose_provenance: null, block_count: 0 },
  ],
};

beforeEach(() => {
  getDeliverableMock.mockReset().mockResolvedValue(DETAIL);
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

async function mountPiece() {
  render(
    <MemoryRouter initialEntries={["/write/d-1"]}>
      <Routes>
        <Route path="/write/:deliverableId" element={<WriteHome />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Why the finches matter" });
}

const tokens = (el: Element) => el.className.split(/\s+/);

describe("B3-6 Write answers to its pane's width", () => {
  it("the open piece is an inline-size container", async () => {
    await mountPiece();
    const h1 = screen.getByRole("heading", { name: "Why the finches matter" });
    const root = h1.closest(".container-write");
    expect(root).toBeTruthy();
  });

  it("no viewport breakpoint decides the piece's columns", async () => {
    await mountPiece();
    const root = screen.getByRole("heading", { name: "Why the finches matter" }).closest(".container-write")!;
    const viewportBreakpoint = /^(sm|md|lg|xl|2xl):/;
    const offenders = Array.from(root.querySelectorAll<HTMLElement>("header, header *, aside, [data-blocks-toggle]"))
      .flatMap((el) => tokens(el).filter((t) => viewportBreakpoint.test(t)));
    expect(offenders).toEqual([]);
  });

  it("the header stacks until the container is wide enough for one row, so the title is never crushed", async () => {
    await mountPiece();
    const header = screen.getByRole("heading", { name: "Why the finches matter" }).closest("header")!;
    expect(tokens(header)).toContain("flex-col");
    expect(tokens(header)).toContain("write-md:flex-row");
    // The actions column may shrink and wrap in the narrow form; only the
    // one-row form pins it.
    const actions = header.querySelector<HTMLElement>("[data-piece-actions]")!;
    expect(actions).toBeTruthy();
    expect(tokens(actions)).not.toContain("shrink-0");
    expect(tokens(actions)).toContain("flex-wrap");
  });

  it("the block repository is a column at write-lg and a drawer from a Blocks toggle below it", async () => {
    await mountPiece();
    const aside = document.querySelector<HTMLElement>("[data-block-repository-aside]")!;
    expect(aside).toBeTruthy();
    expect(tokens(aside)).toContain("write-lg:flex");
    expect(tokens(aside)).not.toContain("lg:flex");
    const toggle = document.querySelector<HTMLElement>("[data-blocks-toggle]")!;
    expect(toggle).toBeTruthy();
    expect(tokens(toggle)).toContain("write-lg:hidden");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    act(() => {
      fireEvent.click(toggle);
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(aside.getAttribute("data-open")).toBe("true");
    // Esc closes the drawer (it is a transient overlay: one Esc, one handler).
    act(() => {
      fireEvent.keyDown(aside, { key: "Escape" });
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});
