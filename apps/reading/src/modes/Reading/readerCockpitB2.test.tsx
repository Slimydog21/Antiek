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
  const { default: BookReader } = await import("./index");
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
