/**
 * digDeeper.test.tsx — island SPR-04 proofs (dig deeper from the island).
 *
 *   1. The dig-deeper launch issues exactly ONE startInvestigation with the
 *      island's thread as parent_investigation_id and the anchor quote in
 *      the seed (context/spawn_context); the new chase appears in the
 *      island's family view WITHOUT a reload; the launched state + the
 *      explicit "open the chase →" jump match the workstation chase (no
 *      island-specific fork — no implicit navigation).
 *   2. The no-orphan seam: a seeded ESCALATED distilled question carrying a
 *      reserved_child_investigation_id launches INTO that id (asserted on
 *      the request body); a second dig on the same question targets the
 *      SAME reserved id — never a sibling duplicate.
 *   3. Deepen is the labelled budget alternative: present with a resolvable
 *      LIVE session (one steer call, kind "deepen"), honestly ABSENT when
 *      the session is terminal or unresolvable — asserted by DOM query.
 *   4. Cost copy: both options render their one-line cost semantics; the
 *      capacity-refusal toast path is exercised with a mocked 429
 *      (compute_capacity_exhausted) response.
 *   5. BOTH reader mounts, per the SPR-02 harness.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../../api/books";
import type { BookAnchor, DistillationResponse } from "../../../lib/api";
import type { InvestigationSummary } from "../../../lib/api";
import { useWorkspace } from "../../../workspace/WorkspaceStore";
import { resetReadingStateBus } from "../../../hooks/useReadingState";
import { WindowHostProvider } from "../../../components/windows/windowHostContext";
import { LemonToastViewport } from "../../../components/lemon/LemonToast";

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

vi.mock("../../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
  };
});

vi.mock("../../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (e: unknown) => postTypedEventMock(e),
    searchBlocks: (q: string) => searchBlocksMock(q),
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

vi.mock("../../../hooks/useInvestigation", () => ({
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

function islandAnchor(over: Partial<BookAnchor> = {}): BookAnchor {
  return {
    anchor_id: "a-island",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 0,
      end_scalar: 7,
      quote: "The ope",
      prefix: "",
      suffix: "ning of the book.",
    },
    servable_at_pin: true,
    selection_text_sha256: "s".repeat(64),
    page_index_hint: 0,
    source: "floatmenu_deep_research",
    status: "active",
    exact_valid: true,
    investigation_id: "inv-thread",
    created_at: "2026-09-25T10:00:00Z",
    updated_at: "2026-09-25T10:00:00Z",
    ...over,
  };
}

function summary(over: Partial<InvestigationSummary> = {}): InvestigationSummary {
  return {
    investigation_id: "inv-thread",
    question: "the island's question",
    status: "in_progress",
    started_at: "2026-09-25T10:00:00Z",
    completed_at: null,
    cost_usd_total: 0.42,
    parent_investigation_id: null,
    ...over,
  };
}

const ESCALATED_QUESTION = {
  node_id: "q-esc",
  kind: "question",
  text: "an escalated question?",
  refinement_count: 0,
  escalated: true,
  reserved_child_investigation_id: "inv-reserved-1",
};

function distillation(over: Partial<DistillationResponse> = {}): DistillationResponse {
  return {
    investigation_id: "inv-thread",
    insights: [
      { node_id: "n-0", kind: "insight", text: "finding 0", refinement_count: 0, escalated: false },
    ],
    questions: [ESCALATED_QUESTION],
    ...over,
  } as DistillationResponse;
}

interface Harness {
  investigations: InvestigationSummary[];
  posts: { url: string; body: Record<string, unknown> }[];
  steers: { url: string; body: Record<string, unknown> }[];
}

interface RouteOptions {
  /** The session response for /sessions/inv-thread (null → 404, the
   *  honest unresolvable). */
  session?: Record<string, unknown> | null;
  /** The distill read (terminal threads). */
  distillation?: DistillationResponse;
  /** When set, POST /investigations hard-refuses with this status/body. */
  startRefusal?: { status: number; body: unknown };
}

function route(opts: RouteOptions = {}): Harness {
  const server: Harness = { investigations: [summary()], posts: [], steers: [] };
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/anchors") && method === "GET") {
      return jsonResponse({
        document_id: "doc-1",
        anchors: [{ ...islandAnchor(), anchor: { ...islandAnchor().anchor } }],
        count: 1,
      });
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
    if (url.endsWith("/distill")) {
      return jsonResponse(opts.distillation ?? distillation());
    }
    if (url.includes("/steer") && method === "POST") {
      server.steers.push({ url, body: parsedBody });
      return jsonResponse({ session_id: "inv-thread", investigation_id: "inv-thread", state: "running" });
    }
    if (url.includes("/sessions/")) {
      if (opts.session) return jsonResponse(opts.session);
      return jsonResponse({ detail: "not a session" }, 404);
    }
    if (url.endsWith("/investigations") && method === "POST") {
      server.posts.push({ url, body: parsedBody });
      if (opts.startRefusal) {
        return jsonResponse(opts.startRefusal.body, opts.startRefusal.status);
      }
      const childId = (parsedBody?.investigation_id as string | undefined) ?? "inv-chase-1";
      // The substrate parents the child from the request (the family list
      // carries it on the next read — the island's no-reload refetch).
      if (!server.investigations.some((i) => i.investigation_id === childId)) {
        server.investigations.push(
          summary({
            investigation_id: childId,
            question: (parsedBody?.question as string | undefined) ?? null,
            parent_investigation_id:
              (parsedBody?.parent_investigation_id as string | undefined) ?? null,
            status: "in_progress",
          }),
        );
      }
      return jsonResponse({ investigation_id: childId, status: "in_progress", start_event_id: "ev-1" }, 201);
    }
    if (url.includes("/investigations")) {
      return jsonResponse({
        count: server.investigations.length,
        investigations: server.investigations.map((i) => ({ ...i })),
      });
    }
    return jsonResponse({ text: "reply" });
  });
  return server;
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

async function renderReader(initialEntry = "/read/doc-1") {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("../index");
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
      <LemonToastViewport />
    </MemoryRouter>,
  );
}

async function renderWindowReader(documentId: string) {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("../index");
  return render(
    <MemoryRouter initialEntries={["/research"]}>
      <WindowHostProvider value={true}>
        <BookReader documentId={documentId} />
        <LemonToastViewport />
      </WindowHostProvider>
    </MemoryRouter>,
  );
}

function projection(status: string) {
  return {
    id: "inv-thread",
    status,
    question: "the island's question",
    events: [],
    terminalPayload: null,
    costTotal: 0.42,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
  };
}

async function expandIsland() {
  await screen.findByText("The ope");
  fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
  await screen.findByText("Open research →");
  // The dig-deeper control renders after the expand. Await it so callers
  // never fireEvent.click(null) on a tick where the button is not mounted
  // (CI hit this as "Unable to fire a click event - please provide a DOM
  // element" in the launch proof).
  await waitFor(() =>
    expect(document.querySelector("[data-island-dig-deeper]")).toBeTruthy(),
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  window.localStorage.removeItem("antiek:investigation_tree");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  useInvestigationMock.mockReset().mockReturnValue(projection("in_progress"));
  useWorkspace.getState().reset();
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.removeItem("antiek.island.hidden");
  window.localStorage.removeItem("antiek:investigation_tree");
});

// ── Proof 1: the dig-deeper launch + the family consequence ───────────────

describe("the dig-deeper chase from the island", () => {
  it("launches exactly ONE child with the island's thread as parent and the anchor quote in the seed — the chase joins the family view WITHOUT a reload", async () => {
    const server = route();
    await renderReader();
    await expandIsland();

    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
    const composer = document.querySelector("[data-dig-deeper]")!;
    expect(composer).toBeTruthy();
    // The passage quote is prefilled (the form's shape)…
    expect(composer.querySelector("[data-dig-quote]")!.textContent).toContain("The ope");
    // …and the question textarea is editable before launch.
    fireEvent.change(screen.getByLabelText("What do you want to find out?"), {
      target: { value: "why the opening matters" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));

    // Exactly ONE startInvestigation; the island's thread is the parent; the
    // seed carries the anchor quote + the parent thread's question.
    await waitFor(() => expect(server.posts).toHaveLength(1));
    const body = server.posts[0].body;
    expect(body.parent_investigation_id).toBe("inv-thread");
    expect(body.question).toBe("why the opening matters");
    expect(String(body.context)).toContain("The ope");
    expect(String(body.context)).toContain("the island's question");
    expect(String(body.spawn_context)).toContain("The ope");
    // No reserved id on a bare dig — the substrate mints the fresh child.
    expect("investigation_id" in body).toBe(false);

    // The launched state matches the workstation chase's vocabulary and the
    // navigation stays the EXPLICIT jump (no island-specific fork — the
    // reader never left the book).
    await waitFor(() => expect(document.querySelector("[data-dig-launched]")).toBeTruthy());
    const openChase = document.querySelector("[data-dig-open-chase]")!;
    expect(openChase.getAttribute("href")).toBe("/inv/inv-chase-1");
    expect(screen.getByRole("dialog")).toBeTruthy(); // still in the card

    // The chase appears in the island's family view immediately — no reload.
    await waitFor(() =>
      expect(document.querySelector("[data-island-family]")!.textContent).toContain(
        "why the opening matters",
      ),
    );
  });

  it("window-mounted reader: the same dig-deeper launch works (one implementation, both mounts)", async () => {
    const server = route();
    await renderWindowReader("doc-1");
    await expandIsland();

    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));
    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].body.parent_investigation_id).toBe("inv-thread");
    await waitFor(() => expect(document.querySelector("[data-dig-launched]")).toBeTruthy());
  });
});

// ── Proof 2: the no-orphan reserved-id path ───────────────────────────────

describe("the no-orphan reserved-id path", () => {
  it("digging on an escalated question launches INTO the reserved child id — a second dig targets the SAME id, never a sibling", async () => {
    useInvestigationMock.mockReturnValue(projection("completed"));
    const server = route({ distillation: distillation() });
    await renderReader();
    await expandIsland();
    // The terminal thread's open question renders with its dig affordance.
    const digQ = document.querySelector('[data-island-dig-question="q-esc"]')!;
    expect(digQ).toBeTruthy();

    fireEvent.click(digQ);
    // The composer is prefilled with the QUESTION's text (not the quote).
    expect(
      (screen.getByLabelText("What do you want to find out?") as HTMLTextAreaElement).value,
    ).toBe("an escalated question?");
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));
    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].body.investigation_id).toBe("inv-reserved-1");
    expect(server.posts[0].body.parent_investigation_id).toBe("inv-thread");

    // A second dig on the same question: the reserved id rides again — the
    // launch can only ever land on the same child, never a sibling mint.
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    fireEvent.click(document.querySelector('[data-island-dig-question="q-esc"]')!);
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));
    await waitFor(() => expect(server.posts).toHaveLength(2));
    expect(server.posts[1].body.investigation_id).toBe("inv-reserved-1");
    expect(
      server.investigations.filter((i) => i.parent_investigation_id === "inv-thread"),
    ).toHaveLength(1); // one child for the question, not two
  });
});

// ── Proof 3: deepen — the labelled budget alternative, honestly gated ─────

describe("the deepen alternative", () => {
  const liveSession = {
    session_id: "inv-thread",
    live: true,
    researches: [
      { investigation_id: "inv-thread", sub_question: "the island's question", state: "running" },
    ],
  };

  it("a resolvable LIVE session renders the deepen option — one steer call with kind deepen", async () => {
    const server = route({ session: liveSession });
    await renderReader();
    await expandIsland();
    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);

    const deepen = await waitFor(() => {
      const el = document.querySelector("[data-dig-deepen]");
      expect(el).toBeTruthy();
      return el!;
    });
    fireEvent.click(
      Array.from(deepen.querySelectorAll("button")).find((b) =>
        b.textContent?.includes("More budget on this same thread"),
      )!,
    );
    await waitFor(() => expect(server.steers).toHaveLength(1));
    expect(server.steers[0].url).toContain("/sessions/inv-thread/researches/inv-thread/steer");
    expect(server.steers[0].body.kind).toBe("deepen");
    await screen.findByText(/Budget added/);
  });

  it("a TERMINAL session renders NO deepen option — never a dead button; the chase remains", async () => {
    route({
      session: {
        session_id: "inv-thread",
        live: false,
        researches: [
          { investigation_id: "inv-thread", sub_question: "q", state: "done" },
        ],
      },
    });
    await renderReader();
    await expandIsland();
    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
    await screen.findByRole("button", { name: "Follow this" });
    // Let the session read settle, then assert by DOM query.
    await waitFor(() =>
      expect(apiFetchMock.mock.calls.some(([u]) => String(u).includes("/sessions/"))).toBe(true),
    );
    expect(document.querySelector("[data-dig-deepen]")).toBeNull();
    expect(screen.getByRole("button", { name: "Follow this" })).toBeTruthy();
  });

  it("an UNRESOLVABLE session renders NO deepen option either (the honest absence)", async () => {
    route({ session: null });
    await renderReader();
    await expandIsland();
    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
    await screen.findByRole("button", { name: "Follow this" });
    await waitFor(() =>
      expect(apiFetchMock.mock.calls.some(([u]) => String(u).includes("/sessions/"))).toBe(true),
    );
    expect(document.querySelector("[data-dig-deepen]")).toBeNull();
  });
});

// ── Proof 4: the cost copy + the capacity-refusal path ────────────────────

describe("the cost copy and the capacity path", () => {
  const liveSession = {
    session_id: "inv-thread",
    live: true,
    researches: [
      { investigation_id: "inv-thread", sub_question: "q", state: "running" },
    ],
  };

  it("both options state their one-line cost semantics", async () => {
    route({ session: liveSession });
    await renderReader();
    await expandIsland();
    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);

    expect(document.querySelector("[data-dig-chase-cost]")!.textContent).toBe(
      "Follow this — a new child investigation, its own budget.",
    );
    await waitFor(() =>
      expect(document.querySelector("[data-dig-deepen-cost]")!.textContent).toBe(
        "Deepen — the same investigation, more budget.",
      ),
    );
  });

  it("a capacity-refused launch surfaces the capacity toast through the existing startInvestigation path (no fabricated child)", async () => {
    const server = route({
      startRefusal: {
        status: 429,
        body: {
          detail: {
            code: "compute_capacity_exhausted",
            message: "Agent compute at monthly capacity.",
            used_compute_units: 900,
            monthly_compute_units: 1000,
            enforcement: "hard",
            used_status: "exhausted",
          },
        },
      },
    });
    await renderReader();
    await expandIsland();
    fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));

    // The existing startInvestigation path owns the capacity toast.
    await screen.findByText(/Agent compute at monthly capacity \(900\/1000 ACU\)/);
    // The composer shows the shared honest failure; NO child was minted.
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(server.investigations).toHaveLength(1); // only the parent
    expect(document.querySelector("[data-dig-launched]")).toBeNull();
  });
});
