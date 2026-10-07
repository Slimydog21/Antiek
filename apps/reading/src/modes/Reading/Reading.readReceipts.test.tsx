import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { resetReadingStateBus, setReadingStateOwner } from "../../hooks/useReadingState";
import { setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";

// Only the external API responses are controlled. The reader, dwell hook,
// threshold and typed-event serialization run together. These synthetic
// unit books do not establish signed production reading availability.
const { detail, body, houses } = vi.hoisted(() => ({
  detail: vi.fn<(id: string) => Promise<BookDetail>>(),
  body: vi.fn<(id: string) => Promise<FullTextResponse>>(),
  houses: vi.fn(),
}));
vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  getBook: detail,
  getBookFullText: body,
  listBooks: houses,
}));
import BookReader from "./index";

let clock = 0;
let events: unknown[] = [];

function tree(id: string) {
  return <MemoryRouter><BookReader documentId={id} /></MemoryRouter>;
}

beforeEach(() => {
  clock = 0;
  events = [];
  vi.spyOn(performance, "now").mockImplementation(() => clock);
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  window.sessionStorage.clear();
  setWorkspaceOwner("unit-reader");
  setReadingStateOwner("unit-reader");
  resetReadingStateBus();
  detail.mockImplementation(async (id) => ({
    document_id: id, title: `Unit book ${id}`, author: null,
    servability: "public_domain", servable_full_text: true,
    page_count: 2, cover_uri: null, ip_holder_id: null,
    taken_down: false, pagination_scheme: "pdf_page",
    provenance: null, license_basis: null, toc: [],
  }));
  body.mockImplementation(async (id) => ({
    document_id: id, title: `Unit book ${id}`, author: null,
    servability: "public_domain", servable: true,
    full_text: `## Page 1\n\nUnit ${id} passage 1.\n\n## Page 2\n\nUnit ${id} passage 2.`,
    snippet: null, reason: "servable", tier: null, ad_eligible: false,
    canonical_url: null, license: null,
  }));
  houses.mockResolvedValue({ books: [], count: 0 });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/events/typed") && typeof init?.body === "string") {
      events.push(JSON.parse(init.body));
      return new Response(JSON.stringify({ event_id: "unit-read-event" }), { status: 200 });
    }
    throw new TypeError("controlled ancillary outage");
  }));
});

afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  resetReadingStateBus();
  setReadingStateOwner(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function readTwoPages(id: string) {
  await screen.findByText(`Unit ${id} passage 1.`);
  clock += 20_000;
  fireEvent.click(screen.getByRole("button", { name: "Next →" }));
  await screen.findByText(`Unit ${id} passage 2.`);
  clock += 10_000;
  act(() => window.dispatchEvent(new Event("pagehide")));
  await act(async () => {});
}

it("emits once for each ad-free book, with no duplicate on a same-session revisit", async () => {
  const view = render(tree("a"));
  await readTwoPages("a");
  expect(events).toEqual([
    expect.objectContaining({
      document_id: "a", investigation_id: "read-a",
      payload: expect.objectContaining({ action_type: "source.read", dwell_ms: 30_000, page_count: 2 }),
    }),
  ]);

  view.rerender(tree("b"));
  await readTwoPages("b");
  expect(events).toHaveLength(2);
  expect(events[1]).toEqual(expect.objectContaining({
    document_id: "b", investigation_id: "read-b",
    payload: expect.objectContaining({ action_type: "source.read", dwell_ms: 30_000, page_count: 2 }),
  }));

  view.rerender(tree("a"));
  await screen.findByText("Unit a passage 2.");
  fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
  await readTwoPages("a");
  expect(events).toHaveLength(2);
});

it("refuses source.read on cleanup after the account retires at the reading threshold", async () => {
  const view = render(tree("a"));
  await screen.findByText("Unit a passage 1.");
  clock = 20_000;
  fireEvent.click(screen.getByRole("button", { name: "Next →" }));
  await screen.findByText("Unit a passage 2.");
  clock = 30_000;
  act(() => {
    setWorkspaceOwner(null);
    view.unmount();
  });
  expect(events).toEqual([]);
});
