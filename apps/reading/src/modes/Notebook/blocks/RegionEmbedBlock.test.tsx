import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NodeViewProps } from "@tiptap/react";

import { getHtmlProjectionByDocument } from "../../../api/htmlProjections";
import { openReader } from "../../../workspace/actions";
import { RegionEmbedNodeView, resolveLegacyPageAnchor } from "./RegionEmbedBlock";

vi.mock("../../../api/htmlProjections", async (load) => ({
  ...(await load<typeof import("../../../api/htmlProjections")>()),
  getHtmlProjectionByDocument: vi.fn(),
}));
vi.mock("../../../workspace/actions", () => ({ openReader: vi.fn() }));
vi.mock("../../../components/lemon/LemonCard", () => ({
  default: ({ title, children }: { title: React.ReactNode; children: React.ReactNode }) => <section>{title}{children}</section>,
}));

const mapping = (kind: string, page: number, id: string) => ({
  source_locator: { kind, page }, state: "resolved" as const, html_anchor_id: id, candidates: [] as const,
});
const projection = (anchor_mappings: ReturnType<typeof mapping>[]) => ({
  identity: {}, projection_id: `hproj-${"a".repeat(64)}`, html_sha256: "b".repeat(64), html: "", anchor_mappings,
});
const props = (attrs: Record<string, unknown>) => ({ node: { attrs }, deleteNode: vi.fn() }) as unknown as NodeViewProps;
const canonical = (char: string) => `antiek-anchor-${char.repeat(64)}`;

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("resolveLegacyPageAnchor", () => {
  it("returns the sole matching resolved PDF mapping", () => {
    expect(resolveLegacyPageAnchor([mapping("pdf_page_bbox", 4, "anchor-4")], 4)).toBe("anchor-4");
  });

  it("returns null for none, multiple, and non-PDF mappings", () => {
    expect(resolveLegacyPageAnchor([], 4)).toBeNull();
    expect(resolveLegacyPageAnchor([mapping("pdf_page_bbox", 4, "a"), mapping("pdf_page_bbox", 4, "b")], 4)).toBeNull();
    expect(resolveLegacyPageAnchor([mapping("epub_cfi", 4, "a")], 4)).toBeNull();
  });
});

describe("RegionEmbedNodeView", () => {
  it("opens a canonical anchor directly without loading a projection", () => {
    render(<RegionEmbedNodeView {...props({ document_id: "doc-1", anchor_id: canonical("a"), source_page: 3 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open region" }));
    expect(openReader).toHaveBeenCalledWith({ documentId: "doc-1", anchorId: canonical("a") });
    expect(getHtmlProjectionByDocument).not.toHaveBeenCalled();
  });

  it("resolves a legacy page to exactly one anchor and disables while loading", async () => {
    let resolve!: (value: ReturnType<typeof projection>) => void;
    vi.mocked(getHtmlProjectionByDocument).mockReturnValue(new Promise((yes) => { resolve = yes; }));
    render(<RegionEmbedNodeView {...props({ document_id: "doc-1", page: 8 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open region" }));
    expect((screen.getByRole("button", { name: "Resolving…" }) as HTMLButtonElement).disabled).toBe(true);
    resolve(projection([mapping("pdf_page_bbox", 8, "anchor-8")]));
    await waitFor(() => expect(openReader).toHaveBeenCalledWith({ documentId: "doc-1", anchorId: "anchor-8" }));
  });

  it("shows an accessible unresolved error for missing or ambiguous mappings", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockResolvedValue(projection([
      mapping("pdf_page_bbox", 8, "a"), mapping("pdf_page_bbox", 8, "b"),
    ]));
    render(<RegionEmbedNodeView {...props({ document_id: "doc-1", page: 8 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open region" }));
    expect((await screen.findByRole("alert")).textContent).toContain("exactly one");
    expect(openReader).not.toHaveBeenCalled();
  });

  it("shows projection errors (including 404) without opening", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockRejectedValue(new Error("HTTP 404"));
    render(<RegionEmbedNodeView {...props({ document_id: "doc-404", page: 2 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open region" }));
    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 404");
    expect(openReader).not.toHaveBeenCalled();
  });

  it("renders an honest disabled state when document or locator is missing", () => {
    render(<RegionEmbedNodeView {...props({ caption: "orphan" })} />);
    expect((screen.getByRole("button", { name: "Open region" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("no document");
  });

  it("refuses a malformed persisted canonical anchor", () => {
    render(<RegionEmbedNodeView {...props({ document_id: "doc-1", anchor_id: "anchor-1" })} />);
    expect((screen.getByRole("button", { name: "Open region" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("malformed canonical anchor");
    expect(openReader).not.toHaveBeenCalled();
  });

  it("aborts and ignores a legacy resolution after unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(getHtmlProjectionByDocument).mockImplementation((_id, received) => {
      signal = received;
      return new Promise(() => undefined);
    });
    const view = render(<RegionEmbedNodeView {...props({ document_id: "doc-1", page: 3 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Open region" }));
    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(openReader).not.toHaveBeenCalled();
  });
});
