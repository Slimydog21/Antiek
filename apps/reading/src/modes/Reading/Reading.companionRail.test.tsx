/**
 * Reading.companionRail.test.tsx — the document companion in the rail
 * (companions SPR-02), BOTH reader mounts:
 *
 *   - the companion section renders the generated content with its
 *     provenance markers (data-evidence-id per claim/process) in the
 *     standalone route AND the window-mounted reader — one implementation,
 *     the unit-4 harness;
 *   - a withheld document's section renders METADATA LINES ONLY (the DOM is
 *     grepped for the withheld sentence — absent; the server never sends it);
 *   - the rail stays READ-ONLY (no edit affordance in the companion section
 *     — asserted by DOM query);
 *   - NO raw-HTML injection: the generated narrative renders as structured
 *     content only (the rail path greps clean of dangerouslySetInnerHTML,
 *     asserted at the source level);
 *   - the inspect toggle renders the honest evidence-base dump;
 *   - LAZY (the lane-B hotfix's client half): the section is a collapsed
 *     disclosure and NOTHING is requested on reader open — the GET used to
 *     rebuild under the single writer lock on every open. First open GETs;
 *     `not_built` POSTs /refresh exactly once; `withheld` and a 404 read the
 *     same unavailable line; a 503 from refresh names only whether a last
 *     build exists; no status number, server code or error_type renders.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import { resetReadingStateBus } from "../../hooks/useReadingState";

const WITHHELD_SENTENCE = "the withheld sentence that must never render";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  useInvestigationMock,
  postTypedEventMock,
  searchBlocksMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  useInvestigationMock: vi.fn(),
  postTypedEventMock: vi.fn((_e: unknown) => Promise.resolve({ event_id: "e" })),
  searchBlocksMock: vi.fn((_q: string) => Promise.resolve({ count: 0, hits: [] })),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
  };
});

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (e: unknown) => postTypedEventMock(e),
    searchBlocks: (q: string) => searchBlocksMock(q),
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));

const BODY =
  "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.";

function makeDetail(over: Partial<BookDetail> = {}): BookDetail {
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
    toc: [{ title: "Chapter 1", page_index: 0, level: 0 }],
    ...over,
  };
}

function makeBody(over: Partial<FullTextResponse> = {}): FullTextResponse {
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: BODY,
    snippet: null,
    title: "A Servable Book",
    author: "Auth",
    reason: "servable",
    tier: null,
    ad_eligible: true,
    canonical_url: null,
    license: null,
    ...over,
  };
}

function companionPayload(servable: boolean) {
  return {
    document_id: "doc-1",
    exists: true,
    title: "A Servable Book",
    servable,
    rebuilt_at: "2026-09-25T12:00:00Z",
    claims: [
      {
        evidence_id: "ev-claim-1",
        kind: "insight",
        node_ref: "node:n-1",
        text: servable ? "the companion's first finding" : null,
      },
      {
        evidence_id: "ev-claim-2",
        kind: "question",
        node_ref: "node:n-2",
        text: servable ? "the companion's open question" : null,
      },
    ],
    anchors: [
      {
        evidence_id: "ev-anchor-1",
        anchor_ref: "anchor:ahl-1",
        status: "active",
        page_index_hint: 0,
      },
    ],
    processes: [
      {
        evidence_id: "ev-proc-1",
        detail: "thread",
        label: "a research thread on a passage",
        status_line: "working…",
      },
    ],
  };
}

function evidenceRows() {
  return {
    rows: [
      { evidence_id: "ev-claim-1", kind: "claim", refs: ["node:n-1", "doc:doc-1"], tombstone: false, rebuilt_at: "2026-09-25T12:00:00Z" },
      { evidence_id: "ev-proc-1", kind: "process", refs: ["investigation:inv-1", "doc:doc-1"], tombstone: false, rebuilt_at: "2026-09-25T12:00:00Z" },
    ],
    count: 2,
  };
}

type CompanionHandler = (url: string) => Response | Promise<Response>;

function builtPayload(over: Record<string, unknown> = {}) {
  return { ...companionPayload(true), state: "built", ...over };
}

/** Lane B's pinned 503 body — the error_type is a server detail that must never render. */
function rebuildFailed(hasLastBuild: boolean) {
  return jsonResponse(
    { detail: "companion_rebuild_failed", error_type: "DuckDBLockTimeout", has_last_build: hasLastBuild },
    503,
  );
}

function methodOf(init: unknown): string {
  return ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase();
}

function route(
  servable: boolean,
  companion: { get?: CompanionHandler; post?: CompanionHandler } = {},
) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: unknown) => {
    const url = String(input);
    if (url.includes("/companion")) {
      if (methodOf(init) === "POST") {
        return companion.post
          ? companion.post(url)
          : jsonResponse({ ...companionPayload(servable), state: "built" });
      }
      // Default GET: the PRE-hotfix payload (no `state`) — the legacy server.
      return companion.get ? companion.get(url) : jsonResponse(companionPayload(servable));
    }
    if (url.endsWith("/evidence")) {
      return jsonResponse(evidenceRows());
    }
    if (url.endsWith("/anchors")) {
      return jsonResponse({ document_id: "doc-1", anchors: [], count: 0 });
    }
    if (url.endsWith("/anchor-map")) {
      return jsonResponse({
        document_id: "doc-1",
        chunks: [
          { chunk_id: "c-1", section_path: "Page 1", body_start: 11, body_end: 33, node_text_sha256: "h".repeat(64) },
        ],
        complete: true,
      });
    }
    if (url.endsWith("/reading-state")) {
      return jsonResponse({ detail: "reading_state_not_found" }, 404);
    }
    if (url.includes("/sessions/")) {
      return jsonResponse({ detail: "not a session" }, 404);
    }
    if (url.includes("/investigations")) {
      return jsonResponse({ count: 0, investigations: [] });
    }
    return jsonResponse({ text: "reply" });
  });
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function companionCalls(method: "GET" | "POST") {
  return apiFetchMock.mock.calls.filter(
    ([input, init]) => String(input).includes("/companion") && methodOf(init) === method,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Let every mount-time effect and microtask settle before counting calls. */
async function settle() {
  await new Promise((r) => setTimeout(r, 30));
}

async function companionSection(): Promise<HTMLElement> {
  return waitFor(() => {
    const el = document.querySelector<HTMLElement>("[data-companion-section]");
    expect(el).toBeTruthy();
    return el!;
  });
}

function companionHeader(section: HTMLElement): HTMLElement {
  return within(section).getByRole("button", { name: "The companion so far" });
}

function companionRegion(section: HTMLElement): HTMLElement {
  const id = companionHeader(section).getAttribute("aria-controls");
  expect(id).toBeTruthy();
  const region = document.getElementById(id!);
  expect(region).toBeTruthy();
  return region!;
}

async function openCompanion(): Promise<HTMLElement> {
  const section = await companionSection();
  fireEvent.click(companionHeader(section));
  return section;
}

async function renderRail(documentId = "doc-1") {
  const { default: ReadingCompanion } = await import("./ReadingCompanion");
  const view = render(
    <MemoryRouter>
      <ReadingCompanion documentId={documentId} readingThreadId={`read-${documentId}`} />
    </MemoryRouter>,
  );
  const rerenderRail = (next: string) =>
    view.rerender(
      <MemoryRouter>
        <ReadingCompanion documentId={next} readingThreadId={`read-${next}`} />
      </MemoryRouter>,
    );
  return { ...view, rerenderRail };
}

async function renderReader() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/read/doc-1"]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function renderWindowReader() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/research"]}>
      <WindowHostProvider value={true}>
        <BookReader documentId="doc-1" />
      </WindowHostProvider>
    </MemoryRouter>,
  );
}

// Pay the reader's cold module graph once, outside any single test's budget
// (under host load the first test otherwise spends most of its 5s importing).
beforeAll(async () => {
  await import("./index");
  await import("./ReadingCompanion");
}, 60_000);

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
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
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the companion rail section in BOTH reader mounts", () => {
  it("standalone route: generated content with provenance markers + the inspect dump", async () => {
    route(true);
    await renderReader();
    await screen.findByText("The opening of the book.");

    const section = await openCompanion();
    // Generated content WITH provenance markers (data attrs, never labels).
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(section.textContent).toContain("a research thread on a passage");
    expect(section.querySelectorAll("[data-evidence-id]").length).toBeGreaterThanOrEqual(3);
    // Read-only: no edit affordance anywhere in the section.
    expect(section.querySelector("textarea, input, [contenteditable]")).toBeNull();

    // The inspect dump: the evidence base's only user surface.
    fireEvent.click(within(section).getByRole("button", { name: "inspect evidence base" }));
    const dump = await waitFor(() => {
      const el = document.querySelector("[data-companion-inspect]");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(dump.textContent).toContain("claim");
    expect(dump.textContent).toContain("process");
    expect(dump.textContent).toContain("ev-claim-1");
  });

  it("window-mounted reader: the same section renders (one implementation, both mounts)", async () => {
    route(true);
    await renderWindowReader();
    await screen.findByText("The opening of the book.");
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's open question"));
  });

  it("a withheld document's section renders metadata lines only — the withheld sentence never enters the DOM", async () => {
    route(false);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("grounded in a withheld source"));
    expect(section.textContent).toContain("withheld");
    expect(section.textContent).toContain("grounded in a withheld source");
    // The grep enforcement at the DOM level: no claim text, and the withheld
    // fixture sentence is nowhere in the document.
    expect(section.textContent).not.toContain("the companion's first finding");
    expect(document.body.textContent).not.toContain(WITHHELD_SENTENCE);
  });

  it("no raw-HTML injection anywhere in the rail path (source-level grep)", () => {
    // The sanctioned-rendering discipline, asserted at the source: the rail
    // and its client render structured content, never generated HTML.
    const fs = require("node:fs") as typeof import("node:fs");
    const path = require("node:path") as typeof import("node:path");
    const rail = fs.readFileSync(
      path.join(__dirname, "ReadingCompanion.tsx"),
      "utf-8",
    );
    const client = fs.readFileSync(
      path.join(__dirname, "../../api/companions.ts"),
      "utf-8",
    );
    expect(rail).not.toContain("dangerouslySetInnerHTML");
    expect(client).not.toContain("dangerouslySetInnerHTML");
    expect(client).not.toContain("innerHTML");
  });
});

const UNAVAILABLE = "The companion isn't available for this document.";
const LOAD_FAILED = "Couldn't load the companion.";
const BUILD_FAILED = "Couldn't build the companion yet.";
const REBUILD_FAILED = "Couldn't rebuild the companion. The last version is shown.";
const SERVER_DETAIL = /\b503\b|\b404\b|companion_rebuild_failed|book_not_found|DuckDBLockTimeout|error_type/;

describe("the companion section is lazy — nothing requested on reader open", () => {
  it("standalone reader open: zero companion calls, a collapsed disclosure", async () => {
    route(true);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const section = await companionSection();
    await settle();
    expect(companionCalls("GET")).toHaveLength(0);
    expect(companionCalls("POST")).toHaveLength(0);
    const header = companionHeader(section);
    expect(header.getAttribute("aria-expanded")).toBe("false");
    // aria-controls points at a real element even while collapsed.
    expect(companionRegion(section)).toBeTruthy();
    expect(section.textContent).not.toContain("the companion's first finding");
  });

  it("window-mounted reader open: zero companion calls", async () => {
    route(true);
    await renderWindowReader();
    await screen.findByText("The opening of the book.");
    await companionSection();
    await settle();
    expect(companionCalls("GET")).toHaveLength(0);
    expect(companionCalls("POST")).toHaveLength(0);
  });
});

describe("the companion section's states (lane B's pinned wire shape)", () => {
  it("open → built: one GET, today's rendering, no POST", async () => {
    route(true, { get: () => jsonResponse(builtPayload()) });
    await renderRail();
    const section = await openCompanion();
    expect(companionHeader(section).getAttribute("aria-expanded")).toBe("true");
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(section.textContent).toContain("a research thread on a passage");
    expect(section.textContent).toContain("rebuilt 2026-09-25");
    expect(companionCalls("GET")).toHaveLength(1);
    expect(String(companionCalls("GET")[0][0])).toContain("/documents/doc-1/companion?format=json");
    expect(companionCalls("POST")).toHaveLength(0);
  });

  it("a legacy payload with no state (pre-hotfix server) renders as built", async () => {
    route(true); // default GET omits `state`
    await renderRail();
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(within(section).getByRole("button", { name: "Refresh" })).toBeTruthy();
    expect(companionCalls("POST")).toHaveLength(0);
  });

  it("open → not_built → 'Building the companion…' → exactly one POST → built", async () => {
    const post = deferred<Response>();
    route(true, {
      get: () => jsonResponse({ document_id: "doc-1", state: "not_built" }),
      post: () => post.promise,
    });
    await renderRail();
    const section = await openCompanion();
    const building = await within(section).findByText("Building the companion…");
    expect(building.closest("[aria-live]")?.getAttribute("aria-live")).toBe("polite");
    await waitFor(() => expect(companionCalls("POST")).toHaveLength(1));
    expect(String(companionCalls("POST")[0][0])).toContain("/documents/doc-1/companion/refresh");
    post.resolve(jsonResponse(builtPayload()));
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(section.textContent).not.toContain("Building the companion…");
    await settle();
    expect(companionCalls("POST")).toHaveLength(1);
    expect(companionCalls("GET")).toHaveLength(1);
  });

  it("withheld: the unavailable line, never a POST, never a retry", async () => {
    route(true, {
      get: () => jsonResponse({ document_id: "doc-1", state: "withheld", reason: "taken_down" }),
    });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(UNAVAILABLE);
    await settle();
    expect(companionCalls("POST")).toHaveLength(0);
    expect(companionCalls("GET")).toHaveLength(1);
    expect(within(section).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "Refresh" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "inspect evidence base" })).toBeNull();
  });

  it.each([
    ["withheld", () => jsonResponse({ document_id: "doc-1", state: "withheld", reason: "not_servable" })],
    ["404", () => jsonResponse({ detail: "book_not_found" }, 404)],
  ])("%s → the region reads exactly the unavailable line (no existence disclosure)", async (_label, get) => {
    route(true, { get });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(UNAVAILABLE);
    expect(companionRegion(section).textContent?.trim()).toBe(UNAVAILABLE);
    expect(section.textContent).not.toMatch(SERVER_DETAIL);
    expect(companionCalls("POST")).toHaveLength(0);
  });

  it("refresh 503 with has_last_build=true while a payload is shown: keeps it, offers Retry, no server detail", async () => {
    route(true, { get: () => jsonResponse(builtPayload()), post: () => rebuildFailed(true) });
    await renderRail();
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    fireEvent.click(within(section).getByRole("button", { name: "Refresh" }));
    await within(section).findByText(REBUILD_FAILED);
    expect(section.textContent).toContain("the companion's first finding");
    expect(within(section).getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(section.textContent).not.toMatch(SERVER_DETAIL);
  });

  it("refresh 503 with has_last_build=false: couldn't build yet, Retry offered, no automatic retry", async () => {
    route(true, {
      get: () => jsonResponse({ document_id: "doc-1", state: "not_built" }),
      post: () => rebuildFailed(false),
    });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(BUILD_FAILED);
    expect(within(section).getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(section.textContent).not.toContain("the companion's first finding");
    expect(section.textContent).not.toMatch(SERVER_DETAIL);
    await settle();
    expect(companionCalls("POST")).toHaveLength(1);
  });

  it("refresh 503 with has_last_build=true and nothing in hand: reads the last build once so 'shown' is true", async () => {
    let gets = 0;
    route(true, {
      get: () => {
        gets += 1;
        return gets === 1
          ? jsonResponse({ document_id: "doc-1", state: "not_built" })
          : jsonResponse(builtPayload());
      },
      post: () => rebuildFailed(true),
    });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(REBUILD_FAILED);
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(section.textContent).not.toMatch(SERVER_DETAIL);
    await settle();
    expect(companionCalls("POST")).toHaveLength(1);
    expect(companionCalls("GET")).toHaveLength(2);
  });

  it("a network failure reads 'Couldn't load the companion.' and Retry re-reads", async () => {
    let gets = 0;
    route(true, {
      get: () => {
        gets += 1;
        if (gets === 1) throw new TypeError("Failed to fetch");
        return jsonResponse(builtPayload());
      },
    });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(LOAD_FAILED);
    expect(section.textContent).not.toContain("Failed to fetch");
    fireEvent.click(within(section).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(section.textContent).not.toContain(LOAD_FAILED);
    expect(companionCalls("GET")).toHaveLength(2);
    expect(companionCalls("POST")).toHaveLength(0);
  });

  it("Retry after a failed first build POSTs once more, then renders", async () => {
    let posts = 0;
    route(true, {
      get: () => jsonResponse({ document_id: "doc-1", state: "not_built" }),
      post: () => {
        posts += 1;
        return posts === 1 ? rebuildFailed(false) : jsonResponse(builtPayload());
      },
    });
    await renderRail();
    const section = await openCompanion();
    await within(section).findByText(BUILD_FAILED);
    fireEvent.click(within(section).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    expect(companionCalls("POST")).toHaveLength(2);
    expect(companionCalls("GET")).toHaveLength(1);
  });

  it("Refresh is disabled with a visible reason while a request is in flight", async () => {
    const post = deferred<Response>();
    route(true, { get: () => jsonResponse(builtPayload()), post: () => post.promise });
    await renderRail();
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    fireEvent.click(within(section).getByRole("button", { name: "Refresh" }));
    await within(section).findByText("Rebuilding the companion…");
    const refresh = within(section).getByRole("button", { name: "Refresh" }) as HTMLButtonElement;
    expect(refresh.disabled).toBe(true);
    fireEvent.click(refresh);
    expect(companionCalls("POST")).toHaveLength(1);
    // The companion in hand stays readable while it rebuilds.
    expect(section.textContent).toContain("the companion's first finding");
    post.resolve(jsonResponse(builtPayload({ rebuilt_at: "2026-09-27T08:00:00Z" })));
    await waitFor(() => expect(section.textContent).toContain("rebuilt 2026-09-27"));
    expect((within(section).getByRole("button", { name: "Refresh" }) as HTMLButtonElement).disabled).toBe(false);
    expect(section.textContent).not.toContain("Rebuilding the companion…");
  });

  it("collapsing and re-opening does not refetch", async () => {
    route(true, { get: () => jsonResponse(builtPayload()) });
    await renderRail();
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    fireEvent.click(companionHeader(section));
    expect(companionHeader(section).getAttribute("aria-expanded")).toBe("false");
    expect(companionRegion(section).hidden).toBe(true);
    fireEvent.click(companionHeader(section));
    expect(companionHeader(section).getAttribute("aria-expanded")).toBe("true");
    expect(companionRegion(section).hidden).toBe(false);
    expect(section.textContent).toContain("the companion's first finding");
    await settle();
    expect(companionCalls("GET")).toHaveLength(1);
  });

  it("the inspect toggle appears only once the section is open and built", async () => {
    route(true, { get: () => jsonResponse(builtPayload()) });
    await renderRail();
    const section = await companionSection();
    expect(within(section).queryByRole("button", { name: "inspect evidence base" })).toBeNull();
    fireEvent.click(companionHeader(section));
    const inspect = await within(section).findByRole("button", { name: "inspect evidence base" });
    fireEvent.click(inspect);
    await waitFor(() => expect(section.querySelector("[data-companion-inspect]")).toBeTruthy());
  });

  it("a documentId change resets: collapsed again, nothing fetched until opened, then the new document", async () => {
    route(true, {
      get: (url) =>
        jsonResponse(
          url.includes("/documents/doc-2/")
            ? builtPayload({
                document_id: "doc-2",
                claims: [{ evidence_id: "ev-d2", kind: "insight", node_ref: "node:d2", text: "the second book's finding" }],
              })
            : builtPayload(),
        ),
    });
    const { rerenderRail } = await renderRail("doc-1");
    let section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("the companion's first finding"));
    rerenderRail("doc-2");
    section = await companionSection();
    await waitFor(() => expect(companionHeader(section).getAttribute("aria-expanded")).toBe("false"));
    expect(section.textContent).not.toContain("the companion's first finding");
    await settle();
    expect(companionCalls("GET").filter(([u]) => String(u).includes("/documents/doc-2/"))).toHaveLength(0);
    fireEvent.click(companionHeader(section));
    await waitFor(() => expect(section.textContent).toContain("the second book's finding"));
    expect(companionCalls("GET").filter(([u]) => String(u).includes("/documents/doc-2/"))).toHaveLength(1);
  });
});

describe("claim labels follow the payload's real kind", () => {
  it("insight → Finding, question → Open question, claim → Claim, evidence → Evidence, unknown → no label", async () => {
    const claims = [
      { evidence_id: "ev-insight", kind: "insight", node_ref: "node:1", text: "an insight row" },
      { evidence_id: "ev-question", kind: "question", node_ref: "node:2", text: "a question row" },
      { evidence_id: "ev-claim", kind: "claim", node_ref: "node:3", text: "a claim row" },
      { evidence_id: "ev-evidence", kind: "evidence", node_ref: "node:4", text: "an evidence row" },
      { evidence_id: "ev-unknown", kind: "mystery_kind", node_ref: "node:5", text: "an unknown row" },
    ];
    route(true, { get: () => jsonResponse(builtPayload({ claims })) });
    await renderRail();
    const section = await openCompanion();
    await waitFor(() => expect(section.textContent).toContain("an unknown row"));
    const row = (id: string) => section.querySelector(`[data-evidence-id="${id}"]`)!.textContent ?? "";
    expect(row("ev-insight")).toContain("Finding");
    expect(row("ev-question")).toContain("Open question");
    expect(row("ev-claim")).toContain("Claim");
    expect(row("ev-claim")).not.toContain("Open question");
    expect(row("ev-evidence")).toContain("Evidence");
    expect(row("ev-evidence")).not.toContain("Open question");
    expect(row("ev-unknown").trim()).toBe("an unknown row");
  });
});

describe("no status number, server code or error_type can render (source-level)", () => {
  it("the companion section's source never reads a status, message, body or error_type", () => {
    const fs = require("node:fs") as typeof import("node:fs");
    const path = require("node:path") as typeof import("node:path");
    const rail = fs.readFileSync(path.join(__dirname, "ReadingCompanion.tsx"), "utf-8");
    // From the section's view model to EOF: the state union, its copy, the
    // component and its label helper.
    const start = rail.indexOf("type CompanionView =");
    expect(start).toBeGreaterThan(-1);
    const section = rail.slice(start);
    expect(section).not.toMatch(/error_type|errorType|companion_rebuild_failed|book_not_found/);
    expect(section).not.toMatch(/\.status\b|\.message\b|\.body\b|\bHTTP\b/);
    expect(section).not.toMatch(/\b(404|500|503)\b/);
  });
});
