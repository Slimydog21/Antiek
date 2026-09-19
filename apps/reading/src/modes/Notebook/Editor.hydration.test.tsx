import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import type { Editor as TipTapEditor } from "@tiptap/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({
  generation: 1,
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock("../../lib/auth", () => ({
  useAuth: () => ({
    state: { status: "authenticated" },
    sessionGeneration: harness.generation,
  }),
}));

vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return {
    ...actual,
    getNotebookContent: harness.get,
    putNotebookContent: harness.put,
  };
});

import { ApiError } from "../../lib/api";
import { NotebookEditor } from "./Editor";
import { recoveryDraftKey } from "./recoveryDraft";

const HASH = "a".repeat(64);
const ACCOUNT = "b".repeat(64);
const RECOVERY = "c".repeat(64);

function proseDoc(text: string) {
  return {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text }] }],
  };
}

function content(text: string, revision = 7) {
  return {
    notebook_id: "nb-1",
    title: "Notebook",
    investigation_id: null,
    doc: proseDoc(text),
    revision,
    content_sha256: HASH,
    updated_at: "2026-07-15T00:00:00Z",
    account_scope: ACCOUNT,
    recovery_scope: RECOVERY,
  };
}

function installStorage(): Storage {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => void values.delete(key),
    setItem: (key, value) => void values.set(key, String(value)),
  };
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  return storage;
}

beforeEach(() => {
  installStorage();
  harness.generation = 1;
  harness.get.mockReset();
  harness.put.mockReset();
});

afterEach(cleanup);

describe("NotebookEditor server authority", () => {
  it("always hydrates from canonical server content and never reads legacy bytes", async () => {
    const storage = window.localStorage;
    storage.setItem("antiek.notebook.nb-1", "<p>FOREIGN-LEGACY-BYTES</p>");
    const getItem = vi.spyOn(storage, "getItem");
    harness.get.mockResolvedValue(content("SERVER-WINS"));

    const { container } = render(<NotebookEditor notebookId="nb-1" />);

    await waitFor(() => expect(container.textContent).toContain("SERVER-WINS"));
    expect(container.textContent).not.toContain("FOREIGN-LEGACY-BYTES");
    expect(container.textContent).toContain("unscoped bytes were not read");
    expect(getItem).not.toHaveBeenCalledWith("antiek.notebook.nb-1");
    expect(container.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true");
    expect(harness.get).toHaveBeenCalledWith("nb-1", expect.any(AbortSignal));
  });

  it("fails closed when hydration fails and cannot autosave", async () => {
    harness.get.mockRejectedValue(new Error("network down"));
    const editorRef = createRef<TipTapEditor>();
    const { container } = render(
      <NotebookEditor notebookId="nb-1" autosaveDelayMs={0} editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>} />,
    );

    await waitFor(() => expect(container.textContent).toContain("save unavailable"));
    expect(container.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("false");
    editorRef.current!.commands.insertContent("must not save");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(harness.put).not.toHaveBeenCalled();
  });

  it("sends the exact conditional mutation and advances its baseline", async () => {
    harness.get.mockResolvedValue(content("SERVER"));
    harness.put.mockResolvedValue({
      schema_version: 1,
      notebook_id: "nb-1",
      revision: 8,
      content_sha256: "d".repeat(64),
      replayed: false,
    });
    const editorRef = createRef<TipTapEditor>();
    render(
      <NotebookEditor notebookId="nb-1" autosaveDelayMs={0} editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>} />,
    );
    await waitFor(() => expect(document.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true"));

    editorRef.current!.commands.insertContent(" changed");
    await waitFor(() => expect(harness.put).toHaveBeenCalledTimes(1));
    expect(harness.put).toHaveBeenCalledWith(
      "nb-1",
      expect.objectContaining({
        schema_version: 1,
        base_revision: 7,
        mutation_key: expect.any(String),
        doc: expect.objectContaining({ type: "doc" }),
      }),
    );
  });

  it("serializes edits made while a save is in flight onto the acknowledged revision", async () => {
    harness.get.mockResolvedValue(content("SERVER"));
    let resolveFirst!: (value: Record<string, unknown>) => void;
    harness.put
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({ schema_version: 1, notebook_id: "nb-1", revision: 9, content_sha256: "e".repeat(64), replayed: false });
    const editorRef = createRef<TipTapEditor>();
    render(<NotebookEditor notebookId="nb-1" autosaveDelayMs={0} editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>} />);
    await waitFor(() => expect(document.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true"));
    editorRef.current!.commands.insertContent(" A");
    await waitFor(() => expect(harness.put).toHaveBeenCalledTimes(1));
    editorRef.current!.commands.insertContent(" B");
    resolveFirst({ schema_version: 1, notebook_id: "nb-1", revision: 8, content_sha256: "d".repeat(64), replayed: false });
    await waitFor(() => expect(harness.put).toHaveBeenCalledTimes(2));
    expect(harness.put.mock.calls[1][1]).toEqual(expect.objectContaining({ base_revision: 8 }));
    expect(JSON.stringify(harness.put.mock.calls[1][1].doc)).toContain("B");
  });

  it("stores an account-scoped recovery envelope only on transport failure", async () => {
    harness.get.mockResolvedValue(content("SERVER"));
    harness.put.mockRejectedValue(new TypeError("fetch failed"));
    const editorRef = createRef<TipTapEditor>();
    const { container } = render(
      <NotebookEditor notebookId="nb-1" autosaveDelayMs={0} editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>} />,
    );
    await waitFor(() => expect(container.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true"));
    editorRef.current!.commands.insertContent(" offline edit");

    await waitFor(() => expect(container.textContent).toContain("recovery saved locally"));
    const draft = JSON.parse(window.localStorage.getItem(recoveryDraftKey(RECOVERY))!);
    expect(draft).toMatchObject({
      schema_version: 2,
      account_scope: ACCOUNT,
      notebook_id: "nb-1",
      base_revision: 7,
      base_content_sha256: HASH,
    });
  });

  it("does not mislabel an HTTP conflict as offline or create a draft", async () => {
    harness.get.mockResolvedValue(content("SERVER"));
    harness.put.mockRejectedValue(new ApiError("conflict", 409, "{}"));
    const editorRef = createRef<TipTapEditor>();
    const { container } = render(
      <NotebookEditor notebookId="nb-1" autosaveDelayMs={0} editorRef={editorRef as React.MutableRefObject<TipTapEditor | null>} />,
    );
    await waitFor(() => expect(container.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true"));
    editorRef.current!.commands.insertContent(" conflict");

    await waitFor(() => expect(container.textContent).toContain("conflict — reload"));
    expect(window.localStorage.getItem(recoveryDraftKey(RECOVERY))).not.toBeNull();
  });

  it("loads a stale recovery draft for review without auto-overwriting canonical content", async () => {
    window.localStorage.setItem(recoveryDraftKey(RECOVERY), JSON.stringify({
      schema_version: 2, account_scope: ACCOUNT, notebook_id: "nb-1",
      base_revision: 6, base_content_sha256: "f".repeat(64),
      doc: proseDoc("STALE RECOVERY"), saved_at: "2026-07-14T00:00:00Z",
    }));
    harness.get.mockResolvedValue(content("NEW SERVER", 7));
    const { container } = render(<NotebookEditor notebookId="nb-1" autosaveDelayMs={0} />);
    await waitFor(() => expect(container.querySelector("button")).not.toBeNull());
    fireEvent.click(container.querySelector("button")!);
    await waitFor(() => expect(container.textContent).toContain("STALE RECOVERY"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(harness.put).not.toHaveBeenCalled();
  });

  it("fences a slow response after the auth generation changes", async () => {
    let resolveFirst!: (value: ReturnType<typeof content>) => void;
    harness.get.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }));
    harness.get.mockResolvedValueOnce(content("ACCOUNT-TWO"));
    const view = render(<NotebookEditor notebookId="nb-1" />);
    harness.generation = 2;
    view.rerender(<NotebookEditor notebookId="nb-1" />);
    resolveFirst(content("STALE-ACCOUNT-ONE"));

    await waitFor(() => expect(view.container.textContent).toContain("ACCOUNT-TWO"));
    expect(view.container.textContent).not.toContain("STALE-ACCOUNT-ONE");
  });
});
