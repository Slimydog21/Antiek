import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { LemonModal } from "../components/lemon/LemonModal";
import { PanelHandle } from "./PanelHandle";
import { panelFocusId } from "./panelFocusId";
import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";

vi.mock("./PanelRegistry", () => ({ PanelRegistry: { Notes: () => <input aria-label="Hosted draft" defaultValue="Kept draft" /> } }));
const state = () => useWorkspace.getState();
beforeEach(() => {
  disablePersistence(); state().reset();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("innerWidth", 1000); vi.stubGlobal("innerHeight", 800);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function title(id: string): HTMLElement {
  const span = within(screen.getByRole("region", { name: id })).getByText(id);
  if (!span.parentElement) throw new Error("No actual title strip");
  return span.parentElement;
}
function mount(ids = ["a"]) {
  for (const id of ids) state().open("Notes", {}, { id, title: id, mode: "floating" });
  return render(<>{ids.map((id) => <PanelLayoutPanel key={id} id={id} />)}</>);
}

describe("actual panel title keyboard", () => {
  it("provides a focusable title that synchronizes current store focus", () => {
    mount(["a", "b"]); const strip = title("a"); act(() => { strip.focus(); });
    expect(document.activeElement).toBe(strip); expect(state().focusedPanelId).toBe("a");
  });
  it("moves 24px per same-batch arrow on the actual focused title", () => {
    mount(); const strip = title("a"), before = state().panels.a.rect; act(() => { strip.focus(); });
    act(() => { fireEvent.keyDown(strip, { key: "ArrowRight" }); fireEvent.keyDown(strip, { key: "ArrowRight", repeat: true }); });
    expect(state().panels.a.rect.x).toBe(before.x + 48);
  });
  it("resizes with Shift and arrows without moving", () => {
    mount(); const strip = title("a"), before = state().panels.a.rect; act(() => { strip.focus(); });
    fireEvent.keyDown(strip, { key: "ArrowDown", shiftKey: true });
    expect(state().panels.a.rect).toEqual({ ...before, height: before.height + 24 });
  });
});


describe("title admission and retained panel behavior", () => {
  it("focuses a floating title once and retains its actual input/node/draft through geometry updates", () => {
    mount(["a", "b"]); const strip = title("a"), input = within(screen.getByRole("region", { name: "a" })).getByRole("textbox");
    fireEvent.change(input, { target: { value: "Local draft" } }); const before = state().zCounter;
    act(() => { strip.focus(); }); expect(state().zCounter).toBe(before + 1);
    const focusedZ = state().zCounter;
    fireEvent.keyDown(strip, { key: "ArrowLeft" }); fireEvent.keyDown(strip, { key: "ArrowUp", shiftKey: true });
    expect(state().zCounter).toBe(focusedZ); expect(title("a")).toBe(strip);
    expect(within(screen.getByRole("region", { name: "a" })).getByRole("textbox")).toBe(input);
    expect(input).toHaveProperty("value", "Local draft");
  });
  it("clamps movement to the inherited viewport bounds and resize to 240 by 160", () => {
    mount(); const strip = title("a"); act(() => { strip.focus(); state().setRect("a", { x: 919, y: 719, width: 241, height: 161 }); });
    fireEvent.keyDown(strip, { key: "ArrowRight" }); fireEvent.keyDown(strip, { key: "ArrowDown" });
    expect(state().panels.a.rect).toEqual({ x: 920, y: 720, width: 241, height: 161 });
    fireEvent.keyDown(strip, { key: "ArrowLeft", shiftKey: true }); fireEvent.keyDown(strip, { key: "ArrowUp", shiftKey: true });
    expect(state().panels.a.rect).toEqual({ x: 920, y: 720, width: 240, height: 160 });
    act(() => { state().setRect("a", { x: -159, y: 1 }); });
    fireEvent.keyDown(strip, { key: "ArrowLeft" }); fireEvent.keyDown(strip, { key: "ArrowUp" });
    expect(state().panels.a.rect.x).toBe(-160); expect(state().panels.a.rect.y).toBe(0);
  });
  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { isComposing: true }])("refuses %j and leaves geometry unchanged", (options) => {
    mount(); const strip = title("a"); act(() => { strip.focus(); }); const before = state();
    expect(fireEvent.keyDown(strip, { key: "ArrowRight", ...options })).toBe(true); expect(state()).toBe(before);
  });
  it("refuses consumed/AltGraph, disconnected and stale unfocused titles", () => {
    const view = mount(["a", "b"]); const strip = title("a"); act(() => { strip.focus(); });
    for (const consumed of [true, false]) {
      const e = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
      if (consumed) e.preventDefault(); else Object.defineProperty(e, "getModifierState", { value: (key: string) => key === "AltGraph" });
      const before = state(); fireEvent(strip, e); expect(state()).toBe(before);
    }
    const before = state(); fireEvent.keyDown(title("b"), { key: "ArrowRight" }); expect(state()).toBe(before);
    view.unmount(); fireEvent.keyDown(strip, { key: "ArrowRight" }); expect(state()).toBe(before);
  });
  it.each(["hidden", "aria-hidden", "inert"])("refuses %s ancestry", (attribute) => {
    mount(); const strip = title("a"); act(() => { strip.focus(); }); const before = state();
    screen.getByRole("region", { name: "a" }).setAttribute(attribute, attribute === "aria-hidden" ? "true" : "");
    expect(fireEvent.keyDown(strip, { key: "ArrowRight" })).toBe(true); expect(state()).toBe(before);
  });
  it("keeps input/button arrows native and does not add Enter/fullscreen commands", () => {
    mount(); const strip = title("a"), input = screen.getByRole("textbox"), pin = screen.getByRole("button", { name: "Pin" });
    for (const target of [input, pin]) { act(() => { target.focus(); }); const before = state(); expect(fireEvent.keyDown(target, { key: "ArrowRight" })).toBe(true); expect(state()).toBe(before); }
    act(() => { strip.focus(); }); const before = state(); fireEvent.keyDown(strip, { key: "Enter" }); fireEvent.keyDown(strip, { key: "f" }); expect(state()).toBe(before);
  });
  it("retains named entry in docked mode and refuses unavailable move/resize capabilities", () => {
    state().open("Notes", {}, { id: "a", title: "a", mode: "floating" });
    const view = render(<PanelHandle id="a" draggable={false} resizable={false} />);
    const strip = screen.getByRole("group", { name: "a — panel controls" }); act(() => { strip.focus(); }); const before = state();
    expect(strip.getAttribute("aria-keyshortcuts")).toBeNull(); fireEvent.keyDown(strip, { key: "ArrowRight" }); fireEvent.keyDown(strip, { key: "ArrowDown", shiftKey: true }); expect(state()).toBe(before);
    view.unmount(); act(() => { state().setMode("a", "docked-left"); }); render(<PanelLayoutPanel id="a" />);
    const dock = screen.getByRole("group", { name: "a — panel controls" }); act(() => { dock.focus(); });
    expect(dock.tabIndex).toBe(0); expect(dock.getAttribute("aria-keyshortcuts")).toBeNull(); const docked = state(); fireEvent.keyDown(dock, { key: "ArrowRight" }); expect(state()).toBe(docked);
  });
  it("distinguishes persistent parent marker, real current dropdown and unrelated nonmodal overlays", () => {
    mount(["a", "b"]); const strip = title("a"); act(() => { strip.focus(); });
    expect(strip.closest('[role="region"]')?.hasAttribute("data-esc-overlay")).toBe(true);
    fireEvent.click(within(screen.getByRole("region", { name: "a" })).getByRole("button", { name: "Panel actions" }));
    act(() => { strip.focus(); }); const before = state(); expect(fireEvent.keyDown(strip, { key: "ArrowRight" })).toBe(true); expect(state()).toBe(before);
    const other = title("b"); act(() => { other.focus(); }); const rect = state().panels.b.rect; fireEvent.keyDown(other, { key: "ArrowRight" }); expect(state().panels.b.rect.x).toBe(rect.x + 24);
  });
  it("refuses a real global modal even when title focus is forced", () => {
    mount(); render(<LemonModal open title="Modal" onClose={() => {}}><input /></LemonModal>); const strip = title("a"); act(() => { strip.focus(); });
    const before = state(); expect(fireEvent.keyDown(strip, { key: "ArrowRight" })).toBe(true); expect(state()).toBe(before);
  });
  it("retains pointer drag and resize with only pointer-capture stubbed", () => {
    mount(); const strip = title("a"); Object.defineProperty(strip, "setPointerCapture", { value: vi.fn(), configurable: true });
    const before = state().panels.a.rect;
    fireEvent(strip, new MouseEvent("pointerdown", { bubbles: true, clientX: 10, clientY: 20 }));
    fireEvent(strip, new MouseEvent("pointermove", { bubbles: true, clientX: 30, clientY: 50 }));
    fireEvent(strip, new MouseEvent("pointerup", { bubbles: true }));
    expect(state().panels.a.rect).toEqual({ ...before, x: before.x + 20, y: before.y + 30 });
    const grip = screen.getByTitle("Resize panel"); Object.defineProperty(grip, "setPointerCapture", { value: vi.fn(), configurable: true });
    fireEvent(grip, new MouseEvent("pointerdown", { bubbles: true, clientX: 0, clientY: 0 }));
    fireEvent(grip, new MouseEvent("pointermove", { bubbles: true, clientX: 30, clientY: 40 }));
    fireEvent(grip, new MouseEvent("pointerup", { bubbles: true }));
    expect(state().panels.a.rect.width).toBe(before.width + 30); expect(state().panels.a.rect.height).toBe(before.height + 40);
  });
  it("retains actual dropdown Tab, Enter and arrow choices through simulated browser activation", async () => {
    mount(); const user = userEvent.setup(); act(() => { title("a").focus(); });
    await user.tab(); expect(document.activeElement).toBe(screen.getByRole("button", { name: "Pin" }));
    await user.tab(); expect(document.activeElement).toBe(screen.getByRole("button", { name: "Panel actions" }));
    await user.keyboard("{Enter}"); expect(screen.getByRole("menu")).toBeTruthy();
    await user.keyboard("{ArrowDown}"); expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: /Dock left/ }));
    await user.keyboard("{ArrowDown}"); expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: /Dock right/ }));
    await user.keyboard("{Enter}"); expect(state().panels.a.mode).toBe("docked-right"); expect(screen.queryByRole("menu")).toBeNull();
  });
  it("encodes every UTF-16 string injectively, including empty and lone surrogates", () => {
    const ids = ["", "a", "0000", "\u0000", "é", "漢", "😀", "\ud800", "\udc00", "a:b", "a-b", "toString"];
    expect(new Set(ids.map(panelFocusId)).size).toBe(ids.length);
    for (const id of ids) expect(panelFocusId(id)).toMatch(/^panel-title-(?:[0-9a-f]{4})*$/);
  });
});
