import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import DocumentStylePreview from "./DocumentStylePreview";

const styles = {
  styles: [
    { name: "antiek", label: "Antiek", description: "Default", builtin: true, source_fidelity: false, theme_css: "", parent: null },
    { name: "book", label: "Book", description: "A printed page", builtin: true, source_fidelity: true, theme_css: "", parent: null },
  ],
};

const HASH = "c".repeat(64);

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** A projected document as `GET /documents/{id}/render` answers it. */
function projected(style: string, documentId = "doc-9", revision = "2") {
  return new Response("<!doctype html><title>Projected</title>", {
    headers: {
      "Content-Type": "text/html",
      "X-Document-ID": documentId,
      "X-Artifact-Style": style,
      "X-Content-SHA256": HASH,
      "X-Reader-Revision": revision,
    },
  });
}

function styleOf(url: string): string {
  return new URL(url, "http://test").searchParams.get("style") ?? "antiek";
}

describe("DocumentStylePreview", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      if (url.startsWith("/documents/doc-9/render")) return Promise.resolve(projected(styleOf(url)));
      return Promise.resolve(json({ detail: `unexpected ${url}` }, 500));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("projects the document through GET /documents/{id}/render in a sandboxed frame", async () => {
    render(<DocumentStylePreview documentId="doc-9" />);
    const frame = await screen.findByTitle("Antiek document preview");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(screen.getByRole("listbox", { name: "Document styles" }).getAttribute("aria-orientation")).toBe(
      "horizontal",
    );
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/documents/doc-9/render?style=antiek",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    // Every render call is a GET: the route has no apply leg.
    for (const [url, init] of apiFetchMock.mock.calls.filter(([u]) => String(u).includes("/render"))) {
      expect(String(url)).toContain("/documents/");
      expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
    }
  });

  it("re-projects the same document when another style is picked", async () => {
    render(<DocumentStylePreview documentId="doc-9" />);
    await screen.findByTitle("Antiek document preview");
    fireEvent.click(screen.getByRole("option", { name: /Book/ }));
    await screen.findByTitle("Book document preview");
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/documents/doc-9/render?style=book",
      expect.anything(),
    );
    expect(screen.getByTestId("document-render-receipt").textContent).toContain("reader rev 2");
  });

  it("offers no Apply action and no version receipt", async () => {
    render(<DocumentStylePreview documentId="doc-9" />);
    await screen.findByTitle("Antiek document preview");
    expect(screen.queryByRole("button", { name: /Apply/ })).toBeNull();
    expect(screen.queryByText(/Version .* saved/)).toBeNull();
    expect(screen.getByText(/Preview only/).textContent).toContain("no version chain");
  });

  it("refuses a render whose receipt names another document", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      return Promise.resolve(projected(styleOf(url), "doc-other"));
    });
    render(<DocumentStylePreview documentId="doc-9" />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "invalid or mismatched document receipt",
    );
    expect(screen.queryByTitle("Antiek document preview")).toBeNull();
  });

  it("names the serve gate's refusal instead of a generic failure", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      return Promise.resolve(json({ detail: "sanitizer_version_stale" }, 422));
    });
    render(<DocumentStylePreview documentId="doc-9" />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("older sanitizer version");
    expect(alert.textContent).toContain("resanitize_reader_html");
    await waitFor(() => expect(screen.getByText("Preview unavailable for this document.")).toBeTruthy());
  });

  it("shows an honest unavailable state when the wheel cannot load", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("backend offline"));
    render(<DocumentStylePreview documentId="doc-9" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Styles unavailable · backend offline");
  });

  it("starts on the requested style when the wheel has it", async () => {
    render(<DocumentStylePreview documentId="doc-9" initialStyle="book" />);
    await screen.findByTitle("Book document preview");
    expect(screen.getByRole("option", { name: /Book/ }).getAttribute("aria-selected")).toBe("true");
  });
});
