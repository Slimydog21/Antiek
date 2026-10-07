// Landing: these cases exercise the pane-flow arrangement, which is behind
// antiek.flag.pane.flow (default OFF). The flag is set before any import
// reads the keymap (vi.hoisted runs first).
vi.hoisted(() => { try { window.localStorage.setItem("antiek.flag.pane.flow", "on"); } catch { /* storage unavailable */ } });
import { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { useCallback, useState } from "react";
import { createPortal } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { prefixState } from "../components/hotkeys/prefixState";
import { ApiError } from "../lib/api";
import { SlashMenu } from "../modes/Notebook/SlashMenu";
import { escOverlayOpen } from "./escapeOverlay";
import { PanelLayout } from "./PanelLayout";
import { PaneFlowLayout } from "./PaneFlowLayout";
import { COMPANION_PANE, paneKey } from "./paneFlowGeometry";
import { installShortcuts } from "./shortcuts";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

const api = vi.hoisted(() => ({ read: vi.fn(), write: vi.fn() }));
vi.mock("../lib/api", async (original) => ({
  ...await original<typeof import("../lib/api")>(),
  getNotebookContent: api.read,
  apiFetch: api.write,
}));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));
vi.mock("./usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => true }));

// The real registry mounts NotebookEditor in a real docked PanelLayoutPanel.
// Its only supplied API result is a failed GET. The real SlashMenu is portalled
// into that panel with a separate local TipTap editor; this unit does not prove
// Notebook hydration, its slash trigger, persisted content, or native geometry.
function MenuFixture({ target, editor, query, onClose }: {
  target: HTMLElement;
  editor: Editor;
  query: string;
  onClose: () => void;
}) {
  const [open, setOpen] = useState(true);
  const close = useCallback(() => {
    onClose();
    setOpen(false);
  }, [onClose]);
  return open ? createPortal(<SlashMenu editor={editor} query={query} onClose={close} />, target) : null;
}

function node(selector: string): HTMLElement {
  const result = document.querySelector(selector);
  if (!(result instanceof HTMLElement)) throw new Error(`Missing actual host: ${selector}`);
  return result;
}

function press(target: HTMLElement, key: string, code: string, extra: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", {
    key, code, bubbles: true, cancelable: true, ctrlKey: true, altKey: true, ...extra,
  });
  act(() => { target.dispatchEvent(event); });
  return event;
}

function presentation() {
  const state = useWorkspace.getState();
  return {
    order: state.paneOrder.map(paneKey), arrangement: state.paneArrangement,
    zoom: state.paneZoom, focus: state.paneFocus, fullscreen: state.fullscreenPane,
  };
}

const editors: Editor[] = [];
const removals: (() => void)[] = [];
let uninstall: (() => void) | null = null;

beforeEach(() => {
  disablePersistence();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  useWorkspace.getState().setPaneArrangement("horizontal");
  prefixState.disarm();
  api.read.mockRejectedValue(new ApiError("F1 control: notebook unavailable", 503, ""));
  api.write.mockRejectedValue(new TypeError("Unexpected API write in F1 ownership control"));
  vi.spyOn(Element.prototype, "clientWidth", "get").mockImplementation(() => 1000);
  vi.spyOn(Element.prototype, "clientHeight", "get").mockImplementation(() => 700);
  vi.spyOn(Element.prototype, "getClientRects").mockImplementation(function (this: Element): DOMRectList {
    if (!this.isConnected || this.closest("[hidden], [inert]")) {
      return { length: 0, item: () => null, *[Symbol.iterator]() {} };
    }
    const rect = new DOMRect(0, 0, 1000, 700);
    return { 0: rect, length: 1, item: (index) => index === 0 ? rect : null,
      *[Symbol.iterator]() { yield rect; } };
  });
  vi.stubGlobal("ResizeObserver", class implements ResizeObserver {
    constructor(private callback: ResizeObserverCallback) {}
    observe(target: Element) {
      const size = { inlineSize: 1000, blockSize: 700 };
      this.callback([{ target, contentRect: new DOMRect(0, 0, 1000, 700),
        borderBoxSize: [size], contentBoxSize: [size], devicePixelContentBoxSize: [size] }], this);
    }
    unobserve() {}
    disconnect() {}
  });
});

afterEach(() => {
  uninstall?.(); uninstall = null;
  for (const remove of removals.splice(0)) remove();
  cleanup();
  for (const editor of editors.splice(0)) editor.destroy();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  prefixState.disarm();
  api.read.mockReset(); api.write.mockReset();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

async function mountDockedHost() {
  useWorkspace.getState().open("NotebookEditor", { notebookId: "f1:failed-notebook-control" }, {
    id: "f1:actual-docked-host", mode: "docked-right", title: "F1 notebook host",
  });
  render(<PaneFlowLayout><PanelLayout mainSlot={<button>Core control</button>} /></PaneFlowLayout>);
  const panel = screen.getByRole("region", { name: "F1 notebook host" });
  await within(panel).findByRole("alert");
  expect(api.read).toHaveBeenCalledWith("f1:failed-notebook-control");
  expect(panel.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("false");
  expect(api.write).not.toHaveBeenCalled();
  const companion = node('[data-pane-host="companion"]');
  const core = node('[data-pane-host="core"]');
  expect(panel.closest("[data-pane-host]")).toBe(companion);
  expect(useWorkspace.getState().panels["f1:actual-docked-host"].kind).toBe("NotebookEditor");
  uninstall = installShortcuts(() => {});
  // Successful actual dispatch before the menu proves connected host admission.
  act(() => { companion.focus(); });
  expect(press(companion, "ArrowLeft", "ArrowLeft").defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(core);
  expect(press(core, "ArrowRight", "ArrowRight").defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(companion);
  return { panel, companion, core };
}

function mountMenu(target: HTMLElement, query = "heading", onClose = vi.fn()) {
  const editor = new Editor({ extensions: [StarterKit], content: "<p>/</p>" });
  editors.push(editor);
  const result = render(<MenuFixture target={target} editor={editor} query={query} onClose={onClose} />);
  return { ...result, editor, onClose,
    query: (next: string) => result.rerender(<MenuFixture target={target} editor={editor} query={next} onClose={onClose} />) };
}

function observeDocumentEscape() {
  const observations: { prevented: boolean; zoom: ReturnType<typeof presentation>["zoom"] }[] = [];
  const observer = (event: KeyboardEvent) => {
    if (event.key === "Escape") observations.push({ prevented: event.defaultPrevented, zoom: presentation().zoom });
  };
  document.addEventListener("keydown", observer);
  removals.push(() => document.removeEventListener("keydown", observer));
  return observations;
}

describe("F1 real SlashMenu in the registered docked host (source controls, NOT_RUN)", () => {
  it("refuses focus, reorder, L and F from an actual focused option and admits focus after cleanup", async () => {
    const { panel, companion, core } = await mountDockedHost();
    const menu = mountMenu(panel);
    const option = within(panel).getByRole("option", { name: /Heading 1/ });
    const popup = within(panel).getByRole("listbox");
    expect(popup.hasAttribute("data-esc-overlay")).toBe(true);
    expect(option.closest("[data-pane-host]")).toBe(companion);
    act(() => { option.focus(); });
    const before = presentation();
    const content = menu.editor.getJSON();
    for (const [key, code, shiftKey] of [
      ["ArrowLeft", "ArrowLeft", false], ["ArrowRight", "ArrowRight", false],
      ["ArrowLeft", "ArrowLeft", true], ["ArrowRight", "ArrowRight", true],
      ["l", "KeyL", false], ["f", "KeyF", false],
    ] as const) {
      expect(press(option, key, code, { shiftKey }).defaultPrevented).toBe(false);
      expect(presentation()).toEqual(before);
      expect(document.activeElement).toBe(option);
    }
    expect(menu.editor.getJSON()).toEqual(content);
    expect(menu.onClose).not.toHaveBeenCalled();
    expect(press(option, "Escape", "Escape", { ctrlKey: false, altKey: false }).defaultPrevented).toBe(true);
    expect(menu.onClose).toHaveBeenCalledTimes(1);
    expect(within(panel).queryByRole("listbox")).toBeNull();
    expect(escOverlayOpen(document)).toBe(false);
    act(() => { companion.focus(); });
    expect(press(companion, "ArrowLeft", "ArrowLeft").defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(core);
  });

  it("lets the positive menu close at window bubble before a later eligible Escape restores", async () => {
    const { panel, companion } = await mountDockedHost();
    expect(press(companion, "f", "KeyF").defaultPrevented).toBe(true);
    expect(presentation().zoom).toEqual(COMPANION_PANE);
    const atLocalClose = vi.fn(() => presentation().zoom);
    const menu = mountMenu(panel, "heading", atLocalClose);
    const observations = observeDocumentEscape();
    const option = within(panel).getByRole("option", { name: /Heading 1/ });
    act(() => { option.focus(); });
    const escape = press(option, "Escape", "Escape", { ctrlKey: false, altKey: false });
    expect(observations).toEqual([{ prevented: false, zoom: COMPANION_PANE }]);
    expect(atLocalClose.mock.results[0]?.value).toEqual(COMPANION_PANE);
    expect(escape.defaultPrevented).toBe(true);
    expect(presentation().zoom).toEqual(COMPANION_PANE);
    expect(within(panel).queryByRole("listbox")).toBeNull();
    expect(escOverlayOpen(document)).toBe(false);
    expect(menu.editor.getJSON().content?.[0]?.type).toBe("paragraph");
    act(() => { companion.focus(); });
    press(companion, "Escape", "Escape", { ctrlKey: false, altKey: false });
    expect(presentation().zoom).toBeNull();
    expect(atLocalClose).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(companion);
  });

  it("keeps a filtered-empty menu's local arrows, no-choice Enter and first Escape while restoring only after unmount", async () => {
    const { panel, companion } = await mountDockedHost();
    press(companion, "f", "KeyF");
    expect(presentation().zoom).toEqual(COMPANION_PANE);
    const atLocalClose = vi.fn(() => presentation().zoom);
    const menu = mountMenu(panel, "heading", atLocalClose);
    menu.query("no-slash-entry-matches-this-control");
    expect(within(panel).queryByRole("listbox")).toBeNull();
    expect(panel.querySelector("[data-esc-overlay]")).toBeNull();
    expect(escOverlayOpen(document)).toBe(true);
    act(() => { companion.focus(); });
    const content = menu.editor.getJSON();
    for (const key of ["ArrowUp", "ArrowDown"]) {
      expect(press(companion, key, key, { ctrlKey: false, altKey: false }).defaultPrevented).toBe(true);
      expect(presentation().zoom).toEqual(COMPANION_PANE);
    }
    expect(press(companion, "Enter", "Enter", { ctrlKey: false, altKey: false }).defaultPrevented).toBe(false);
    expect(menu.editor.getJSON()).toEqual(content);
    expect(atLocalClose).not.toHaveBeenCalled();
    const observations = observeDocumentEscape();
    expect(press(companion, "Escape", "Escape", { ctrlKey: false, altKey: false }).defaultPrevented).toBe(true);
    expect(observations).toEqual([{ prevented: false, zoom: COMPANION_PANE }]);
    expect(atLocalClose.mock.results[0]?.value).toEqual(COMPANION_PANE);
    expect(presentation().zoom).toEqual(COMPANION_PANE);
    expect(atLocalClose).toHaveBeenCalledTimes(1);
    expect(escOverlayOpen(document)).toBe(false);
    press(companion, "Escape", "Escape", { ctrlKey: false, altKey: false });
    expect(presentation().zoom).toBeNull();
    expect(atLocalClose).toHaveBeenCalledTimes(1);
    expect(api.write).not.toHaveBeenCalled();
  });
});
