import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HtmlReaderPanel from "./HtmlReaderPanel";
import { getHtmlProjectionByDocument } from "../api/htmlProjections";
import { postTypedEvent } from "../lib/api";

vi.mock("../api/htmlProjections", async (load) => ({ ...(await load<typeof import("../api/htmlProjections")>()), getHtmlProjectionByDocument: vi.fn() }));
vi.mock("../lib/api", () => ({ postTypedEvent: vi.fn() }));
vi.mock("./HtmlReader", () => ({
  default: ({ documentId, investigationId, initialAnchorId, onRegionSelected }: { documentId: string; investigationId: string; initialAnchorId?: string; onRegionSelected: (value: unknown) => void }) => <button data-testid="reader" data-document={documentId} data-investigation={investigationId} data-anchor={initialAnchorId} onClick={() => void onRegionSelected({ documentId: "spoofed", investigationId: "spoofed", payload: { action_type: "document.region_selected", region_id: "r1" }, anchor: {} })}>reader</button>,
}));

const projection = { html: "<p id=\"antiek-anchor-1\">one</p>", projection_id: `hproj-${"a".repeat(64)}`, html_sha256: "b".repeat(64), identity: {}, anchor_mappings: [] };
const deferred = <T,>() => { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HtmlReaderPanel", () => {
  it("aborts stale loads and only renders the current document with its anchor", async () => {
    const first = deferred<typeof projection>();
    vi.mocked(getHtmlProjectionByDocument).mockImplementationOnce((_id, signal) => { expect(signal).toBeInstanceOf(AbortSignal); return first.promise; }).mockResolvedValueOnce(projection);
    const view = render(<HtmlReaderPanel documentId="doc-old" anchorId="antiek-anchor-old" />);
    view.rerender(<HtmlReaderPanel documentId="doc-new" anchorId="antiek-anchor-new" />);
    await screen.findByTestId("reader");
    expect(screen.getByTestId("reader").getAttribute("data-document")).toBe("doc-new");
    expect(screen.getByTestId("reader").getAttribute("data-anchor")).toBe("antiek-anchor-new");
    await act(async () => first.resolve(projection));
    expect(screen.getByTestId("reader").getAttribute("data-document")).toBe("doc-new");
  });

  it("shows load errors and retries", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(projection);
    render(<HtmlReaderPanel documentId="doc-1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("offline");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading HTML projection" }));
    await screen.findByTestId("reader");
    expect(getHtmlProjectionByDocument).toHaveBeenCalledTimes(2);
  });

  it("posts selections with authoritative panel lineage and reports post failure", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockResolvedValue(projection);
    vi.mocked(postTypedEvent).mockRejectedValueOnce(new Error("write failed"));
    render(<HtmlReaderPanel documentId="doc-real" investigationId="inv-real" />);
    fireEvent.click(await screen.findByTestId("reader"));
    await waitFor(() => expect(postTypedEvent).toHaveBeenCalledWith(expect.objectContaining({ document_id: "doc-real", investigation_id: "inv-real", role: "user_agent" })));
    expect((await screen.findByRole("alert")).textContent).toContain("write failed");
  });
});
