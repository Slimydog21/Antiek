import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceWindow } from "./WorkspaceWindow";
import { LemonModal } from "../lemon/LemonModal";
import { useWindows } from "../../workspace/windowsStore";

const state = () => useWindows.getState();
beforeEach(() => {
  state().reset();
  vi.stubGlobal("innerWidth", 1440);
  vi.stubGlobal("innerHeight", 900);
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function chrome(id: string): HTMLElement {
  const root = screen.getByRole("dialog", { name: id });
  const bar = root.querySelector("[data-window-titlebar]");
  if (!(bar instanceof HTMLElement)) throw new Error("Missing actual title bar");
  return bar;
}
function open(id = "island") {
  return state().open("subaction", { workflow: "research" },
    { id, title: id, rect: { x: 200, y: 200, width: 500, height: 400 } });
}

describe("mothership island keyboard ownership", () => {
  it("leaves native titlebar buttons' Enter to their own action", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const button = screen.getByRole("button", { name: "Close window" });
    button.focus();
    expect(fireEvent.keyDown(button, { key: "Enter" })).toBe(true);
    expect(state().windows[id]?.mode).toBe("floating");
    fireEvent.click(button);
    expect(state().windows[id]).toBeUndefined();
  });

  it("accumulates two same-batch movement presses from current geometry", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    act(() => {
      fireEvent.keyDown(bar, { key: "ArrowRight" });
      fireEvent.keyDown(bar, { key: "ArrowRight", repeat: true });
    });
    expect(state().windows[id]?.rect.x).toBe(248);
  });

  it("uses Shift and arrows to resize without moving the island", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    fireEvent.keyDown(bar, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(bar, { key: "ArrowDown", shiftKey: true });
    expect(state().windows[id]?.rect).toEqual({ x: 200, y: 200, width: 524, height: 424 });
  });

  it.each([
    { ctrlKey: true }, { metaKey: true }, { altKey: true },
    { ctrlKey: true, altKey: true }, { isComposing: true },
  ])("preserves browser and composing ownership for %j", (modifier) => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    const before = state().windows[id]?.rect;
    expect(fireEvent.keyDown(bar, { key: "ArrowRight", ...modifier })).toBe(true);
    expect(state().windows[id]?.rect).toEqual(before);
  });

  it("raises the exact island when keyboard focus enters its title bar", () => {
    const a = open("a"), b = open("b");
    render(<><WorkspaceWindow id={a}><div>A</div></WorkspaceWindow><WorkspaceWindow id={b}><div>B</div></WorkspaceWindow></>);
    act(() => { chrome(a).focus(); });
    expect(state().focusedId).toBe(a);
    expect(state().windows[a]?.z).toBeGreaterThan(state().windows[b]?.z ?? 0);
  });

  it("refuses AltGraph even when Ctrl and Alt flags are absent", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    const event = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
    Object.defineProperty(event, "getModifierState", { value: (modifier: string) => modifier === "AltGraph" });
    fireEvent(bar, event);
    expect(event.defaultPrevented).toBe(false);
    expect(state().windows[id]?.rect.x).toBe(200);
  });

  it("does not treat Shift+Enter as fullscreen", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    expect(fireEvent.keyDown(bar, { key: "Enter", shiftKey: true })).toBe(true);
    expect(state().windows[id]?.mode).toBe("floating");
  });

  it("bounds keyboard resize to the viewport and existing minimum size", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    act(() => { state().setRect(id, { x: 200, y: 200, width: 1230, height: 690 }); });
    fireEvent.keyDown(bar, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(bar, { key: "ArrowDown", shiftKey: true });
    expect(state().windows[id]?.rect).toEqual({ x: 200, y: 200, width: 1240, height: 700 });
    act(() => { state().setRect(id, { width: 360, height: 240 }); });
    fireEvent.keyDown(bar, { key: "ArrowLeft", shiftKey: true });
    fireEvent.keyDown(bar, { key: "ArrowUp", shiftKey: true });
    expect(state().windows[id]?.rect).toEqual({ x: 200, y: 200, width: 360, height: 240 });
  });

  it("cannot move an outer island through a nested island's title bar", () => {
    const outer = open("outer"), inner = open("inner");
    render(<WorkspaceWindow id={outer}><WorkspaceWindow id={inner}><div>Nested product</div></WorkspaceWindow></WorkspaceWindow>);
    const bar = chrome(inner); bar.focus();
    fireEvent.keyDown(bar, { key: "ArrowRight" });
    expect(state().windows[inner]?.rect.x).toBe(224);
    expect(state().windows[outer]?.rect.x).toBe(200);
  });

  it("defers Escape to an actual open modal", () => {
    const id = open(), closeModal = vi.fn();
    render(<><WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow><LemonModal open title="Confirmation" onClose={closeModal}>Confirm</LemonModal></>);
    const bar = chrome(id); bar.focus();
    fireEvent.keyDown(bar, { key: "Escape" });
    expect(state().windows[id]).toBeDefined();
    expect(closeModal).toHaveBeenCalledTimes(1);
  });

  it("does not consume an already handled movement event", () => {
    const id = open(); render(<WorkspaceWindow id={id}><div>Product</div></WorkspaceWindow>);
    const bar = chrome(id); bar.focus();
    const event = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
    event.preventDefault(); fireEvent(bar, event);
    expect(state().windows[id]?.rect.x).toBe(200);
  });

  it("preserves a mounted product draft through keyboard move and full/restore", () => {
    let mounts = 0;
    function Draft() {
      const [text, setText] = useState("");
      useEffect(() => { mounts++; }, []);
      return <input aria-label="Product draft" value={text} onChange={(event) => setText(event.target.value)} />;
    }
    const id = open(); render(<WorkspaceWindow id={id}><Draft /></WorkspaceWindow>);
    const input = screen.getByRole("textbox", { name: "Product draft" });
    fireEvent.change(input, { target: { value: "Retain this draft" } });
    input.focus(); fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(state().windows[id]?.rect.x).toBe(200);
    const bar = chrome(id); bar.focus();
    fireEvent.keyDown(bar, { key: "ArrowRight" });
    fireEvent.keyDown(bar, { key: "Enter" });
    expect(state().windows[id]?.mode).toBe("full");
    fireEvent.keyDown(bar, { key: "f" });
    expect(state().windows[id]?.mode).toBe("floating");
    expect(screen.getByRole("textbox", { name: "Product draft" })).toBe(input);
    expect(input).toHaveProperty("value", "Retain this draft");
    expect(mounts).toBe(1);
  });
});
