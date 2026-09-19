import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HostedDocumentPanel, { resolveCitationAnchors } from "./HostedDocumentPanel";
import { PanelRegistry } from "../workspace/PanelRegistry";

const { fetchHostedDocument } = vi.hoisted(() => ({ fetchHostedDocument: vi.fn() }));
const auth = vi.hoisted(() => ({ sessionGeneration: 1 }));
vi.mock("../api/hostedDocuments", () => ({ fetchHostedDocument }));
vi.mock("../lib/auth", () => ({ useAuth: () => auth }));
vi.mock("./windows/HostedHtmlDocumentHost", () => ({
  default: (props: { document_id: string; html: string; view_format: string; initial_anchor_id?: string; citation_anchor_ids?: string[]; citation_receipt_sha256?: string }) => (
    <article data-testid="canonical-host" data-document-id={props.document_id} data-view-format={props.view_format} data-anchor={props.initial_anchor_id ?? ""} data-anchors={(props.citation_anchor_ids ?? []).join(",")} data-receipt={props.citation_receipt_sha256 ?? ""}>{props.html}</article>
  ),
}));

const receipt = {
  document_id: "doc-1", owner_id: "owner", state: "ready", view_format: "html",
  html: "<p>Canonical body</p>", title: "Document", non_viewable_reason: null,
};

beforeEach(() => {
  fetchHostedDocument.mockReset();
  auth.sessionGeneration = 1;
});
afterEach(() => cleanup());

describe("HostedDocumentPanel", () => {
  it("fetches the owner-gated canonical id and renders HTML only", async () => {
    fetchHostedDocument.mockResolvedValue(receipt);
    render(<HostedDocumentPanel documentId="doc-1" initialPage={12} />);
    expect(await screen.findByTestId("canonical-host")).toBeTruthy();
    expect(fetchHostedDocument).toHaveBeenCalledWith("doc-1", []);
    expect(screen.getByTestId("hosted-document-panel").getAttribute("data-source-page")).toBe("12");
  });

  it("requests sealed citation projection and forwards only the server anchor", async () => {
    fetchHostedDocument.mockResolvedValue({
      ...receipt,
      chunk_anchors: [{ chunk_id: "chunk-1", anchor_id: `antiek-chunk-${"a".repeat(64)}` }],
    });
    render(<HostedDocumentPanel documentId="doc-1" citationChunkIds={["chunk-1"]} citationReceiptSha256={"c".repeat(64)} />);
    const host = await screen.findByTestId("canonical-host");
    expect(fetchHostedDocument).toHaveBeenCalledWith("doc-1", ["chunk-1"]);
    expect(host.getAttribute("data-anchor")).toBe(`antiek-chunk-${"a".repeat(64)}`);
    expect(host.getAttribute("data-anchors")).toBe(`antiek-chunk-${"a".repeat(64)}`);
    expect(host.getAttribute("data-receipt")).toBe("c".repeat(64));
    expect(resolveCitationAnchors(["chunk-1"], [
      { chunk_id: "wrong", anchor_id: `antiek-chunk-${"a".repeat(64)}` },
    ])).toEqual([]);
  });

  it("fails closed for non-viewable canonical HTML", async () => {
    fetchHostedDocument.mockResolvedValue({ ...receipt, state: "non_viewable", html: null, non_viewable_reason: "extraction incomplete" });
    render(<HostedDocumentPanel document_id="doc-1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("extraction incomplete");
  });

  it("fails closed when the owner-gated fetch rejects", async () => {
    fetchHostedDocument.mockRejectedValueOnce(new Error("hosted document API 404"));
    render(<HostedDocumentPanel documentId="foreign-doc" />);
    expect((await screen.findByRole("alert")).textContent).toContain("hosted document API 404");
  });

  it("rejects a ready receipt for a different canonical document id", async () => {
    fetchHostedDocument.mockResolvedValue({ ...receipt, document_id: "doc-other" });
    render(<HostedDocumentPanel documentId="doc-1" />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/identity does not match/i);
    expect(screen.queryByTestId("canonical-host")).toBeNull();
  });

  it("maps legacy persisted PdfViewer descriptors to the canonical loader", () => {
    expect(PanelRegistry.PdfViewer).toBe(PanelRegistry.HostedDocument);
  });

  it("renders a legacy PdfViewer descriptor through authenticated canonical HTML", async () => {
    fetchHostedDocument.mockResolvedValue(receipt);
    const LegacyRenderer = PanelRegistry.PdfViewer;
    render(<Suspense fallback={<p>Loading migration…</p>}><LegacyRenderer documentId="doc-1" initialPage={7} /></Suspense>);
    expect(await screen.findByTestId("canonical-host")).toBeTruthy();
    expect(fetchHostedDocument).toHaveBeenCalledWith("doc-1", []);
    expect(screen.getByTestId("hosted-document-panel").getAttribute("data-source-page")).toBe("7");
  });

  it("ignores a stale response after the canonical id changes", async () => {
    let resolveFirst!: (value: unknown) => void;
    fetchHostedDocument.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }));
    fetchHostedDocument.mockResolvedValueOnce({ ...receipt, document_id: "doc-2", html: "<p>Second</p>" });
    const view = render(<HostedDocumentPanel documentId="doc-1" />);
    view.rerender(<HostedDocumentPanel documentId="doc-2" />);
    await screen.findByTestId("canonical-host");
    resolveFirst({ ...receipt, html: "<p>Stale</p>" });
    await waitFor(() => expect(screen.getByTestId("canonical-host").getAttribute("data-document-id")).toBe("doc-2"));
  });

  it("clears and reauthorizes canonical HTML when the account session changes", async () => {
    let resolveSecond!: (value: unknown) => void;
    fetchHostedDocument
      .mockResolvedValueOnce({ ...receipt, html: "<p>First account</p>" })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));
    const view = render(<HostedDocumentPanel documentId="doc-1" />);
    expect((await screen.findByTestId("canonical-host")).textContent).toContain("First account");
    auth.sessionGeneration = 2;
    view.rerender(<HostedDocumentPanel documentId="doc-1" />);
    expect(screen.queryByTestId("canonical-host")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Loading canonical HTML");
    resolveSecond({ ...receipt, html: "<p>Second account</p>" });
    await waitFor(() => expect(screen.getByTestId("canonical-host").textContent).toContain("Second account"));
    expect(fetchHostedDocument).toHaveBeenCalledTimes(2);
  });
});
