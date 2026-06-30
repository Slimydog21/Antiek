import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const { getPageMock, postTypedEventMock, openNotebookMock, toastOkMock } = vi.hoisted(() => ({
  getPageMock: vi.fn(),
  postTypedEventMock: vi.fn(),
  openNotebookMock: vi.fn(),
  toastOkMock: vi.fn(),
}));

vi.mock("pdfjs-dist/build/pdf.worker.mjs?url", () => ({
  default: "mock-pdf-worker.mjs",
}));

vi.mock("pdfjs-dist", () => {
  class TextLayer {
    constructor(_args: unknown) {}
    async render() {}
  }

  return {
    GlobalWorkerOptions: { workerSrc: "" },
    TextLayer,
    getDocument: vi.fn(() => ({
      promise: Promise.resolve({
        numPages: 5,
        getPage: getPageMock,
      }),
    })),
  };
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  postTypedEvent: postTypedEventMock,
}));

vi.mock("../workspace/actions", () => ({
  openNotebook: openNotebookMock,
}));

vi.mock("./lemon/LemonToast", () => ({
  toast: { ok: toastOkMock },
}));

import PdfViewer from "./PdfViewer";

function makePage(pageNumber: number) {
  return {
    getViewport: vi.fn(() => ({ width: 600, height: 800 })),
    render: vi.fn(() => ({ promise: Promise.resolve() })),
    getTextContent: vi.fn(() =>
      Promise.resolve({
        items: [{ str: `Page ${pageNumber} text` }],
      }),
    ),
  };
}

function renderViewer(initialPage?: number) {
  return render(
    <PdfViewer
      pdfBytes={new Uint8Array([1, 2, 3])}
      investigationId="inv-1"
      documentId="doc-1"
      initialPage={initialPage}
    />,
  );
}

describe("PdfViewer initialPage", () => {
  beforeEach(() => {
    getPageMock.mockReset();
    getPageMock.mockImplementation((pageNumber: number) => Promise.resolve(makePage(pageNumber)));
    postTypedEventMock.mockReset();
    openNotebookMock.mockReset();
    toastOkMock.mockReset();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    );
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the requested 1-based page and reports that page in the header", async () => {
    renderViewer(3);

    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(3));
    expect(await screen.findByText("page: 3")).toBeTruthy();
  });

  it("clamps an out-of-range requested page to the PDF page count", async () => {
    renderViewer(99);

    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(5));
    expect(await screen.findByText("page: 5")).toBeTruthy();
  });

  it("clamps a below-range requested page to page one", async () => {
    renderViewer(-4);

    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(1));
    expect(await screen.findByText("page: 1")).toBeTruthy();
  });

  it("rerenders when only the requested initial page changes", async () => {
    const pdfBytes = new Uint8Array([1, 2, 3]);
    const { rerender } = render(
      <PdfViewer
        pdfBytes={pdfBytes}
        investigationId="inv-1"
        documentId="doc-1"
        initialPage={2}
      />,
    );
    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(2));

    rerender(
      <PdfViewer
        pdfBytes={pdfBytes}
        investigationId="inv-1"
        documentId="doc-1"
        initialPage={4}
      />,
    );

    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(4));
    expect(await screen.findByText("page: 4")).toBeTruthy();
  });
});
