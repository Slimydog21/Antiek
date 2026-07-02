import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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
    private readonly args: { textContentSource: { items: { str: string }[] }; container: HTMLElement };

    constructor(args: { textContentSource: { items: { str: string }[] }; container: HTMLElement }) {
      this.args = args;
    }

    async render() {
      for (const item of this.args.textContentSource.items) {
        const span = document.createElement("span");
        span.textContent = item.str;
        this.args.container.appendChild(span);
      }
    }
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

const defaultTextItems = [{ str: "Page " }, { str: "1" }, { str: " text" }];
let textItems = defaultTextItems;

function makePage(pageNumber: number) {
  return {
    getViewport: vi.fn(() => ({ width: 600, height: 800 })),
    render: vi.fn(() => ({ promise: Promise.resolve() })),
    getTextContent: vi.fn(() =>
      Promise.resolve({
        items: textItems.map((item) => ({
          str: item.str.replace("{page}", String(pageNumber)),
        })),
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
    textItems = defaultTextItems;
    postTypedEventMock.mockReset();
    postTypedEventMock.mockResolvedValue({ event_id: "evt-1", action_type: "document.region_selected" });
    openNotebookMock.mockReset();
    toastOkMock.mockReset();
    vi.stubGlobal("crypto", { randomUUID: () => "12345678-90ab-cdef-1234-567890abcdef" });
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

  it("maps a selection to the exact text-layer offset when the phrase repeats", async () => {
    textItems = [
      { str: "alpha repeated " },
      { str: "middle " },
      { str: "alpha repeated" },
    ];
    const { container } = renderViewer(1);
    await waitFor(() => expect(getPageMock).toHaveBeenCalledWith(1));

    const spans = Array.from(container.querySelectorAll(".pdf-text-layer span"));
    const repeatedTextNode = spans[2]?.firstChild;
    expect(repeatedTextNode).toBeTruthy();

    const range = document.createRange();
    range.setStart(repeatedTextNode!, 0);
    range.setEnd(repeatedTextNode!, "alpha repeated".length);
    Object.defineProperty(range, "getBoundingClientRect", {
      value: () => ({
        left: 20,
        top: 30,
        right: 120,
        bottom: 48,
        width: 100,
        height: 18,
        x: 20,
        y: 30,
        toJSON: () => ({}),
      }),
    });
    vi.stubGlobal("getSelection", () => ({
      isCollapsed: false,
      anchorNode: repeatedTextNode,
      toString: () => "alpha repeated",
      getRangeAt: () => range,
    }));

    const layer = container.querySelector(".pdf-text-layer") as HTMLElement;
    vi.spyOn(layer, "getBoundingClientRect").mockReturnValue({
      left: 10,
      top: 20,
      right: 610,
      bottom: 820,
      width: 600,
      height: 800,
      x: 10,
      y: 20,
      toJSON: () => ({}),
    });

    fireEvent.mouseUp(layer.parentElement!.parentElement!);

    await waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const payload = postTypedEventMock.mock.calls[0][0].payload;
    expect(payload.char_start).toBe("alpha repeated middle ".length);
    expect(payload.char_end).toBe("alpha repeated middle alpha repeated".length);
    expect(payload.text_excerpt).toBe("alpha repeated");
    expect(payload.bbox).toEqual([10, 10, 110, 28]);
  });
});
