import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

import CanonicalTwinReader from "./CanonicalTwinReader";

const twin = {
  document_id: "twin-doc",
  source_asset_id: "source-a",
  source_hash: "revision-a",
  title: "Notes on swept-wing flight",
  html_fragment: "<h2>Why sweep mattered</h2><p>Compressibility changed the design space.</p>",
  authority: "advisory",
  authority_label: "AI-generated advisory notes; verify against sources",
  shareable: false,
  reviewed_promotions_href:
    "/reader/sources/source-a/reviewed-promotions?source_hash=revision-a",
};

const item = {
  candidate_id: "candidate-a",
  node_id: "node-a",
  review_id: "review-a",
  kind: "insight",
  text: "Wing sweep delayed the onset of compressibility effects.",
  evidence_count: 1,
  href: "/reader/promotions/candidate-a",
};

const collection = {
  source_asset_id: "source-a",
  source_hash: "revision-a",
  items: [item],
  complete: true,
  authority: "current_owner_reviewed_source_promotions_v1",
};

const detail = {
  node: {
    node_id: "node-a",
    candidate_id: "candidate-a",
    review_id: "review-a",
    kind: "insight",
    text: item.text,
    owner_id: "acct",
    status: "current",
    authority: "owner_reviewed_evidence_bound_graph_node_v1",
  },
  citations: [
    {
      citation_id: "citation-twin",
      node_id: "node-a",
      owner_id: "acct",
      candidate_id: "candidate-a",
      candidate_digest: "a".repeat(64),
      review_id: "review-a",
      ordinal: 0,
      citation_kind: "canonical_twin",
      document_id: "twin-doc",
      chunk_id: "twin-chunk",
      range_start: null,
      range_end: null,
      text_sha256: "b".repeat(64),
      chunk_sha256: "b".repeat(64),
      document_sha256: null,
      source_envelope_sha256: null,
      content_class: null,
      schema: "antiek.canonical-twin-node-citation.v1",
    },
    {
      citation_id: "citation-source",
      node_id: "node-a",
      owner_id: "acct",
      candidate_id: "candidate-a",
      candidate_digest: "a".repeat(64),
      review_id: "review-a",
      ordinal: 1,
      citation_kind: "evidence",
      document_id: "source-doc",
      chunk_id: "source-chunk",
      range_start: 24,
      range_end: 92,
      text_sha256: "d".repeat(64),
      chunk_sha256: "e".repeat(64),
      document_sha256: "f".repeat(64),
      source_envelope_sha256: "1".repeat(64),
      content_class: "personal_reading",
      schema: "antiek.canonical-twin-node-citation.v1",
    },
  ],
  status: "current",
  authority: "owner_reviewed_evidence_bound_node_citations_v1",
};

function response(value: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function route(path = "/read/twin/source-a?revision=revision-a") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/read/twin/:sourceAssetId" element={<CanonicalTwinReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CanonicalTwinReader", () => {
  it("renders exact advisory HTML and current reviewed notes", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection));
    route();
    expect(await screen.findByRole("heading", { name: twin.title })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Why sweep mattered" })).toBeTruthy();
    expect(screen.getByText(item.text)).toBeTruthy();
    expect(screen.getByText("Private advisory")).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("loads ordered citation proof only when requested", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() => response(detail));
    route();
    const toggle = await screen.findByRole("button", { name: "1 evidence source" });
    expect(screen.queryByText("Canonical note")).toBeNull();
    fireEvent.click(toggle);
    expect(await screen.findByText("Canonical note")).toBeTruthy();
    expect(screen.getByText("Source evidence")).toBeTruthy();
    expect(screen.getByText("Characters 24–92")).toBeTruthy();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("withholds detail when the current identity no longer matches", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() =>
        response({ ...detail, node: { ...detail.node, review_id: "substituted" } }),
      );
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
    expect(screen.queryByText("Source evidence")).toBeNull();
  });

  it("withholds reordered or cross-candidate citation proof", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() =>
        response({
          ...detail,
          citations: detail.citations.map((citation, index) => ({
            ...citation,
            ordinal: index === 0 ? 1 : 0,
          })),
        }),
      );
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
    expect(screen.queryByText("Canonical note")).toBeNull();
  });

  it("withholds a canonical citation bound to another twin document", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() =>
        response({
          ...detail,
          citations: detail.citations.map((citation, index) =>
            index === 0 ? { ...citation, document_id: "another-twin" } : citation,
          ),
        }),
      );
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
  });

  it("withholds duplicated citation identities", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() =>
        response({
          ...detail,
          citations: detail.citations.map((citation) => ({
            ...citation,
            citation_id: "duplicate-citation",
          })),
        }),
      );
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
  });

  it("withholds malformed proof digests and authority labels", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() =>
        response({
          ...detail,
          authority: "browser_asserted",
          citations: detail.citations.map((citation, index) =>
            index === 1 ? { ...citation, chunk_sha256: "not-a-digest" } : citation,
          ),
        }),
      );
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
  });

  it.each([
    ["canonical digest mismatch", { citations: detail.citations.map((citation, index) => index === 0 ? { ...citation, text_sha256: "9".repeat(64) } : citation) }],
    ["canonical metadata injection", { citations: detail.citations.map((citation, index) => index === 0 ? { ...citation, document_sha256: "9".repeat(64) } : citation) }],
    ["evidence metadata omission", { citations: detail.citations.map((citation, index) => index === 1 ? { ...citation, source_envelope_sha256: null } : citation) }],
  ])("withholds %s that violates the normalized citation schema", async (_label, change) => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementationOnce(() => response({ ...detail, ...change }));
    route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    expect(await screen.findByText("Evidence is not currently available.")).toBeTruthy();
    expect(screen.queryByText("Canonical note")).toBeNull();
  });

  it("renders an exact empty revision without inventing notes", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response({ ...collection, items: [] }));
    route();
    expect(await screen.findByText("No reviewed notes for this revision.")).toBeTruthy();
    expect(screen.queryByText(item.text)).toBeNull();
  });

  it("requires a revision and does not issue a request without one", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    route("/read/twin/source-a");
    expect(screen.getByRole("alert").textContent).toContain("exact revision is required");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses a safe unavailable state and retries the whole current projection", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({}, 503))
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection));
    route();
    fireEvent.click(await screen.findByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("heading", { name: twin.title })).toBeTruthy();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  });

  it("never renders a prior ready revision under a newly navigated URL", async () => {
    function NavigateRevision() {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/read/twin/source-b?revision=revision-b")}>Next revision</button>;
    }
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementation(() => new Promise<Response>(() => {}));
    render(
      <MemoryRouter initialEntries={["/read/twin/source-a?revision=revision-a"]}>
        <NavigateRevision />
        <Routes>
          <Route path="/read/twin/:sourceAssetId" element={<CanonicalTwinReader />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: twin.title })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next revision" }));
    expect(screen.queryByRole("heading", { name: twin.title })).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Opening this revision");
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("aborts an in-flight detail read when its note unmounts", async () => {
    let detailSignal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(twin))
      .mockImplementationOnce(() => response(collection))
      .mockImplementation((_input, init) => {
        detailSignal = init?.signal ?? undefined;
        return new Promise<Response>(() => {});
      });
    const view = route();
    fireEvent.click(await screen.findByRole("button", { name: "1 evidence source" }));
    await waitFor(() => expect(detailSignal).toBeDefined());
    view.unmount();
    expect(detailSignal?.aborted).toBe(true);
  });
});
