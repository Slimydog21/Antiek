import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

const tier = vi.hoisted(() => ({ current: "xl" }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tier.current }));
vi.mock("./DocumentTabStrip", () => ({ DocumentTabStrip: () => null }));
vi.mock("./ProjectTreeOverlay", () => ({ default: () => null }));
vi.mock("../components/NotesPanel", () => ({ default: function DockDraft() {
  const [draft, setDraft] = useState("");
  return <input aria-label="Dock draft" value={draft} onChange={(event) => setDraft(event.target.value)} />;
} }));
vi.mock("./CompanionPane", () => ({ default: () => <p>Duplicate companion renderer</p> }));
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

  it("collapses a fixed left dock before it clips the document in a narrow actual container", () => {
    useWorkspace.getState().open("Notes", {}, { mode: "docked-left", id: "left-notes", title: "Notes" });
    mount();
    const descriptor = useWorkspace.getState().panels["left-notes"];
    const dock = screen.getByLabelText("Left dock");
    resizeContainer(450);
    expect(dock.hidden).toBe(true);
    expect(dock.style.width).toBe("0px");
    const paneWidth = right().style.width;
    expect(Number.parseFloat(paneWidth)).toBeGreaterThan(180);
    expect(Number.parseFloat(paneWidth)).toBeLessThan(220);
    fireEvent.click(screen.getByRole("button", { name: "Show left dock" }));
    expect(dock.hidden).toBe(false);
    expect(dock.style.position).toBe("absolute");
    expect(right().style.width).toBe(paneWidth);
    expect(useWorkspace.getState().panels["left-notes"]).toBe(descriptor);
    fireEvent.click(screen.getByRole("button", { name: "Hide left dock" }));
    expect(dock.hidden).toBe(true);
    resizeContainer(1200);
    expect(screen.getByLabelText("Left dock")).toBe(dock);
    expect(dock.hidden).toBe(false);
    expect(dock.style.width).toBe("320px");
    expect(screen.queryByRole("button", { name: "Show left dock" })).toBeNull();
  });

  it("retains one right-content owner and its draft across presets, including the canonical dock panel", () => {
    useWorkspace.getState().open("Companion", {}, { mode: "docked-right", id: "companion:main", title: "Companion" });
    mount();
    const companion = screen.getByRole("textbox", { name: "Right draft" });
    fireEvent.change(companion, { target: { value: "agent edit" } });
    const descriptor = useWorkspace.getState().panels["companion:main"];
    act(() => useWorkspace.getState().setLayoutPreset("docked"));
    expect(screen.getByRole("textbox", { name: "Right draft" })).toBe(companion);
    expect(companion).toHaveProperty("value", "agent edit");
    expect(screen.queryByText("Duplicate companion renderer")).toBeNull();
    expect(useWorkspace.getState().panels["companion:main"]).toBe(descriptor);
    act(() => useWorkspace.getState().setLayoutPreset("omarchy-inset"));
    expect(screen.getByRole("textbox", { name: "Right draft" })).toBe(companion);
    expect(companion).toHaveProperty("value", "agent edit");
  });

  it("keeps primary and opened right content mounted through phone crossings", () => {
    const view = mount();
    const primary = screen.getByRole("textbox", { name: "Primary draft" });
    const companion = screen.getByRole("textbox", { name: "Right draft" });
    fireEvent.change(primary, { target: { value: "primary edit" } });
    fireEvent.change(companion, { target: { value: "agent edit" } });
    tier.current = "sm"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(screen.getByRole("textbox", { name: "Primary draft" })).toBe(primary);
    expect(screen.queryByRole("textbox", { name: "Right draft" })).toBeNull();
    expect(document.contains(companion)).toBe(true);
    tier.current = "xl"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(screen.getByRole("textbox", { name: "Primary draft" })).toBe(primary);
    expect(screen.getByRole("textbox", { name: "Right draft" })).toBe(companion);
    expect(primary).toHaveProperty("value", "primary edit");
    expect(companion).toHaveProperty("value", "agent edit");
  });

  it("does not mount unopened right content in docked or phone layouts", () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const view = mount();
    expect(screen.queryByRole("textbox", { name: "Right draft", hidden: true })).toBeNull();
    tier.current = "sm"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(screen.queryByRole("textbox", { name: "Right draft", hidden: true })).toBeNull();
    useWorkspace.getState().setLayoutPreset("omarchy-inset");
    view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(screen.queryByRole("textbox", { name: "Right draft", hidden: true })).toBeNull();
  });

  it("keeps the canonical close, focus and tab behavior with custom right panels", () => {
    useWorkspace.getState().open("Companion", {}, { mode: "docked-right", id: "companion:main", title: "Companion" });
    useWorkspace.getState().open("Notes", {}, { mode: "docked-right", id: "custom-notes", title: "Right notes" });
    const view = mount();
    const companion = screen.getByRole("textbox", { name: "Right draft" });
    const notes = screen.getByRole("textbox", { name: "Dock draft" });
    fireEvent.change(companion, { target: { value: "agent edit" } });
    fireEvent.change(notes, { target: { value: "notes edit" } });
    const descriptor = useWorkspace.getState().panels["custom-notes"];
    act(() => useWorkspace.getState().setLayoutPreset("docked"));
    fireEvent.mouseDown(companion);
    expect(useWorkspace.getState().focusedPanelId).toBe("companion:main");
    companion.focus();
    fireEvent.keyDown(companion, { key: "Tab" });
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Pin");
    const close = screen.getByRole("region", { name: "Companion" }).querySelector<HTMLButtonElement>("[data-handle-action='close']");
    expect(close).not.toBeNull();
    if (close) { close.focus(); fireEvent.click(close); }
    expect(useWorkspace.getState().panels["companion:main"]).toBeUndefined();
    expect(screen.queryByRole("textbox", { name: "Right draft" })).toBeNull();
    expect(document.activeElement?.hasAttribute("data-cockpit-content")).toBe(true);
    expect(screen.getByRole("textbox", { name: "Dock draft" })).toBe(notes);
    expect(useWorkspace.getState().panels["custom-notes"]).toBe(descriptor);
    act(() => useWorkspace.getState().open("Companion", {}, { mode: "docked-right", id: "companion:main", title: "Companion" }));
    expect(screen.getByRole("textbox", { name: "Right draft" })).toBe(companion);
    expect(companion).toHaveProperty("value", "agent edit");
    notes.focus();
    tier.current = "sm"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    expect(document.contains(notes)).toBe(true);
    expect(screen.queryByRole("textbox", { name: "Dock draft" })).toBeNull();
    expect(document.activeElement?.hasAttribute("data-cockpit-content")).toBe(true);
    tier.current = "xl"; view.rerender(<PanelLayout mainSlot={<PrimaryDraft />} />);
    act(() => useWorkspace.getState().setLayoutPreset("omarchy-inset"));
    expect(screen.getByRole("textbox", { name: "Dock draft" })).toBe(notes);
    expect(notes).toHaveProperty("value", "notes edit");
  });

  it("gives a collapsed left dock one Escape owner and restores the toggle focus", () => {
    useWorkspace.getState().open("Notes", {}, { mode: "docked-left", id: "left-notes", title: "Notes" });
    mount();
    resizeContainer(450);
    fireEvent.click(screen.getByRole("button", { name: "Show left dock" }));
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Pin");
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    const toggle = screen.getByRole("button", { name: "Show left dock" });
    expect(document.activeElement).toBe(toggle);
    expect(screen.getByLabelText("Left dock").hidden).toBe(true);
    fireEvent.click(toggle);
    const notes = screen.getByRole("textbox", { name: "Dock draft" });
    notes.focus();
    fireEvent.keyDown(notes, { key: "Escape" });
    expect(screen.getByLabelText("Left dock").hidden).toBe(false);
  });

  it("hands the canonical surface to its existing floating owner without a hidden duplicate", async () => {
    useWorkspace.getState().open("Companion", {}, { mode: "docked-right", id: "companion:main", title: "Companion" });
    mount();
    act(() => useWorkspace.getState().setMode("companion:main", "floating"));
    await screen.findByText("Duplicate companion renderer");
    expect(screen.queryByRole("textbox", { name: "Right draft", hidden: true })).toBeNull();
    act(() => useWorkspace.getState().setMode("companion:main", "docked-right"));
    expect(screen.getAllByRole("textbox", { name: "Right draft", hidden: true })).toHaveLength(1);
    expect(screen.queryByText("Duplicate companion renderer")).toBeNull();
  });

  it("restores a compact dock when primary fullscreen gives it enough room", () => {
    useWorkspace.getState().open("Notes", {}, { mode: "docked-left", id: "left-notes", title: "Notes" });
    mount();
    const dock = screen.getByLabelText("Left dock");
    resizeContainer(800);
    expect(dock.hidden).toBe(true);
    act(() => useWorkspace.getState().setFullscreenPane("left"));
    expect(dock.hidden).toBe(false);
    expect(dock.style.width).toBe("320px");
    act(() => useWorkspace.getState().setFullscreenPane(null));
    expect(dock.hidden).toBe(true);
  });

});
