/**
 * readerCockpitB2.test.tsx — lane A stage B2, the reader findings from the
 * critic's round 2 on A1, red-first.
 *
 *   5  In the cockpit's left pane at 1024x768 and 1280x800 the reader is
 *      narrower than its reader-md container breakpoint, so the TOC column
 *      was hidden with no way to reach it. The TOC stays reachable in the
 *      pane: a Contents toggle (shown only while the container is narrow)
 *      and a keymap row. The reader's own companion column duplicates the
 *      cockpit's right pane, so it is hidden while that pane is present and
 *      kept in docked and phone layouts.
 *   7  Opening the sponsored "house" slot's book is a promotion, not
 *      provenance: it opens as a root tab, never a branch of kind
 *      "reference".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";

const { getBookMock, getFullTextMock, listBooksMock, navigateMock, useInvestigationMock, tierRef } = vi.hoisted(
  () => ({
    getBookMock: vi.fn(),
    getFullTextMock: vi.fn(),
    listBooksMock: vi.fn(),
    navigateMock: vi.fn(),
    useInvestigationMock: vi.fn(),
    tierRef: { current: "lg" as string },
  }),
);

vi.mock("../../api/books", async (orig) => ({
  ...(await orig<typeof import("../../api/books")>()),
  getBook: getBookMock,
  getBookFullText: getFullTextMock,
  listBooks: listBooksMock,
  recordAdImpressions: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
  apiFetch: vi.fn(() => Promise.resolve(new Response("{}", { status: 404 }))),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
}));

vi.mock("../../hooks/useInvestigation", () => ({ useInvestigation: useInvestigationMock }));
vi.mock("../../workspace/useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

// Imported statically, after the mocks above (vi.mock is hoisted): the
// reader's module graph loads while the file is collected. It used to be a
// dynamic import inside renderReader, so the FIRST test paid the whole load
// inside its 5 s timeout and timed out under a loaded batch (R2-L1: 1 of 5
// runs of `readerCockpitB2 cockpit`, "Test timed out in 5000ms" at 5393 ms).
import BookReader from "./index";

function detail(over: Partial<BookDetail> = {}): BookDetail {
  return {
    document_id: "doc-1",
    title: "A Servable Book",
    author: "Auth",
    servability: "public_domain",
    servable_full_text: true,
    page_count: 2,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    pagination_scheme: "pdf_page",
    provenance: null,
    license_basis: null,
    toc: [
      { title: "Chapter 1", page_index: 0, level: 0 },
      { title: "Chapter 2", page_index: 1, level: 0 },
    ],
    ...over,
  };
}

function body(): FullTextResponse {
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.",
    snippet: null,
    title: "A Servable Book",
    author: "Auth",
    reason: "servable",
    tier: null,
    ad_eligible: true,
    canonical_url: null,
    license: null,
  };
}

async function renderReader(entry = "/read/doc-1") {
  const view = render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByTestId("book-reader-root");
  return view;
}

beforeEach(() => {
  window.sessionStorage.clear();
  tierRef.current = "lg";
  getBookMock.mockReset().mockResolvedValue(detail());
  getFullTextMock.mockReset().mockResolvedValue(body());
  listBooksMock.mockReset().mockResolvedValue({
    books: [{ document_id: "doc-2", title: "Meditations", author: "Marcus Aurelius" }],
    count: 1,
  });
  navigateMock.mockReset();
  useInvestigationMock.mockReset().mockReturnValue({
    id: "read-doc-1",
    status: "not_found",
    events: [],
    question: null,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    reconnects: 0,
  });
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
});

afterEach(async () => {
  cleanup();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  const { useTabTrees } = await import("../../workspace/tabTreeStore");
  useTabTrees.getState().resetTabTrees();
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── 5: the TOC stays reachable in the pane ───────────────────────────────

describe("B2-5 the reader's contents in a narrow pane", () => {
  const toc = () => document.querySelector<HTMLElement>("[data-reader-toc]");
  const toggle = () => screen.queryByRole("button", { name: /contents/i });

  it("a Contents toggle exists, driven by the reader's container width (hidden once the column fits)", async () => {
    await renderReader();
    const button = toggle();
    expect(button).not.toBeNull();
    // Container-query driven: the toggle is for the narrow reader only.
    expect(button!.className).toMatch(/reader-md:hidden/);
    expect(button!.getAttribute("aria-expanded")).toBe("false");
    expect(button!.getAttribute("aria-controls")).toBe(toc()!.id);
    // Closed: the TOC is the container-query column (hidden while narrow).
    expect(toc()!.className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(toc()!.className).toMatch(/reader-md:block/);
  });

  it("the toggle opens the TOC in the pane; a jump or Esc closes it again", async () => {
    await renderReader();
    fireEvent.click(toggle()!);
    expect(toggle()!.getAttribute("aria-expanded")).toBe("true");
    expect(toc()!.getAttribute("data-open")).toBe("true");
    expect(toc()!.className).not.toMatch(/(^|\s)hidden(\s|$)/);
    // A jump reads the chapter, so the drawer steps aside.
    fireEvent.click(screen.getByRole("button", { name: /Chapter 2/ }));
    expect(toc()!.getAttribute("data-open")).toBe("false");
    fireEvent.click(toggle()!);
    expect(toc()!.getAttribute("data-open")).toBe("true");
    act(() => {
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(toc()!.getAttribute("data-open")).toBe("false");
  });

  it("a TOC inside a hidden pane leaves Escape for the active layer", async () => {
    const view = await renderReader();
    fireEvent.click(toggle()!);
    expect(toc()!.getAttribute("data-open")).toBe("true");

    view.container.hidden = true;
    let event: KeyboardEvent | undefined;
    act(() => {
      event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
      document.dispatchEvent(event);
    });
    expect(event!.defaultPrevented).toBe(false);
    expect(toc()!.getAttribute("data-open")).toBe("true");
  });

  it("a visible TOC close restores toggle focus", async () => {
    await renderReader();
    const button = toggle()!;
    fireEvent.click(button);
    expect(toc()!.getAttribute("data-open")).toBe("true");

    const outside = document.createElement("button");
    outside.type = "button";
    outside.dataset.a1cFocusSentinel = "reader";
    document.body.append(outside);
    outside.focus();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(toc()!.getAttribute("data-open")).toBe("false");
    expect(document.activeElement).toBe(button);
    outside.remove();
  });

  it("the keymap's contents action toggles it (the key-sheet row)", async () => {
    const { ACTIONS, KEYMAP } = await import("../../components/hotkeys/keymap");
    expect(Object.keys(ACTIONS)).toContain("reader.tocToggle");
    expect(KEYMAP.filter((r) => r.action === ("reader.tocToggle" as never)).map((r) => r.prefixKey)).toEqual([
      "shift+c",
    ]);
    const { createActionHandlers } = await import("../../workspace/shortcuts");
    const handlers = createActionHandlers(vi.fn() as never) as Record<string, (e: KeyboardEvent) => unknown>;
    // No reader on screen: "not mine", the key is left to the page.
    expect(handlers["reader.tocToggle"](new KeyboardEvent("keydown"))).toBe(false);
    await renderReader();
    let handled: unknown;
    act(() => {
      handled = handlers["reader.tocToggle"](new KeyboardEvent("keydown"));
    });
    expect(handled).not.toBe(false);
    expect(toc()!.getAttribute("data-open")).toBe("true");
  });

  it("the reader's own companion column is hidden while the cockpit's right pane is present", async () => {
    await renderReader();
    const slot = document.querySelector<HTMLElement>("[data-reader-companion-slot]");
    expect(slot).not.toBeNull();
    expect(slot!.hidden).toBe(true);
  });

  it("docked and phone layouts keep the reader's companion column", async () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const docked = await renderReader();
    expect(document.querySelector<HTMLElement>("[data-reader-companion-slot]")!.hidden).toBe(false);
    docked.unmount();
    useWorkspace.getState().setLayoutPreset("omarchy-inset");
    tierRef.current = "sm";
    await renderReader();
    expect(document.querySelector<HTMLElement>("[data-reader-companion-slot]")!.hidden).toBe(false);
  });
});

// ─── 7: a promotion is not provenance ─────────────────────────────────────

describe("B2-7 opening the house slot's book opens a root tab, never a provenance branch", () => {
  async function seedReaderTab(mothership: "reading" | "research") {
    const { useTabTrees } = await import("../../workspace/tabTreeStore");
    await useTabTrees.getState().ensureMothership(mothership);
    const seeded = useTabTrees.getState().spawnTab(mothership, null, {
      tab_id: "tReaderDoc1",
      kind: "reader",
      ref: "doc-1",
      mothership,
      activate: true,
    });
    // The reader tab must be there, or "no branch intent" would pass vacuously.
    expect(seeded.ok).toBe(true);
    expect(useTabTrees.getState().trees[mothership]!.active_tab_id).toBe("tReaderDoc1");
  }

  async function clickHouse() {
    const house = await screen.findAllByRole("button", { name: /Next read from the library: Meditations/ });
    fireEvent.click(house[0]);
    await waitFor(() => expect(navigateMock).toHaveBeenCalled());
    // Let a lazily-imported branch helper resolve, if one were used.
    for (let i = 0; i < 4; i++) await act(async () => {});
  }

  it("navigates plainly to the book (no branch intent), so the tree seeds a root", async () => {
    await seedReaderTab("reading");
    await renderReader();
    await clickHouse();
    const calls = navigateMock.mock.calls;
    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toBe("/read/doc-2");
    const state = (calls[0][1] as { state?: Record<string, unknown> } | undefined)?.state;
    expect(state?.tabBranch).toBeUndefined();
  });

  it("keeps the tree it was opened in (?m) without filing a branch", async () => {
    await seedReaderTab("research");
    await renderReader("/read/doc-1?m=research");
    await clickHouse();
    const [to, options] = navigateMock.mock.calls[0] as [string, { state?: Record<string, unknown> } | undefined];
    expect(to).toBe("/read/doc-2?m=research");
    expect(options?.state?.tabBranch).toBeUndefined();
  });
});

// ─── R2-H4: the Thought partner lives in the reader, not over its text ────
//
// Cockpit repair round 2 (critic H4). The bookmark was `fixed bottom-6
// right-6`: fixed to the VIEWPORT, so in a cockpit pane (and at md / phone
// widths, where one pane is the full width) it sat over the reader's text
// and, at 1280, over the right pane. It now sits in the reader's own chrome
// (the header row, in flow, so it can never cover a line of text), and the
// open conversation is positioned against the reader root, inside the pane.
// The real-browser geometry (no intersection with any text line box at
// 1440/1280/1024/900/390) is in the stage's render probe.

describe("R2-H4 the Thought partner bookmark sits in the reader's chrome", () => {
  it("the bookmark is in the reader header, in flow, never fixed to the viewport", async () => {
    await renderReader();
    const bookmark = await screen.findByTestId("talk-to-book-bookmark");
    expect(bookmark.className).not.toMatch(/(^|\s)(fixed|absolute)(\s|$)/);
    const root = screen.getByTestId("book-reader-root");
    const header = bookmark.closest("header");
    expect(header).not.toBeNull();
    expect(root.contains(header)).toBe(true);
    // The header is the reader's title row (it holds the book's h1).
    expect(header!.querySelector("h1")?.textContent).toBe("A Servable Book");
  });

  // Cockpit R3 (critic low): in the scrolling column the header, and the
  // bookmark with it, scrolled out of view a page into the book, so the
  // book-level conversation was unreachable mid-read. The title row now sits
  // above the scroller; only the reading body scrolls.
  it("the title row with the bookmark stays out of the scrolling body", async () => {
    await renderReader();
    const bookmark = await screen.findByTestId("talk-to-book-bookmark");
    const header = bookmark.closest("header")!;
    expect(header.closest(".overflow-y-auto, .overflow-auto, .overflow-y-scroll")).toBeNull();
    const scroller = screen.getByTestId("reader-scroll");
    expect(scroller.className).toMatch(/(^|\s)overflow-y-auto(\s|$)/);
    expect(scroller.contains(header)).toBe(false);
  });

  it("the open conversation is placed against the reader root, inside the pane", async () => {
    await renderReader();
    fireEvent.click(await screen.findByTestId("talk-to-book-bookmark"));
    const panel = await screen.findByTestId("talk-to-book");
    expect(panel.className).not.toMatch(/(^|\s)fixed(\s|$)/);
    expect(panel.className).toMatch(/(^|\s)absolute(\s|$)/);
    // Its containing block is the reader root (relative), not the viewport:
    // no positioned element sits between them.
    const root = screen.getByTestId("book-reader-root");
    expect(root.className).toMatch(/(^|\s)relative(\s|$)/);
    let el = panel.parentElement;
    while (el && el !== root) {
      expect(el.className).not.toMatch(/(^|\s)(relative|absolute|fixed|sticky)(\s|$)/);
      el = el.parentElement;
    }
    expect(el).toBe(root);
  });
});
