import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

const tier = vi.hoisted(() => ({ current: "xl" }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tier.current }));
vi.mock("./DocumentTabStrip", () => ({ DocumentTabStrip: () => null }));
vi.mock("./ProjectTreeOverlay", () => ({ default: () => null }));
vi.mock("./RightPaneForMode", () => ({
  default: function RightDraft() {
    const [draft, setDraft] = useState("");
    return <input aria-label="Right draft" value={draft} onChange={(event) => setDraft(event.target.value)} />;
  },
}));
function PrimaryDraft() {
  const [draft, setDraft] = useState("");
  return <input aria-label="Primary draft" value={draft} onChange={(event) => setDraft(event.target.value)} />;
}

let cockpitWidth = 1200;
const observers = new Set<FixtureResizeObserver>();
class FixtureResizeObserver implements ResizeObserver {
  constructor(private callback: ResizeObserverCallback) { observers.add(this); }
  observe() {}
  unobserve() {}
  disconnect() { observers.delete(this); }
  notify() { this.callback([], this); }
}
const separator = () => screen.getByRole("separator", { name: "Resize panes" });
const right = () => screen.getByRole("region", { name: "Agents pane" });
const mount = () => render(<PanelLayout mainSlot={<PrimaryDraft />} />);
function resizeContainer(width: number) {
  cockpitWidth = width;
  act(() => { observers.forEach((observer) => observer.notify()); });
}

beforeEach(() => {
  cockpitWidth = 1200;
  tier.current = "xl";
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  vi.stubGlobal("ResizeObserver", FixtureResizeObserver);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => new DOMRect(0, 0, cockpitWidth, 700));
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", { configurable: true, value: () => true });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); observers.clear(); useWorkspace.getState().reset(); });

describe("inset pane resizing", () => {
  it("retains the ratified defaults until the operator resizes", () => {
    const view = mount();
    expect(right().style.width).toBe("320px");
    tier.current = "md";
    view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(right().style.width).toBe("280px");
    expect(separator().getAttribute("aria-orientation")).toBe("vertical");
    expect(separator().tabIndex).toBe(0);
  });

  it("uses local arrow keys and bounds from the actual cockpit, then restores the default", () => {
    mount();
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    expect(right().style.width).toBe("336px");
    fireEvent.keyDown(separator(), { key: "End" });
    expect(right().style.width).toBe("844px");
    expect(separator().getAttribute("aria-valuenow")).toBe("844");
    fireEvent.keyDown(separator(), { key: "Home" });
    expect(right().style.width).toBe("280px");
    fireEvent.keyDown(separator(), { key: "Enter" });
    expect(right().style.width).toBe("320px");
  });

  it("drags to peer width, ignores a second pointer, clamps and cancels", () => {
    mount();
    fireEvent.pointerDown(separator(), { pointerId: 1, clientX: 900, button: 0 });
    fireEvent.pointerMove(separator(), { pointerId: 2, clientX: 100 });
    expect(right().style.width).toBe("320px");
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: 638 });
    expect(right().style.width).toBe("582px");
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: -1000 });
    expect(right().style.width).toBe("844px");
    fireEvent.pointerCancel(separator(), { pointerId: 1 });
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: 1000 });
    expect(right().style.width).toBe("844px");
  });

  it("clamps to a shrinking container and restores the preferred width when it grows", () => {
    mount();
    fireEvent.keyDown(separator(), { key: "End" });
    resizeContainer(800);
    expect(right().style.width).toBe("444px");
    resizeContainer(1200);
    expect(right().style.width).toBe("844px");
    resizeContainer(450);
    expect(Number.parseFloat(right().style.width)).toBeLessThan(450 - 36);
    expect(Number.parseFloat(right().style.width)).toBeGreaterThan(0);
  });

  it("preserves both mounted drafts and the chosen width across fullscreen", () => {
    mount();
    const primary = screen.getByRole("textbox", { name: "Primary draft" });
    const companion = screen.getByRole("textbox", { name: "Right draft" });
    fireEvent.change(primary, { target: { value: "primary edit" } });
    fireEvent.change(companion, { target: { value: "agent edit" } });
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    for (const side of ["left", "right"] as const) {
      act(() => useWorkspace.getState().setFullscreenPane(side));
      expect(screen.queryByRole("separator", { name: "Resize panes" })).toBeNull();
      act(() => useWorkspace.getState().setFullscreenPane(null));
      expect(screen.getByRole("textbox", { name: "Primary draft" })).toBe(primary);
      expect(screen.getByRole("textbox", { name: "Right draft" })).toBe(companion);
      expect(right().style.width).toBe("336px");
    }
  });

  it("preserves the primary draft and width across presets without a docked resize control", () => {
    mount();
    const primary = screen.getByRole("textbox", { name: "Primary draft" });
    fireEvent.change(primary, { target: { value: "primary edit" } });
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    act(() => useWorkspace.getState().setLayoutPreset("docked"));
    expect(screen.queryByRole("separator", { name: "Resize panes" })).toBeNull();
    act(() => useWorkspace.getState().setLayoutPreset("omarchy-inset"));
    expect(screen.getByRole("textbox", { name: "Primary draft" })).toBe(primary);
    expect(right().style.width).toBe("336px");
  });

  it("keeps phone behavior without a separator and restores the preferred width", () => {
    const view = mount();
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    tier.current = "sm"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(screen.queryByRole("separator", { name: "Resize panes" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Agents pane" })).toBeNull();
    tier.current = "xl"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(right().style.width).toBe("336px");
  });

});
