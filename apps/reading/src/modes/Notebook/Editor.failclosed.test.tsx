/**
 * Editor.failclosed.test.tsx — audit wave4 C12 + C13.
 *
 * C12: a failed hydration GET with nothing cached used to leave an EMPTY
 * editor marked hydrated. The first word typed then PUT a one-paragraph doc,
 * and the server's atomic replace deleted every persisted block (its
 * empty-doc floor only refuses EMPTY docs). Pinned: on a non-404 GET failure
 * over an empty editor, the autosave gate stays closed, the editor is
 * read-only, an alert with a retry is shown, and the retry hydrates from the
 * substrate before any save. A 404 (a notebook with no server row — scratch,
 * claim-* notebooks) has nothing to destroy and still hydrates.
 *
 * C13: every non-2xx PUT fell into the offline branch and showed "saved to
 * local". Pinned: a network failure (and a 404 local-only notebook) still
 * reads "saved to local"; a server REJECTION (401/403/409/422/500) reads as
 * not saved, and the draft is still kept in localStorage.
 *
 * Mocks at the api boundary (getNotebookContent + apiFetch), as in
 * Editor.hydration.test.tsx; edits go through the real TipTap editor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { ApiError } from "../../lib/api";
import { NotebookEditor } from "./Editor";

function proseDoc(...texts: string[]) {
  return {
    type: "doc",
    content: texts.map((text) => ({
      type: "paragraph",
      content: [{ type: "text", text }],
    })),
  };
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  getNotebookContentMock.mockReset();
  apiFetchMock.mockReset();
  window.localStorage.clear();
});

function mount(notebookId: string) {
  const editorRef = createRef<TipTapEditor>();
  const utils = render(
    <NotebookEditor
      notebookId={notebookId}
      autosaveDelayMs={0}
      editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>}
    />,
  );
  return { ...utils, editorRef };
}

function root() {
  return document.querySelector("[data-notebook-editor]");
}

describe("C12 — failed hydration with no cache fails closed", () => {
  it.each([
    ["HTTP 500", () => new ApiError("HTTP 500", 500, "")],
    ["HTTP 401", () => new ApiError("HTTP 401", 401, "")],
    ["network", () => new TypeError("Failed to fetch")],
  ])("%s: no PUT, editor read-only, alert shown", async (_l, make) => {
    getNotebookContentMock.mockRejectedValue(make());
    apiFetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { editorRef } = mount("nb-x");
    await waitFor(() => expect(editorRef.current).toBeTruthy());
    await screen.findByRole("alert");

    expect(root()?.getAttribute("data-hydrated")).toBe("false");
    expect(editorRef.current!.isEditable).toBe(false);

    editorRef.current!.commands.insertContent("hello");
    await new Promise((r) => setTimeout(r, 30));
    expect(apiFetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("saved")).toBeNull();
  });

  it("retry hydrates from the substrate; the next save carries every block", async () => {
    getNotebookContentMock.mockRejectedValueOnce(new ApiError("HTTP 503", 503, ""));
    getNotebookContentMock.mockResolvedValue({
      notebook_id: "nb-x",
      doc: proseDoc("SERVER-BLOCK-1", "SERVER-BLOCK-2"),
    });
    apiFetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { editorRef, container } = mount("nb-x");
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    await waitFor(() => expect(container.textContent).toContain("SERVER-BLOCK-2"));
    await waitFor(() => expect(root()?.getAttribute("data-hydrated")).toBe("true"));
    expect(editorRef.current!.isEditable).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();

    editorRef.current!.commands.insertContent("hello");
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
    const body = JSON.parse(apiFetchMock.mock.calls.at(-1)![1].body as string);
    expect(JSON.stringify(body.doc)).toContain("SERVER-BLOCK-1");
    expect(JSON.stringify(body.doc)).toContain("SERVER-BLOCK-2");
  });

  it("CONTROL: a 404 (no server notebook, nothing to destroy) still hydrates and saves", async () => {
    getNotebookContentMock.mockRejectedValue(new ApiError("HTTP 404", 404, ""));
    apiFetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { editorRef } = mount("scratch");
    await waitFor(() => expect(root()?.getAttribute("data-hydrated")).toBe("true"));
    expect(screen.queryByRole("alert")).toBeNull();
    editorRef.current!.commands.insertContent("hello");
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
  });
});

describe("C13 — a server rejection is not 'saved to local'", () => {
  async function saveWith(response: unknown) {
    getNotebookContentMock.mockResolvedValue({
      notebook_id: "nb-s",
      doc: proseDoc("SERVER"),
    });
    if (response instanceof Error) apiFetchMock.mockRejectedValue(response);
    else apiFetchMock.mockResolvedValue(response);

    const { editorRef } = mount("nb-s");
    await waitFor(() => expect(root()?.getAttribute("data-hydrated")).toBe("true"));
    editorRef.current!.commands.insertContent("Y");
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
  }

  it.each([401, 403, 409, 422, 500])("HTTP %i shows not saved, keeps the draft", async (status) => {
    await saveWith({ ok: false, status });

    await waitFor(() => expect(screen.getByText(/^not saved/)).toBeTruthy());
    expect(screen.queryByText("saved to local")).toBeNull();
    expect(screen.queryByText("saved")).toBeNull();
    // The draft survives locally even though the server refused it.
    expect(window.localStorage.getItem("antiek.notebook.nb-s")).toContain("Y");
  });

  it("401/403 tell the operator to sign in; 409 to reload", async () => {
    await saveWith({ ok: false, status: 403 });
    await waitFor(() => expect(screen.getByText("not saved — sign in again")).toBeTruthy());
  });

  it("409 tells the operator to reload", async () => {
    await saveWith({ ok: false, status: 409 });
    await waitFor(() => expect(screen.getByText("not saved — reload")).toBeTruthy());
  });

  it("CONTROL: a network failure still reads 'saved to local'", async () => {
    await saveWith(new TypeError("Failed to fetch"));
    await waitFor(() => expect(screen.getByText("saved to local")).toBeTruthy());
  });

  it("CONTROL: a 404 (local-only notebook) still reads 'saved to local'", async () => {
    await saveWith({ ok: false, status: 404 });
    await waitFor(() => expect(screen.getByText("saved to local")).toBeTruthy());
  });

  // The substrate implements PUT /notebooks/{id}/content, so a 405 or 501 is
  // never its refusal: the host that answered is not the substrate (a static
  // host, a proxy, a wrong base URL). That is the offline class. The e2e
  // smoke and operator-day specs run the editor against exactly such a host
  // (Storybook's static server) and pin "saved to local".
  it.each([405, 501])("CONTROL: HTTP %i (host is not the substrate) reads 'saved to local'", async (status) => {
    await saveWith({ ok: false, status });
    await waitFor(() => expect(screen.getByText("saved to local")).toBeTruthy());
    expect(screen.queryByText(/^not saved/)).toBeNull();
  });

  it("CONTROL: a 200 reads 'saved'", async () => {
    await saveWith({ ok: true, status: 200 });
    await waitFor(() => expect(screen.getByText("saved")).toBeTruthy());
  });
});
