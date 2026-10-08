import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LemonModal } from "../components/lemon/LemonModal";
import { PanelLayout } from "./PanelLayout";
import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { readKeyboardOwnership } from "./keyboardOwnership";

// The real panel frame, title, store and Escape owners remain mounted. No book,
// provider, reader or persisted document is supplied by this mechanical fixture.
vi.mock("./PanelRegistry", () => ({ PanelRegistry: { Notes: () => null } }));
vi.mock("./RightPaneForMode", () => ({ default: () => null }));
vi.mock("./DocumentTabStrip", () => ({ DocumentTabStrip: () => null }));
vi.mock("./ProjectTreeOverlay", () => ({ default: () => null }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));

const state = () => useWorkspace.getState();
const originalClose = state().close;
const closeCalls: string[] = [];

beforeEach(() => {
  disablePersistence();
  useWorkspace.setState({ close: originalClose });
  state().reset();
  closeCalls.length = 0;
  useWorkspace.setState({ close: (id) => { closeCalls.push(id); originalClose(id); } });
  vi.stubGlobal("matchMedia", () => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
});

afterEach(() => {
  cleanup();
  useWorkspace.setState({ close: originalClose });
  state().reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function title(id = "a") {
  return screen.getByRole("group", { name: `Panel ${id} — panel controls` });
}

function mount(ids = ["a"]) {
  for (const id of ids) state().open("Notes", {}, { id, title: `Panel ${id}`, mode: "floating" });
  const view = render(<>{ids.map((id) => <PanelLayoutPanel key={id} id={id} />)}</>);
  const strip = title(ids[0]);
  const root = screen.getByRole("region", { name: `Panel ${ids[0]}` });
  act(() => strip.focus());
  expect(document.activeElement).toBe(strip);
  expect(state().focusedPanelId).toBe(ids[0]);
  return { view, strip, root };
}

function key(options: KeyboardEventInit = {}) {
  return new KeyboardEvent("keydown", {
    key: "Escape", bubbles: true, cancelable: true, ...options,
  });
}

function dispatch(target: EventTarget, event = key()) {
  act(() => { target.dispatchEvent(event); });
  return event;
}

function kept(event: KeyboardEvent) {
  expect(event.defaultPrevented).toBe(false);
  expect(closeCalls).toEqual([]);
  expect(state().panels.a).toBeDefined();
}

describe("floating panel Escape ownership", () => {
  it.each(["title", "control"])("closes exactly once from the genuinely focused %s", (origin) => {
    const { strip, root } = mount();
    const target = origin === "title" ? strip : within(root).getByRole("button", { name: "Pin" });
    act(() => target.focus());
    expect(document.activeElement).toBe(target);
    expect(dispatch(target).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
    expect(state().panels.a).toBeUndefined();
  });

  it("refuses a body-origin key even while the panel title is focused", () => {
    mount();
    kept(dispatch(document.body));
  });

  it("refuses a sibling panel target while only the store still names this panel", () => {
    mount(["a", "b"]);
    const sibling = title("b"), event = key();
    act(() => {
      sibling.focus();
      useWorkspace.setState({ focusedPanelId: "a" });
      sibling.dispatchEvent(event);
    });
    expect(document.activeElement).toBe(sibling);
    kept(event);
    expect(state().panels.b).toBeDefined();
  });

  it("requires actual panel focus even for a connected panel-owned event target", () => {
    const { strip } = mount();
    const outside = document.createElement("button");
    document.body.append(outside);
    try {
      act(() => outside.focus());
      expect(document.activeElement).toBe(outside);
      kept(dispatch(strip));
    } finally {
      outside.remove();
    }
  });

  it("refuses a different control within the panel when it does not own actual focus", () => {
    const { strip, root } = mount();
    const pin = within(root).getByRole("button", { name: "Pin" });
    expect(document.activeElement).toBe(strip);
    kept(dispatch(pin));
  });

  it("admits a descendant event of the actual focused control", () => {
    const { root } = mount();
    const control = document.createElement("button"), child = document.createElement("span");
    control.append(child); root.append(control);
    act(() => control.focus());
    expect(document.activeElement).toBe(control);
    expect(dispatch(child).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
  });

  it("does not close for a detached target or detached rendered root", () => {
    const { strip, root } = mount();
    const parent = root.parentNode, next = root.nextSibling;
    if (!parent) throw new Error("No connected panel parent");
    try {
      root.remove();
      kept(dispatch(strip));
      kept(dispatch(document.body));
    } finally {
      parent.insertBefore(root, next);
    }
  });

  it.each(["focus", "mode", "membership"])("rechecks current %s before React commits the retirement", (retirement) => {
    const { strip } = mount(), event = key();
    act(() => {
      if (retirement === "focus") useWorkspace.setState({ focusedPanelId: null });
      else if (retirement === "mode") state().setMode("a", "docked-left");
      else originalClose("a");
      strip.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(false);
    expect(closeCalls).toEqual([]);
    if (retirement === "membership") expect(state().panels.a).toBeUndefined();
    else expect(state().panels.a).toBeDefined();
  });

  it("does not consume a second same-batch key after the first closes its member", () => {
    const { strip } = mount(), first = key(), second = key();
    act(() => { strip.dispatchEvent(first); strip.dispatchEvent(second); });
    expect(first.defaultPrevented).toBe(true);
    expect(second.defaultPrevented).toBe(false);
    expect(closeCalls).toEqual(["a"]);
  });

  it.each([
    { ctrlKey: true }, { metaKey: true }, { altKey: true },
    { shiftKey: true }, { isComposing: true },
  ])("leaves modified or composing Escape %j unconsumed", (options) => {
    const { strip } = mount();
    kept(dispatch(strip, key(options)));
  });

  it("leaves consumed and AltGraph keys to their existing owner", () => {
    const { strip } = mount(), consumed = key(), altGraph = key();
    consumed.preventDefault();
    dispatch(strip, consumed);
    expect(consumed.defaultPrevented).toBe(true);
    expect(closeCalls).toEqual([]);
    Object.defineProperty(altGraph, "getModifierState", { value: (name: string) => name === "AltGraph" });
    kept(dispatch(strip, altGraph));
  });

  it.each(["hidden", "aria-hidden", "inert"])("refuses %s on roots, ancestors and targets", (attribute) => {
    const { view, strip, root } = mount();
    for (const node of [root, view.container, strip]) {
      node.setAttribute(attribute, attribute === "aria-hidden" ? "true" : "");
      kept(dispatch(strip));
      node.removeAttribute(attribute);
    }
  });

  it.each(["input", "textarea", "select"])("leaves a focused %s editable control unconsumed", (tag) => {
    const { root } = mount(), control = document.createElement(tag);
    root.append(control);
    act(() => control.focus());
    expect(document.activeElement).toBe(control);
    kept(dispatch(control));
  });

  it.each(["", "true", "plaintext-only"])("honors inherited contenteditable=%s", (value) => {
    const { root } = mount(), editor = document.createElement("div"), child = document.createElement("span");
    editor.setAttribute("contenteditable", value); child.tabIndex = 0;
    editor.append(child); root.append(editor);
    act(() => child.focus());
    expect(document.activeElement).toBe(child);
    kept(dispatch(child));
  });

  it("inherits editing past an invalid contenteditable attribute", () => {
    const { root } = mount(), editor = document.createElement("div"), child = document.createElement("span");
    editor.setAttribute("contenteditable", "true"); child.setAttribute("contenteditable", "invalid"); child.tabIndex = 0;
    editor.append(child); root.append(editor);
    act(() => child.focus());
    kept(dispatch(child));
  });

  it("admits an explicit noneditable focused child inside an editor", () => {
    const { root } = mount(), editor = document.createElement("div"), control = document.createElement("button");
    editor.setAttribute("contenteditable", "true"); control.setAttribute("contenteditable", "false");
    editor.append(control); root.append(editor);
    act(() => control.focus());
    expect(document.activeElement).toBe(control);
    expect(dispatch(control).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
  });

  it("keeps the actual focused editor authoritative for a noneditable decorative descendant event", () => {
    const { root } = mount(), editor = document.createElement("div"), child = document.createElement("span");
    editor.setAttribute("contenteditable", "true"); editor.tabIndex = 0;
    child.setAttribute("contenteditable", "false");
    editor.append(child); root.append(editor);
    act(() => editor.focus());
    expect(document.activeElement).toBe(editor);
    kept(dispatch(child));
  });

  it("lets the real child menu own the first Escape", () => {
    const { root } = mount();
    fireEvent.click(within(root).getByRole("button", { name: "Panel actions" }));
    const item = screen.getAllByRole("menuitem")[0];
    act(() => item.focus());
    expect(dispatch(item).defaultPrevented).toBe(true);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(closeCalls).toEqual([]);
    expect(state().panels.a).toBeDefined();
    act(() => title().focus());
    expect(dispatch(title()).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
  });

  it.each(["menu", "listbox", "dialog"])("defers to a child %s marker even before it consumes the key", (role) => {
    const { root } = mount(), overlay = document.createElement("div");
    overlay.setAttribute("role", role); overlay.setAttribute("data-esc-overlay", ""); overlay.tabIndex = 0;
    root.append(overlay);
    act(() => overlay.focus());
    kept(dispatch(overlay));
  });

  it("lets the actual top modal own Escape even if panel focus is forced", () => {
    const { strip } = mount();
    function ModalOwner() {
      const [open, setOpen] = useState(true);
      return <LemonModal open={open} title="Escape owner" onClose={() => setOpen(false)}><button>Modal control</button></LemonModal>;
    }
    render(<ModalOwner />);
    act(() => strip.focus());
    expect(document.activeElement).toBe(strip);
    expect(dispatch(strip).defaultPrevented).toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(closeCalls).toEqual([]);
    expect(state().panels.a).toBeDefined();
    expect(dispatch(strip).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
  });

  // REWRITTEN at landing (pane-flow packet → main): main registers the panel's
  // Escape through workspace/keyboardOwnership.ts, which wraps the handler and
  // (in dev) adds one shared capture observer, so a raw window.addEventListener
  // spy no longer sees the panel's own listener. The contract is the same —
  // exactly one admitted owner while the floating panel is focused, none after
  // it retires — asserted through the seam's registry instead.
  it.each(["unmount", "focus", "mode"])("retires the exact admitted Escape owner after %s", (retirement) => {
    const owners = () => readKeyboardOwnership().registrations.filter((r) => r.id === "panel.floating.escape");
    const { view } = mount();
    expect(owners()).toHaveLength(1);
    if (retirement === "unmount") view.unmount();
    else act(() => {
      if (retirement === "focus") useWorkspace.setState({ focusedPanelId: null });
      else state().setMode("a", "docked-left");
    });
    expect(owners()).toHaveLength(0);
    kept(dispatch(document.body));
  });

  it("preserves the actual fullscreen owner until the next key after panel close", () => {
    state().setLayoutPreset("omarchy-inset");
    state().open("Notes", {}, { id: "a", title: "Panel a", mode: "floating" });
    render(<PanelLayout mainSlot={<button>Main control</button>} />);
    act(() => { state().setFullscreenPane("left"); title().focus(); });
    expect(document.activeElement).toBe(title());
    expect(dispatch(title()).defaultPrevented).toBe(true);
    expect(closeCalls).toEqual(["a"]);
    expect(state().panels.a).toBeUndefined();
    expect(state().fullscreenPane).toBe("left");
    // REWRITTEN at landing: main's fullscreen Escape owner (PanelLayout,
    // id pane.fullscreen.escape) restores the panes without claiming the
    // event (no preventDefault), so the contract asserted here is the
    // restore itself — the next Escape after the close restores fullscreen,
    // and the close is not repeated (S04: the actual focused host owns F/Esc).
    dispatch(document.body);
    expect(state().fullscreenPane).toBeNull();
    expect(closeCalls).toEqual(["a"]);
  });
});
