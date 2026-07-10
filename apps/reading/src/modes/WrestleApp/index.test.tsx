import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), abortSignals: [] as AbortSignal[], documentId: "doc-1" as string | undefined, starters: [] as unknown[] }));
vi.mock("react-router-dom", () => ({ useParams: () => ({ documentId: mocks.documentId }) }));
vi.mock("../../api/htmlProjections", async (original) => ({ ...(await original()), getHtmlProjectionByDocument: (id: string, signal: AbortSignal) => { mocks.abortSignals.push(signal); return mocks.get(id, signal); } }));
vi.mock("../../lib/api", () => ({ postTypedEvent: (value: unknown) => mocks.post(value) }));
vi.mock("../../hooks/useEventStream", () => ({ useEventStream: () => ({ events: ["event"], status: "open", reconnects: 0 }) }));
vi.mock("../../workspace/PanelHost", () => ({ PanelHost: ({ starters, children }: { starters: unknown[]; children: React.ReactNode }) => { mocks.starters = starters; return <main>{children}</main>; } }));
vi.mock("../../components/HtmlReader", () => ({ default: ({ html, initialAnchorId, onRegionSelected, investigationId, documentId }: any) => <section aria-label="HTML document reader" data-anchor={initialAnchorId} data-html={html}><button onClick={() => onRegionSelected({ investigationId, documentId, payload: { action_type: "document.region_selected", region_id: "r", page: 2, char_start: 1, char_end: 3, text_excerpt: "hi" } })}>select</button></section> }));

import { HtmlProjectionError } from "../../api/htmlProjections";
import WrestleApp from ".";

const projection = { identity: { source_document_id: "doc-1" }, projection_id: "hproj-a", html_sha256: "a".repeat(64), html: "<article>hello</article>", anchor_mappings: [] };
let resolveLoad: ((value: typeof projection) => void) | undefined;

beforeEach(() => {
  sessionStorage.clear(); history.replaceState({}, "", "/documents/doc-1");
  mocks.documentId = "doc-1"; mocks.get.mockReset(); mocks.post.mockReset().mockResolvedValue({}); mocks.abortSignals.length = 0; mocks.starters = [];
  mocks.get.mockResolvedValue(projection);
  vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-1234-1234-123456789abc" });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("WrestleApp HTML integration", () => {
  it("shows loading, renders HtmlReader, preserves panels, and has no legacy rendering path", async () => {
    mocks.get.mockImplementation(() => new Promise((resolve) => { resolveLoad = resolve; }));
    const { container } = render(<WrestleApp />);
    expect(screen.getByRole("status").textContent).toContain("Loading HTML projection");
    resolveLoad!(projection);
    expect((await screen.findByLabelText("HTML document reader")).getAttribute("data-html")).toBe(projection.html);
    expect(mocks.starters).toEqual(expect.arrayContaining([expect.objectContaining({ kind: "Notes", id: "wrestle:notes:inv-123456781234" }), expect.objectContaining({ kind: "CrossDocs" })]));
    expect(container.querySelector("input,canvas,iframe,object,embed")).toBeNull();
    expect(container.textContent).not.toMatch(/PDF|upload|blob/i);
  });

  it.each([[404, "No ready"], [409, "multiple ready"], [503, "storage is temporarily unavailable"], [500, "HTTP 500"]])("shows an honest %i failure", async (status, message) => {
    mocks.get.mockRejectedValue(new HtmlProjectionError(status, "backend detail"));
    render(<WrestleApp />);
    expect((await screen.findByRole("alert")).textContent).toContain(message);
  });

  it("requires documentId and does not fetch or offer fallback", () => {
    mocks.documentId = undefined; render(<WrestleApp />);
    expect(screen.getByRole("alert").textContent).toContain("document ID is required");
    expect(mocks.get).not.toHaveBeenCalled(); expect(screen.queryByRole("button")).toBeNull();
  });

  it("retries after failure", async () => {
    mocks.get.mockRejectedValueOnce(new HtmlProjectionError(404, "missing")).mockResolvedValueOnce(projection);
    render(<WrestleApp />); fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("HTML document reader")).not.toBeNull(); expect(mocks.get).toHaveBeenCalledTimes(2);
  });

  it("uses canonical ?anchor= and ignores ?page=", async () => {
    const anchor = `antiek-anchor-${"a".repeat(64)}`;
    history.replaceState({}, "", `/documents/doc-1?anchor=${anchor}&page=9`); render(<WrestleApp />);
    expect((await screen.findByLabelText("HTML document reader")).getAttribute("data-anchor")).toBe(anchor);
  });

  it("does not pass a malformed anchor into the HTML reader", async () => {
    history.replaceState({}, "", "/documents/doc-1?anchor=antiek-anchor-z"); render(<WrestleApp />);
    expect((await screen.findByLabelText("HTML document reader")).getAttribute("data-anchor")).toBeNull();
  });

  it("posts selection lineage exactly once and surfaces post errors", async () => {
    mocks.post.mockRejectedValue(new Error("write failed")); render(<WrestleApp />);
    fireEvent.click(await screen.findByRole("button", { name: "select" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    expect(mocks.post).toHaveBeenCalledWith({ investigation_id: "inv-123456781234", document_id: "doc-1", payload: expect.objectContaining({ action_type: "document.region_selected", region_id: "r" }), role: "user_agent" });
    expect((await screen.findByRole("alert")).textContent).toContain("write failed");
  });

  it("aborts on unmount and ignores a stale response after document change", async () => {
    const pending: Array<(value: typeof projection) => void> = [];
    mocks.get.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));
    const view = render(<WrestleApp />); mocks.documentId = "doc-2"; view.rerender(<WrestleApp />);
    expect(mocks.abortSignals[0].aborted).toBe(true); pending[0]({ ...projection, html: "stale" }); pending[1]({ ...projection, html: "fresh" });
    expect((await screen.findByLabelText("HTML document reader")).getAttribute("data-html")).toBe("fresh");
    view.unmount(); expect(mocks.abortSignals[1].aborted).toBe(true);
  });
});
