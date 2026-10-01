import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { LemonModal } from "../components/lemon/LemonModal";
import ThreadIsland from "../modes/Reading/island/ThreadIsland";
import type { IslandThreadState } from "../modes/Reading/island/useIslandThread";
import { WorkspaceWindow } from "../components/windows/WorkspaceWindow";
import { installShortcuts } from "./shortcuts";
import { useWindows } from "./windowsStore";
import { useWorkspace } from "./WorkspaceStore";

vi.mock("../modes/Reading/island/useIslandThread", () => ({ useIslandThread: () => thread }));
const thread: IslandThreadState = {
  status: "complete", costTotal: 0, question: "A real thread", family: [], loading: false,
  outcomeLoading: false, sessionState: null, retry: null, refetchFamily: vi.fn(),
  outcome: { insights: [], questions: [] },
};

const state = () => useWindows.getState();
let uninstall = () => {};
beforeEach(() => {
  state().reset(); useWorkspace.getState().reset();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  uninstall = installShortcuts(vi.fn());
});
afterEach(() => { uninstall(); cleanup(); vi.unstubAllGlobals(); });
function frame(id: string) { return screen.getByRole("dialog", { name: id }); }
function press(target: EventTarget, key = "[", options: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, metaKey: true, bubbles: true, cancelable: true, ...options });
  act(() => { target.dispatchEvent(event); });
  return event;
}
async function mount(ids = ["a", "b", "c"]) {
  for (const id of ids) state().open("subaction", { opaque: id }, { id, title: id });
  const view = render(<>{ids.map((id) => <WorkspaceWindow key={id} id={id}><input aria-label={`Draft ${id}`} defaultValue={`Kept ${id}`} /><button>Child {id}</button></WorkspaceWindow>)}</>);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  act(() => { frame(ids[ids.length - 1]).focus(); });
  return view;
}

describe("actual product window cycle", () => {
  it("cycles all three actual window roots backward despite z-order restacking", async () => {
    await mount();
    for (const id of ["b", "a", "c", "b"]) {
      const event = press(document.activeElement ?? document);
      expect(state().focusedId).toBe(id);
      expect(document.activeElement).toBe(frame(id));
      expect(event.defaultPrevented).toBe(true);
    }
  });
  it("advances two same-batch presses from the current store cursor", async () => {
    await mount(); const origin = frame("c");
    act(() => { press(origin); press(origin, "[", { repeat: true }); });
    expect(state().focusedId).toBe("a");
    expect(document.activeElement).toBe(frame("a"));
  });
  it("never falls through to panels from an actual product child button", async () => {
    await mount(); const ws = useWorkspace.getState();
    act(() => { ws.open("Notes", {}, { id: "left", mode: "docked-left" }); ws.open("Notes", {}, { id: "right", mode: "docked-right" }); ws.focus("left"); });
    const child = screen.getByRole("button", { name: "Child c" }); act(() => { child.focus(); });
    const event = press(child);
    expect(useWorkspace.getState().focusedPanelId).toBe("left");
    expect(state().focusedId).toBe("c");
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("window cycle ownership and retention", () => {
  it("cycles four windows forward and supports two same-batch forward presses", async () => {
    await mount(["a", "b", "c", "d"]);
    for (const id of ["a", "b", "c", "d"]) {
      press(document.activeElement ?? document, "]");
      expect(state().focusedId).toBe(id); expect(document.activeElement).toBe(frame(id));
    }
    const origin = frame("d");
    act(() => { press(origin, "]"); press(origin, "]", { repeat: true }); });
    expect(state().focusedId).toBe("b"); expect(document.activeElement).toBe(frame("b"));
  });
  it("accepts the actual titlebar and document fallback while preserving mounted drafts and mode/geometry", async () => {
    await mount();
    const node = frame("c"), input = screen.getByRole("textbox", { name: "Draft c" });
    fireEvent.change(input, { target: { value: "Unsubmitted draft" } });
    act(() => { state().expand("c"); });
    const before = state().windows.c;
    const bar = node.querySelector("[data-window-titlebar]");
    if (!(bar instanceof HTMLElement)) throw new Error("Missing actual chrome");
    act(() => { bar.focus(); });
    press(bar); press(document, "]");
    expect(frame("c")).toBe(node); expect(screen.getByRole("textbox", { name: "Draft c" })).toBe(input);
    expect(input).toHaveProperty("value", "Unsubmitted draft");
    expect(state().windows.c).toMatchObject({ rect: before.rect, mode: before.mode, payload: before.payload });
  });
  it("keeps panels isolated while cycling frames, and windows isolated outside a frame", async () => {
    await mount(); const ws = useWorkspace.getState();
    act(() => { ws.open("Notes", {}, { id: "left", mode: "docked-left" }); ws.open("Notes", {}, { id: "right", mode: "docked-right" }); ws.focus("left"); });
    press(frame("c")); expect(state().focusedId).toBe("b"); expect(useWorkspace.getState().focusedPanelId).toBe("left");
    const outside = document.createElement("button"); document.body.appendChild(outside); outside.focus();
    press(outside); expect(useWorkspace.getState().focusedPanelId).toBe("right"); expect(state().focusedId).toBe("b");
    outside.remove();
  });
  it.each(["input", "textarea", "select", "contenteditable", "button"])("refuses native %s descendants without panel fallback", async (kind) => {
    await mount();
    const el = document.createElement(kind === "contenteditable" ? "div" : kind);
    if (kind === "contenteditable") { el.setAttribute("contenteditable", "true"); el.tabIndex = 0; }
    frame("c").appendChild(el); act(() => { el.focus(); });
    expect(document.activeElement).toBe(el);
    const event = press(el); expect(event.defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
  });
  it.each([{ isComposing: true }, { altKey: true }, { shiftKey: true }, { ctrlKey: true }])("refuses composing and extra modifiers %j", async (options) => {
    await mount(); const event = press(frame("c"), "[", options);
    expect(event.defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
  });
  it("accepts the existing Ctrl bracket binding without Meta", async () => {
    await mount(); press(frame("c"), "[", { metaKey: false, ctrlKey: true }); expect(state().focusedId).toBe("b");
  });
  it("refuses consumed and reported AltGraph events even without Alt flags", async () => {
    await mount();
    for (const kind of ["consumed", "altGraph"]) {
      const event = new KeyboardEvent("keydown", { key: "[", metaKey: true, bubbles: true, cancelable: true });
      if (kind === "consumed") event.preventDefault();
      else Object.defineProperty(event, "getModifierState", { value: (key: string) => key === "AltGraph" });
      act(() => { frame("c").dispatchEvent(event); });
      expect(state().focusedId).toBe("c");
      expect(event.defaultPrevented).toBe(kind === "consumed");
    }
  });
  it.each(["hidden", "aria-hidden", "inert"])("refuses %s frame ancestry", async (attribute) => {
    await mount(); const current = frame("c"); current.setAttribute(attribute, attribute === "aria-hidden" ? "true" : "");
    const event = press(current); expect(event.defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
  });
  it("refuses stale targets, unsupported frame IDs and disconnected origins", async () => {
    const view = await mount(); const stale = frame("b");
    expect(press(stale).defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
    const current = frame("c"); current.setAttribute("data-workspace-window", "missing");
    expect(press(current).defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
    view.unmount(); const afterUnmount = state().focusedId;
    expect(current.isConnected).toBe(false);
    expect(press(current).defaultPrevented).toBe(false); expect(state().focusedId).toBe(afterUnmount);
  });
  it("refuses a real top modal even if focus is forced back to frame chrome", async () => {
    await mount(); render(<LemonModal open title="Confirmation" onClose={() => {}}><input aria-label="Modal field" /></LemonModal>);
    act(() => { frame("c").focus(); });
    expect(press(frame("c")).defaultPrevented).toBe(false); expect(state().focusedId).toBe("c");
  });
  it("a real nested island and Dig deeper form retain ownership; only its own frame is blocked", async () => {
    state().open("reader", {}, { id: "a", title: "a" }); state().open("reader", {}, { id: "b", title: "b" });
    render(<MemoryRouter><WorkspaceWindow id="a"><ThreadIsland anchorId="anchor" documentId="doc" investigationId="inv" servable passageQuote="Allowed quote" pageIndexHint={0} /></WorkspaceWindow><WorkspaceWindow id="b"><div>Other product</div></WorkspaceWindow></MemoryRouter>);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const dismiss = screen.getByRole("button", { name: "Dismiss the island" });
    expect(press(dismiss).defaultPrevented).toBe(false); expect(state().focusedId).toBe("a");
    fireEvent.click(screen.getByRole("button", { name: "Dig deeper" }));
    const input = screen.getByRole("textbox", { name: "What do you want to find out?" });
    expect(press(input).defaultPrevented).toBe(false); expect(state().focusedId).toBe("a");
    act(() => { frame("a").focus(); });
    expect(press(frame("a")).defaultPrevented).toBe(false); expect(state().focusedId).toBe("a");
    act(() => { frame("b").focus(); });
    expect(press(frame("b")).defaultPrevented).toBe(true); expect(state().focusedId).toBe("a");
    expect(screen.getByRole("textbox", { name: "What do you want to find out?" })).toBe(input);
  });
  it("does not consume single-window cycling and uninstalls the one dispatcher", async () => {
    await mount(["a"]); expect(press(frame("a")).defaultPrevented).toBe(false);
    act(() => { state().open("subaction", {}, { id: "b" }); });
    uninstall(); expect(press(frame("a")).defaultPrevented).toBe(false); expect(state().focusedId).toBe("b");
  });
});


describe("opaque DOM window identity", () => {
  it("can enter and leave a real mounted empty-ID window in the cycle ring", async () => {
    await mount(["", "b", "c"]);
    press(frame("c")); expect(state().focusedId).toBe("b");
    press(frame("b")); expect(state().focusedId).toBe("");
    expect(document.activeElement).toBe(frame(""));
    const leave = press(frame(""));
    expect(state().focusedId).toBe("c"); expect(document.activeElement).toBe(frame("c"));
    expect(leave.defaultPrevented).toBe(true);
    expect(state().cycleOrder).toEqual(["", "b", "c"]);
  });
  it("refuses a connected foreign frame marker naming an inherited Record key", async () => {
    await mount();
    render(<div data-workspace-window="toString" tabIndex={0} aria-label="Foreign marker" role="region" />);
    const foreign = screen.getByRole("region", { name: "Foreign marker" });
    act(() => { foreign.focus(); });
    const before = state(); const event = press(foreign);
    expect(state()).toBe(before);
    expect(document.activeElement).toBe(foreign);
    expect(event.defaultPrevented).toBe(false);
  });
});
