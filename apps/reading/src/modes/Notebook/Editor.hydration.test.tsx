/**
 * Editor.hydration.test.tsx — SPR-01 M5.
 *
 * Two defenses close the fresh-browser data-loss bug; this file pins the
 * client half:
 *
 *   1. A fresh mount (empty localStorage) hydrates the editor from the
 *      substrate GET (/notebooks/{id}/content), NOT the empty `<p></p>` seed —
 *      so the first autosave carries the real doc, never an empty one.
 *   2. The 1.5 s autosave timer is GATED on a "hydrated" flag: an edit during
 *      the hydration window must not PUT (that pre-hydration doc could wipe
 *      persisted blocks). After hydration, autosave works and carries the real
 *      doc.
 *   3. Offline fallback preserved: when the GET fails, the editor keeps its
 *      cached (localStorage) content and still becomes hydrated so the operator
 *      can keep editing.
 *
 * We mock at the api boundary (getNotebookContent + apiFetch) — jsdom needs no
 * network. TipTap renders in jsdom; we drive edits through the real editor via
 * the `editorRef` handle.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import type { Editor as TipTapEditor } from "@tiptap/react";

const { getNotebookContentMock, apiFetchMock } = vi.hoisted(() => ({
  getNotebookContentMock: vi.fn(),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getNotebookContent: getNotebookContentMock,
    apiFetch: apiFetchMock,
  };
});

import { NotebookEditor } from "./Editor";

function proseDoc(text: string) {
  return {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text }] }],
  };
}

afterEach(() => {
  cleanup();
  getNotebookContentMock.mockReset();
  apiFetchMock.mockReset();
  window.localStorage.clear();
});

beforeEach(() => {
  window.localStorage.clear();
});

describe("NotebookEditor — substrate hydration (M5)", () => {
  it("hydrates a fresh mount from the substrate GET, not the empty <p></p> seed", async () => {
    getNotebookContentMock.mockResolvedValue({
      notebook_id: "nb-1",
      doc: proseDoc("HYDRATED-FROM-SUBSTRATE"),
    });

    const { container } = render(<NotebookEditor notebookId="nb-1" />);

    await waitFor(() =>
      expect(container.textContent).toContain("HYDRATED-FROM-SUBSTRATE"),
    );
    const root = container.querySelector("[data-notebook-editor]");
    expect(root?.getAttribute("data-hydrated")).toBe("true");
    // It called the hydration GET for this notebook.
    expect(getNotebookContentMock).toHaveBeenCalledWith("nb-1");
  });

  it("keeps cached content and still hydrates when the GET fails (offline)", async () => {
    window.localStorage.setItem(
      "antiek.notebook.nb-off",
      "<p>CACHED-OFFLINE-DRAFT</p>",
    );
    getNotebookContentMock.mockRejectedValue(new Error("network down"));

    const { container } = render(<NotebookEditor notebookId="nb-off" />);

    // The cached draft is preserved (never blown away by a failed fetch)…
    await waitFor(() =>
      expect(container.textContent).toContain("CACHED-OFFLINE-DRAFT"),
    );
    // …and hydration still "completes" so the operator can keep editing.
    await waitFor(() => {
      const root = container.querySelector("[data-notebook-editor]");
      expect(root?.getAttribute("data-hydrated")).toBe("true");
    });
  });
});

describe("NotebookEditor — autosave gated on hydration (M5)", () => {
  it("never autosaves before hydration; saves the real doc after", async () => {
    // Hold hydration open so we can edit inside the window.
    let resolveHydration!: (v: {
      notebook_id: string;
      doc: Record<string, unknown>;
    }) => void;
    getNotebookContentMock.mockReturnValue(
      new Promise((res) => {
        resolveHydration = res;
      }),
    );
    apiFetchMock.mockResolvedValue({ ok: true, status: 200 });

    const editorRef = createRef<TipTapEditor>();
    render(
      <NotebookEditor
        notebookId="nb-1"
        autosaveDelayMs={0}
        editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>}
      />,
    );

    await waitFor(() => expect(editorRef.current).toBeTruthy());

    // Edit BEFORE hydration resolves — the gate must hold the save.
    editorRef.current!.commands.insertContent("typed before hydration");
    await new Promise((r) => setTimeout(r, 20));
    expect(apiFetchMock).not.toHaveBeenCalled();

    // Hydration completes (server has no blocks yet → keeps the typed text).
    resolveHydration({ notebook_id: "nb-1", doc: { type: "doc", content: [] } });
    await waitFor(() => {
      const root = document.querySelector("[data-notebook-editor]");
      expect(root?.getAttribute("data-hydrated")).toBe("true");
    });

    // Now an edit DOES autosave — carrying the real (non-empty) doc.
    editorRef.current!.commands.insertContent(" and after");
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());

    const lastCall = apiFetchMock.mock.calls.at(-1)!;
    expect(String(lastCall[0])).toContain("/notebooks/nb-1/content");
    expect(lastCall[1]?.method).toBe("PUT");
    const body = JSON.parse(lastCall[1]?.body as string);
    // The saved doc is the operator's real content, never an empty doc.
    const savedText = JSON.stringify(body.doc);
    expect(savedText).toContain("typed before hydration");
  });
});
