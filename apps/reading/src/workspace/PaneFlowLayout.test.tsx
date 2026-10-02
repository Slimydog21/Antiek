import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WindowsLayer } from "../components/windows/WindowsLayer";
import { PanelLayout } from "./PanelLayout";
import { PaneFlowLayout } from "./PaneFlowLayout";
import { disablePersistence, enablePersistence, useWorkspace } from "./WorkspaceStore";
import { paneKey } from "./paneFlowGeometry";
import { useWindows } from "./windowsStore";

const controls = vi.hoisted(() => ({ tier: "xl", width: 1000, height: 700,
  coreMounts: 0, coreUnmounts: 0, companionMounts: 0, companionUnmounts: 0,
  resize: new Set<() => void>() }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => controls.tier }));
vi.mock("./usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => true }));
vi.mock("./DocumentTabStrip", () => ({ DocumentTabStrip: () => null }));
vi.mock("./RightPaneForMode", () => ({ default: () => <ControlledBody kind="companion" /> }));
vi.mock("../components/NotesPanel", () => ({ default: () => <textarea aria-label="Controlled dock draft" /> }));

function ControlledBody({ kind }: { kind: "core" | "companion" }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (kind === "core") controls.coreMounts += 1; else controls.companionMounts += 1;
    return () => { if (kind === "core") controls.coreUnmounts += 1; else controls.companionUnmounts += 1; };
  }, [kind]);
  return <div data-testid={`${kind}-scroll`} className="overflow-auto">
    <button onClick={() => setCount((value) => value + 1)}>{kind} count {count}</button>
    <textarea aria-label={`Controlled ${kind} draft`} />
  </div>;
}

function mountWorkspace() {
  const result = render(<PaneFlowLayout><PanelLayout mainSlot={<ControlledBody kind="core" />} /><WindowsLayer /></PaneFlowLayout>);
  act(() => { vi.runOnlyPendingTimers(); });
  return result;
}

function element(selector: string): HTMLElement {
  const node = document.querySelector(selector);
  if (!(node instanceof HTMLElement)) throw new Error(`Missing controlled host: ${selector}`);
  return node;
}

beforeEach(() => {
  vi.useFakeTimers();
  disablePersistence();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useWorkspace.getState().setPaneArrangement("horizontal");
  Object.assign(controls, { tier: "xl", width: 1000, height: 700, coreMounts: 0, coreUnmounts: 0,
    companionMounts: 0, companionUnmounts: 0 });
  controls.resize.clear();
  // Controlled DOM measurements only. These are not native layout proof.
  vi.spyOn(Element.prototype, "clientWidth", "get").mockImplementation(function (this: Element) {
    return this.hasAttribute("data-pane-flow-root") ? controls.width : 1000;
  });
  vi.spyOn(Element.prototype, "clientHeight", "get").mockImplementation(function (this: Element) {
    return this.hasAttribute("data-pane-flow-root") ? controls.height : 700;
  });
  vi.spyOn(Element.prototype, "getClientRects").mockImplementation(function (this: Element): DOMRectList {
    if (!this.isConnected || this.closest("[hidden], [inert]")) {
      return { length: 0, item: () => null, *[Symbol.iterator]() {} };
    }
    const rect = new DOMRect(0, 0, controls.width, controls.height);
    return { 0: rect, length: 1, item: (index) => index === 0 ? rect : null, *[Symbol.iterator]() { yield rect; } };
  });
  vi.stubGlobal("ResizeObserver", class implements ResizeObserver {
    private measure: () => void;
    private target: Element | null = null;
    constructor(callback: ResizeObserverCallback) {
      this.measure = () => {
        if (!this.target) return;
        const size = { inlineSize: controls.width, blockSize: controls.height };
        callback([{ target: this.target, contentRect: new DOMRect(0, 0, controls.width, controls.height),
          borderBoxSize: [size], contentBoxSize: [size], devicePixelContentBoxSize: [size] }], this);
      };
    }
    observe(target: Element) { this.target = target; controls.resize.add(this.measure); this.measure(); }
    unobserve() {}
    disconnect() { controls.resize.delete(this.measure); }
  });
});

afterEach(() => {
  disablePersistence();
  cleanup();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("actual shared PanelLayout and product hosts", () => {
  it("preserves reset's no-write suppression through a nested presentation join", () => {
    useWorkspace.getState().setLayoutPreset("docked");
    useWorkspace.getState().open("Notes", {}, { id: "control:notes", mode: "docked-right" });
    const write = vi.spyOn(Storage.prototype, "setItem");
    enablePersistence();
    useWorkspace.getState().reset();
    act(() => { vi.advanceTimersByTime(400); });
    expect(write.mock.calls.filter(([key]) => key === "antiek.workspace.global")).toEqual([]);
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(["core"]);
  });
  it("retains the core, companion draft, local state and vertical scroll through both modes", () => {
    useWindows.getState().open("u1:non-book-control", {}, { id: "control:a" });
    mountWorkspace();
    const core = screen.getByLabelText("Controlled core draft");
    const companion = screen.getByLabelText("Controlled companion draft");
    const scroll = screen.getByTestId("core-scroll");
    const windowHost = element('[data-workspace-window="control:a"]');
    fireEvent.change(core, { target: { value: "Unsaved local control" } });
    fireEvent.change(companion, { target: { value: "Companion local control" } });
    fireEvent.click(screen.getByText("core count 0"));
    scroll.scrollTop = 312;
    const tiles = useWorkspace.getState().paneTiles;
    act(() => { useWorkspace.getState().togglePaneArrangement(); });
    act(() => { useWorkspace.getState().togglePaneArrangement(); });
    expect(screen.getByLabelText("Controlled core draft")).toBe(core);
    expect(screen.getByLabelText("Controlled companion draft")).toBe(companion);
    expect(element('[data-workspace-window="control:a"]')).toBe(windowHost);
    expect(core instanceof HTMLTextAreaElement && core.value).toBe("Unsaved local control");
    expect(companion instanceof HTMLTextAreaElement && companion.value).toBe("Companion local control");
    expect(screen.getByText("core count 1")).toBeTruthy();
    expect(scroll.scrollTop).toBe(312);
    expect(useWorkspace.getState().paneTiles).toEqual(tiles);
    expect([controls.coreMounts, controls.coreUnmounts, controls.companionMounts, controls.companionUnmounts]).toEqual([1, 0, 1, 0]);
  });

  it("keeps host order independent of actual window focus/z restacking", () => {
    const windows = useWindows.getState();
    windows.open("u1:non-book-control", {}, { id: "control:a" });
    windows.open("u1:non-book-control", {}, { id: "control:b" });
    mountWorkspace();
    const order = useWorkspace.getState().paneOrder.map(paneKey);
    const core = element('[data-pane-host="core"]');
    act(() => { core.focus(); windows.focus("control:a"); });
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(order);
    expect(useWindows.getState().order).toEqual(["control:b", "control:a"]);
    expect(document.activeElement).toBe(core);
  });

  it("retains sibling mounts while zoom hides/inerts them and restores horizontal scroll", () => {
    useWindows.getState().open("u1:non-book-control", {}, { id: "control:a" });
    mountWorkspace();
    const root = element("[data-pane-flow-root]");
    const core = element('[data-pane-host="core"]');
    const windowHost = element('[data-workspace-window="control:a"]');
    const order = useWorkspace.getState().paneOrder;
    act(() => { windowHost.focus(); });
    fireEvent.scroll(root, { target: { scrollLeft: 500 } });
    act(() => { useWorkspace.getState().togglePaneZoom({ kind: "window", id: "control:a" }); });
    expect(core.hidden).toBe(true);
    expect(core.inert).toBe(true);
    expect(core.isConnected).toBe(true);
    expect(windowHost.hidden).toBe(false);
    fireEvent.scroll(root, { target: { scrollLeft: 0 } });
    act(() => { useWorkspace.getState().restorePaneZoom(); });
    expect(element('[data-pane-host="core"]')).toBe(core);
    expect(core.hidden).toBe(false);
    expect(core.inert).toBe(false);
    expect(root.scrollLeft).toBe(500);
    expect(useWorkspace.getState().paneOrder).toEqual(order);
    expect([controls.coreUnmounts, controls.companionUnmounts]).toEqual([0, 0]);
  });

  it("returns focus to the same admitted window after the existing restore chip disappears", () => {
    useWindows.getState().open("u1:non-book-control", {}, { id: "control:a" });
    mountWorkspace();
    const windowHost = element('[data-workspace-window="control:a"]');
    act(() => { windowHost.focus(); });
    fireEvent.click(screen.getByLabelText("Zoom pane"));
    const chip = screen.getByLabelText("Exit fullscreen (Esc)");
    act(() => { chip.focus(); });
    fireEvent.click(chip);
    expect(useWorkspace.getState().paneZoom).toBeNull();
    expect(document.activeElement).toBe(windowHost);
    expect(element('[data-workspace-window="control:a"]')).toBe(windowHost);
  });

  it("restores core zoom only from current working-area focus and retains child priority", () => {
    mountWorkspace();
    const core = element('[data-pane-host="core"]');
    act(() => { core.focus(); useWorkspace.getState().togglePaneZoom({ kind: "core" }); });
    const outside = document.createElement("button"); document.body.append(outside);
    act(() => { outside.focus(); });
    fireEvent.keyDown(outside, { key: "Escape", code: "Escape" });
    expect(useWorkspace.getState().paneZoom).toEqual({ kind: "core" });
    const draft = screen.getByLabelText("Controlled core draft");
    act(() => { draft.focus(); });
    fireEvent.keyDown(draft, { key: "Escape", code: "Escape" });
    expect(useWorkspace.getState().paneZoom).toEqual({ kind: "core" });
    const chip = screen.getByLabelText("Exit fullscreen (Esc)");
    act(() => { chip.focus(); });
    fireEvent.keyDown(chip, { key: "Escape", code: "Escape", repeat: true });
    expect(useWorkspace.getState().paneZoom).toEqual({ kind: "core" });
    fireEvent.keyDown(chip, { key: "Escape", code: "Escape" });
    expect(useWorkspace.getState().paneZoom).toBeNull();
    expect(document.activeElement).toBe(core);
    outside.remove();
  });

  it.each([1, 2, 15, 40])("retains %i real window frames with one coordinate origin", (count) => {
    for (let index = 0; index < count; index += 1) {
      useWindows.getState().open("u1:non-book-control", { controlled: true }, { id: `control:${index}` });
    }
    mountWorkspace();
    expect(document.querySelectorAll("[data-workspace-window]")).toHaveLength(count);
    expect(document.querySelectorAll("[data-windows-layer]")).toHaveLength(1);
    expect(useWorkspace.getState().paneOrder).toHaveLength(count + 2);
    const hosts = [...document.querySelectorAll("[data-workspace-window]")];
    act(() => { useWorkspace.getState().togglePaneArrangement(); });
    expect([...document.querySelectorAll("[data-workspace-window]")]).toEqual(hosts);
    expect(useWindows.getState().windows[`control:${count - 1}`].payload).toEqual({ controlled: true });
  });

  it("refuses lost bounds and recovers the same mounts after a positive measurement", () => {
    mountWorkspace();
    const core = element('[data-pane-host="core"]');
    controls.width = 0;
    act(() => { for (const resize of controls.resize) resize(); });
    expect(element("[data-pane-flow-root]").dataset.paneMeasurement).toBe("unmeasured");
    expect(core.hidden).toBe(true);
    controls.width = 1000;
    act(() => { for (const resize of controls.resize) resize(); });
    expect(element('[data-pane-host="core"]')).toBe(core);
    expect(core.hidden).toBe(false);
    expect(controls.coreMounts).toBe(1);
  });

  it("keeps a valid docked empty-right layout absent when flow starts", () => {
    useWorkspace.getState().setLayoutPreset("docked");
    useWorkspace.getState().setPaneArrangement("legacy");
    mountWorkspace();
    const coreDraft = screen.getByLabelText("Controlled core draft");
    act(() => { useWorkspace.getState().setPaneArrangement("horizontal"); });
    expect(useWorkspace.getState().layoutPreset).toBe("docked");
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(["core"]);
    expect(screen.queryByLabelText("Controlled companion draft")).toBeNull();
    expect(screen.getByLabelText("Controlled core draft")).toBe(coreDraft);
  });

  it("keeps an actually admitted dock panel in the same right compound host", async () => {
    useWorkspace.getState().setLayoutPreset("docked");
    useWorkspace.getState().setPaneArrangement("legacy");
    useWorkspace.getState().open("Notes", {}, { id: "control:notes", mode: "docked-right" });
    mountWorkspace();
    await act(async () => { await Promise.resolve(); });
    const draft = screen.getByLabelText("Controlled dock draft");
    fireEvent.change(draft, { target: { value: "Retained dock control" } });
    act(() => { useWorkspace.getState().setPaneArrangement("horizontal"); });
    act(() => { useWorkspace.getState().setPaneArrangement("tiled"); });
    expect(screen.getByLabelText("Controlled dock draft")).toBe(draft);
    expect(useWorkspace.getState().dockRightIds).toEqual(["control:notes"]);
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(["core", "companion"]);
    expect(screen.queryByLabelText("Controlled companion draft")).toBeNull();
    expect(draft instanceof HTMLTextAreaElement && draft.value).toBe("Retained dock control");
  });
});
