import { describe, expect, it, vi } from "vitest";

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
    getDocument: vi.fn(),
  };
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  postTypedEvent: vi.fn(),
}));

vi.mock("../workspace/actions", () => ({
  openNotebook: vi.fn(),
}));

vi.mock("./lemon/LemonToast", () => ({
  toast: { ok: vi.fn() },
}));

import { OnePageFixture, pdfViewerStoryBytes } from "./PdfViewer.stories";

describe("PdfViewer Storybook fixture", () => {
  it("uses real PDF bytes for the interactive story", () => {
    expect(pdfViewerStoryBytes.length).toBeGreaterThan(700);
    expect(new TextDecoder().decode(pdfViewerStoryBytes.slice(0, 8))).toBe("%PDF-1.4");
    expect(OnePageFixture.args?.pdfBytes).toBe(pdfViewerStoryBytes);
  });
});
