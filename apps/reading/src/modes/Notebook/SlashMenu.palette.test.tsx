import { createRef } from "react";
import type { Editor } from "@tiptap/react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import CommandPalette from "../../components/CommandPalette";
import { readKeyboardOwnership } from "../../workspace/keyboardOwnership";
import { installShortcuts } from "../../workspace/shortcuts";
import { NotebookEditor } from "./Editor";

// Only network data is synthetic. TipTap, both overlays and the dispatcher run.
vi.mock("../../lib/api", async (original) => ({
  ...(await original<typeof import("../../lib/api")>()),
  getNotebookContent: vi.fn(async () => ({
    notebook_id: "escape-yield", doc: { type: "doc", content: [{ type: "paragraph" }] },
  })),
  apiFetch: vi.fn(async () => new Response("{}", { status: 404 })),
}));

// jsdom has no Range geometry; ProseMirror needs it when focus returns.
const rangeGeometry = Object.getOwnPropertyDescriptors(Range.prototype);
beforeAll(() => {
  Object.defineProperties(Range.prototype, {
    getClientRects: { configurable: true, value: () => [] },
    getBoundingClientRect: { configurable: true, value: () => new DOMRect() },
  });
});
afterAll(() => {
  for (const name of ["getClientRects", "getBoundingClientRect"]) {
    const descriptor = rangeGeometry[name];
    if (descriptor) Object.defineProperty(Range.prototype, name, descriptor);
    else Reflect.deleteProperty(Range.prototype, name);
  }
});

let uninstall = () => {};
beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {},
  }));
});
afterEach(() => {
  uninstall();
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function overlays() {
  return {
    palette: screen.queryByRole("dialog", { name: "Command palette" }) !== null,
    slash: document.querySelector("[data-notebook-editor] [role=listbox]") !== null,
  };
}
function press(key: string, modifiers: KeyboardEventInit = {}) {
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...modifiers });
}
function expectOwner(id: string) {
  const trace = readKeyboardOwnership().traces.at(-1);
  expect(trace?.eligible.map((owner) => owner.split("#")[0])).toEqual([id]);
  expect(trace?.delivered.map((owner) => owner.split("#")[0])).toEqual([id]);
}
async function mountSlashMenu(platform = "MacIntel") {
  vi.spyOn(navigator, "platform", "get").mockReturnValue(platform);
  const editorRef = createRef<Editor>();
  const { container } = render(<MemoryRouter>
    <NotebookEditor notebookId="escape-yield" editorRef={editorRef} />
    <CommandPalette />
  </MemoryRouter>);
  uninstall = installShortcuts(() => {});
  await waitFor(() => expect(container.querySelector("[data-hydrated=true]")).toBeTruthy());
  const editor = editorRef.current;
  if (!editor) throw new Error("Notebook editor did not mount");
  act(() => {
    editor.commands.insertContent("/");
    editor.view.dom.focus();
  });
  expect(overlays()).toEqual({ palette: false, slash: true });
  return editor;
}
async function openPalette(platform = "MacIntel") {
  press("k", platform === "MacIntel" ? { metaKey: true } : { ctrlKey: true });
  const input = within(screen.getByRole("dialog", { name: "Command palette" })).getByRole("textbox");
  await waitFor(() => expect(document.activeElement).toBe(input));
  expect(overlays()).toEqual({ palette: true, slash: true });
  return input;
}

describe("notebook slash menu yields to the command palette", () => {
  it.each([
    { platform: "MacIntel", lateSlash: false },
    { platform: "MacIntel", lateSlash: true },
    { platform: "Linux x86_64", lateSlash: false },
    { platform: "Linux x86_64", lateSlash: true },
  ])("$platform, late slash registration $lateSlash: each Escape closes one overlay", async ({ platform, lateSlash }) => {
    const editor = await mountSlashMenu(platform);
    await openPalette(platform);
    // A notebook update reinstalls the local listener after the palette's.
    if (lateSlash) act(() => { editor.commands.insertContent("h"); });
    const orderedOwners = readKeyboardOwnership().registrations
      .filter((owner) => ["palette.escape", "notebook.slash-menu"].includes(owner.id))
      .map((owner) => owner.id);
    expect(orderedOwners).toEqual(lateSlash
      ? ["palette.escape", "notebook.slash-menu"] : ["notebook.slash-menu", "palette.escape"]);
    press("Escape");
    expect(overlays(), "One Escape must not close both overlays").toEqual({ palette: false, slash: true });
    expectOwner("palette.escape");
    expect(document.activeElement).toBe(editor.view.dom);
    press("Escape");
    expect(overlays()).toEqual({ palette: false, slash: false });
    expectOwner("notebook.slash-menu");
  });

  it("keeps the slash menu while Escape clears the palette filter, then dismisses each in turn", async () => {
    await mountSlashMenu();
    const input = await openPalette();
    fireEvent.change(input, { target: { value: "no-matching-command" } });
    press("Escape");
    expect(overlays()).toEqual({ palette: true, slash: true });
    expect(input.getAttribute("value")).toBe("");
    expectOwner("palette.escape");
    press("Escape");
    expect(overlays()).toEqual({ palette: false, slash: true });
    expectOwner("palette.escape");
    press("Escape");
    expect(overlays()).toEqual({ palette: false, slash: false });
    expectOwner("notebook.slash-menu");
  });

  it("pauses slash navigation and Enter while the palette is open, then resumes the same selection", async () => {
    const editor = await mountSlashMenu();
    const selection = () => document.querySelector("[data-notebook-editor] [role=option][aria-selected=true]")?.textContent;
    press("ArrowDown");
    expect(selection()).toContain("Heading 2");
    const input = await openPalette();
    fireEvent.change(input, { target: { value: "no-matching-command" } });
    press("ArrowDown");
    press("ArrowUp");
    press("Enter");
    expect(overlays()).toEqual({ palette: true, slash: true });
    expect(selection()).toContain("Heading 2");
    expect(editor.getText()).toBe("/");
    press("Escape"); // Clear the filter first.
    press("Escape");
    press("ArrowUp");
    expect(selection()).toContain("Heading 1");
    expectOwner("notebook.slash-menu");
    press("Escape");
    expect(overlays()).toEqual({ palette: false, slash: false });
    expectOwner("notebook.slash-menu");
  });
});
