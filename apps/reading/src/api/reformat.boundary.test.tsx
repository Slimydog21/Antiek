import { Component, type ReactNode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import ReformatReview from "../modes/Reading/ReformatReview";
import ReformatFlow from "../modes/Reading/island/ReformatFlow";
import type { ProvenanceResponse, PassageSnippet } from "./reformat";

class Boundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) { return { error: error.message }; }
  render() { return this.state.error ? <p data-testid="review-crash">{this.state.error}</p> : this.props.children; }
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const provenance = (): ProvenanceResponse => ({
  document_id: "derived", generation: { generation_id: "generation", source_document_id: "source", source_title: "The Source", prompt: "Compress", model: "fixture", params: {}, mostly_generated: false, created_at: "2026-10-01T00:00:00Z" },
  bites: [{ bite_id: "bite", ordinal: 0, contribution_class: "llm_compressed", source_refs: [{ node_id: "opaque:chunk", start_scalar: 5, end_scalar: 19 }], source_page_hints: [null], investigation_id: null, byte_verified: false }],
});
const snippet = (over: Partial<PassageSnippet> = {}): PassageSnippet => ({ servable: true, text: "A servable passage", page_index_hint: null, chunk_id: "opaque:chunk", start_scalar: 5, end_scalar: 19, ...over });
function server(prov: unknown = provenance(), passage: unknown = snippet(), generation: unknown = { generation_id: "generation", derived_document_id: "derived", thread_id: "thread", bite_count: 1, contribution_classes: [], mostly_generated: false, reclassed_verbatim: 0, null_source_share: 0 }) {
  const posts: { path: string; body: Record<string, unknown> }[] = [];
  const urls: URL[] = [];
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), "http://localhost"); urls.push(url);
    const path = url.pathname.replace(/^\/api/, "");
    if (path.endsWith("/provenance")) return json(prov);
    if (path.endsWith("/passage")) return json(passage);
    if (init?.body) posts.push({ path, body: JSON.parse(String(init.body)) });
    if (path.endsWith("/reformats")) return json(generation);
    if (path.includes("/anchors/")) return json({});
    if (path === "/investigations") return json({ investigation_id: "probe" });
    throw new Error(`Unexpected HTTP ${path}`);
  }));
  return { posts, urls };
}
const drain = async () => { await act(async () => { for (let i=0;i<40;i++) await Promise.resolve(); }); };
function mountReview() { return render(<MemoryRouter><Boundary><ReformatReview documentId="derived" /></Boundary></MemoryRouter>); }
async function pull() {
  fireEvent.click(await screen.findByRole("button", { name: "trace" }));
  fireEvent.click(screen.getByRole("button", { name: "pull the core passage" }));
  await waitFor(() => expect(document.querySelector("[data-probe-snippet]")).not.toBeNull());
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("malformed provenance missing required generation fields cannot crash the actual review", async () => {
  server({ document_id: "derived", generation: { generation_id: "generation" }, bites: [] });
  mountReview(); await drain();
  expect(screen.queryByTestId("review-crash")).toBeNull();
});

it("malformed bite page hints cannot crash the expanded trace", async () => {
  const valid = provenance();
  const { source_page_hints: _missing, ...bite } = valid.bites[0];
  server({ ...valid, bites: [bite] });
  mountReview();
  const trace = await screen.findByRole("button", { name: "trace" });
  fireEvent.click(trace); await drain();
  expect(screen.queryByTestId("review-crash")).toBeNull();
});

it("a malformed generation identity cannot offer an undefined derived document", async () => {
  const backend = server(undefined, undefined, { thread_id: "thread" });
  render(<MemoryRouter><ReformatFlow documentId="source" anchorId="anchor" passageQuote="Allowed passage" onClose={() => {}} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("What should the reformat do?"), { target: { value: "A shorter version" } });
  fireEvent.click(screen.getByRole("button", { name: "Reformat" }));
  await drain();
  expect.soft(screen.queryByRole("button", { name: "Open it" })).toBeNull();
  expect.soft(backend.posts.some((post) => post.path.includes("/anchors/"))).toBe(false);
});

it("a false passage gate wins over contradictory nonnull text in DOM, prefill and outbound probe", async () => {
  const secret = "WITHHELD BODY SENTINEL";
  const backend = server(provenance(), snippet({ servable: false, text: secret }));
  mountReview(); await pull();
  const input = screen.getByLabelText("Probe deeper from this bite") as HTMLInputElement;
  expect.soft(document.querySelector("[data-probe-snippet]")?.textContent).not.toContain(secret);
  expect.soft(input.value).not.toContain(secret);
  fireEvent.click(screen.getByRole("button", { name: "probe deeper" }));
  await waitFor(() => expect(backend.posts.some((post) => post.path === "/investigations")).toBe(true));
  const sent = backend.posts.find((post) => post.path === "/investigations")!;
  expect.soft(JSON.stringify(sent.body)).not.toContain(secret);
});

it("an unknown withheld snippet page is never labeled as page one", async () => {
  server(provenance(), snippet({ servable: false, text: null, page_index_hint: null }));
  mountReview(); await pull();
  expect(document.querySelector("[data-probe-snippet]")?.textContent).not.toContain("page 1");
});

it("preserves the declared opaque chunk and scalar coordinates in an authorized probe", async () => {
  const backend = server(); mountReview(); await pull();
  fireEvent.click(screen.getByRole("button", { name: "probe deeper" }));
  await waitFor(() => expect(backend.posts.some((post) => post.path === "/investigations")).toBe(true));
  const request = backend.urls.find((url) => url.pathname.endsWith("/passage"))!;
  expect(request.searchParams.get("chunk_id")).toBe("opaque:chunk");
  expect(request.searchParams.get("start_scalar")).toBe("5");
  expect(request.searchParams.get("end_scalar")).toBe("19");
  const sent = backend.posts.find((post) => post.path === "/investigations")!;
  expect(sent.body.context).toBe("Core passages: source opaque:chunk [5:19]");
  expect(sent.body.spawn_context).toBe("A servable passage");
});
