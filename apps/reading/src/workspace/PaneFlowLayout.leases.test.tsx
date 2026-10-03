import { useLayoutEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PaneFlowLayout, paneEventTarget, usePaneFlowFrame } from "./PaneFlowLayout";
import { COMPANION_PANE, CORE_PANE, paneKey } from "./paneFlowGeometry";
import type { PaneTarget } from "./panel.types";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

// Observers preserve the actual React effect and lease implementations.
const observations = vi.hoisted(() => {
  const value: {
    controllerInstalls: number;
    controllerCleanups: Array<() => void>;
    controllerRetirements: boolean[];
  } = { controllerInstalls: 0, controllerCleanups: [], controllerRetirements: [] };
  return value;
});

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  const observedLayoutEffect: typeof actual.useLayoutEffect = (effect, dependencies) =>
    actual.useLayoutEffect(() => {
      const before = observations.controllerInstalls;
      const dispose = effect();
      if (observations.controllerInstalls !== before && typeof dispose === "function") {
        observations.controllerCleanups.push(dispose);
      }
      return dispose;
    }, dependencies);
  return { ...actual, useLayoutEffect: observedLayoutEffect };
});

vi.mock("./paneHostLease", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./paneHostLease")>();
  const install: typeof actual.installPaneHostLease = (registry, key, record) => {
    const lease = actual.installPaneHostLease(registry, key, record);
    if (typeof key !== "object" || key === null || !(key instanceof HTMLElement)
        || !key.hasAttribute("data-pane-flow-root")) return lease;
    observations.controllerInstalls += 1;
    return { ...lease, retire: () => {
      const retired = lease.retire();
      observations.controllerRetirements.push(retired);
      return retired;
    } };
  };
  return { ...actual, installPaneHostLease: install };
});

vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));

type Frame = ReturnType<typeof usePaneFlowFrame>;
const frames = new Map<string, Frame>();
const WINDOW: PaneTarget = { kind: "window", id: "p02a:registration-control" };

function ControlledFrame({ name, target }: { name: string; target: PaneTarget }) {
  const frame = usePaneFlowFrame(target);
  const [count, setCount] = useState(0);
  useLayoutEffect(() => { frames.set(name, frame); });
  return <div ref={frame.ref} data-testid={name} data-pane-host={frame.hostKey}
    hidden={frame.hidden || undefined} style={frame.style} tabIndex={-1}>
    <button onClick={() => setCount((previous) => previous + 1)}>{name} count {count}</button>
    <textarea aria-label={`${name} local draft`} />
  </div>;
}

function frame(name: string): Frame {
  const current = frames.get(name);
  if (!current) throw new Error(`Missing actual hook capture ${name}`);
  return current;
}

function element(name: string): HTMLElement {
  const node = screen.getByTestId(name);
  if (!(node instanceof HTMLElement)) throw new Error(`Missing frame ${name}`);
  return node;
}

function currentCleanup(): () => void {
  const dispose = observations.controllerCleanups.at(-1);
  if (!dispose) throw new Error("Missing actual controller effect cleanup");
  return dispose;
}

function eventAt(node: HTMLElement, options: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key: "ArrowRight", code: "ArrowRight",
    ctrlKey: true, altKey: true, bubbles: true, cancelable: true, ...options });
  act(() => { node.focus(); node.dispatchEvent(event); });
  return event;
}

beforeEach(() => {
  disablePersistence();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useWindows.getState().open("p02a:controlled-frame", {}, { id: "p02a:registration-control" });
  useWorkspace.getState().setPaneArrangement("horizontal");
  frames.clear();
  observations.controllerInstalls = 0;
  observations.controllerCleanups.length = 0;
  observations.controllerRetirements.length = 0;
  // Controlled DOM measurements are not native geometry or body continuity proof.
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
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterEach(() => {
  cleanup();
  frames.clear();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("actual frame and controller registration ownership", () => {
  it.each([CORE_PANE, COMPANION_PANE, WINDOW])(
    "keeps the newer same-key host after the older hook's delayed null: %j", (target) => {
      const view = render(<PaneFlowLayout><ControlledFrame name="old" target={target} /></PaneFlowLayout>);
      const oldRef = frame("old").ref;
      view.rerender(<PaneFlowLayout><ControlledFrame name="old" target={target} />
        <ControlledFrame name="new" target={target} /></PaneFlowLayout>);
      const node = element("new");
      const event = eventAt(node);
      expect(paneEventTarget(event)).toEqual(target);
      act(() => { oldRef(null); oldRef(null); });
      expect(paneEventTarget(event)).toEqual(target);
      expect(element("new")).toBe(node);
      expect(document.activeElement).toBe(node);
      expect(paneEventTarget(eventAt(element("old")))).toBeNull();
    },
  );

  it("fences nodeRef when the same hook changes its target and callback identity", () => {
    const view = render(<PaneFlowLayout><ControlledFrame name="switch" target={CORE_PANE} /></PaneFlowLayout>);
    const oldRef = frame("switch").ref;
    const node = element("switch");
    view.rerender(<PaneFlowLayout><ControlledFrame name="switch" target={COMPANION_PANE} /></PaneFlowLayout>);
    expect(frame("switch").ref).not.toBe(oldRef);
    expect(element("switch")).toBe(node);
    const event = eventAt(node);
    act(() => { useWorkspace.getState().togglePaneZoom(COMPANION_PANE); });
    act(() => { oldRef(null); });
    expect(paneEventTarget(event)).toEqual(COMPANION_PANE);
    let restored = false;
    act(() => { restored = frame("switch").restoreZoom(); });
    expect(restored).toBe(true);
    expect(useWorkspace.getState().paneZoom).toBeNull();
  });

  it("does not let the first A callback retire the current A after A to B to A", () => {
    const view = render(<PaneFlowLayout><ControlledFrame name="switch" target={CORE_PANE} /></PaneFlowLayout>);
    const firstA = frame("switch").ref;
    view.rerender(<PaneFlowLayout><ControlledFrame name="switch" target={COMPANION_PANE} /></PaneFlowLayout>);
    view.rerender(<PaneFlowLayout><ControlledFrame name="switch" target={CORE_PANE} /></PaneFlowLayout>);
    const currentA = frame("switch").ref;
    expect(currentA).not.toBe(firstA);
    const event = eventAt(element("switch"));
    act(() => { firstA(null); });
    expect(paneEventTarget(event)).toEqual(CORE_PANE);
    act(() => { currentA(null); });
    expect(paneEventTarget(event)).toBeNull();
  });

  it("keeps the newer installed controller when its older actual effect cleanup runs again", () => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    const oldCleanup = currentCleanup();
    act(() => { useWorkspace.getState().setPaneArrangement("tiled"); });
    const event = eventAt(element("core"));
    const newCleanup = currentCleanup();
    expect(newCleanup).not.toBe(oldCleanup);
    expect(paneEventTarget(event)).toEqual(CORE_PANE);
    act(() => { oldCleanup(); oldCleanup(); });
    expect(observations.controllerRetirements.slice(-2)).toEqual([false, false]);
    expect(paneEventTarget(event)).toEqual(CORE_PANE);
    act(() => { newCleanup(); });
    expect(paneEventTarget(event)).toBeNull();
  });

  it("retires the current own attachment once and admits its actual reattachment", () => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    const node = element("core");
    const ref = frame("core").ref;
    const event = eventAt(node);
    act(() => { ref(null); ref(null); });
    expect(paneEventTarget(event)).toBeNull();
    act(() => { ref(node); });
    expect(paneEventTarget(event)).toEqual(CORE_PANE);
    act(() => { ref(null); });
    expect(paneEventTarget(event)).toBeNull();
  });

  it("retires its actual root on unmount without retiring another live root", () => {
    const left = render(<PaneFlowLayout><ControlledFrame name="left" target={CORE_PANE} /></PaneFlowLayout>);
    const leftEvent = eventAt(element("left"));
    const right = render(<PaneFlowLayout><ControlledFrame name="right" target={CORE_PANE} /></PaneFlowLayout>);
    const rightEvent = eventAt(element("right"));
    left.unmount();
    expect(observations.controllerRetirements.at(-1)).toBe(true);
    expect(paneEventTarget(leftEvent)).toBeNull();
    expect(paneEventTarget(rightEvent)).toEqual(CORE_PANE);
    right.unmount();
    expect(paneEventTarget(rightEvent)).toBeNull();
  });

  it("keeps actual node, callback, local state and descriptor authority through presentation updates", () => {
    render(<PaneFlowLayout><ControlledFrame name="window" target={WINDOW} /></PaneFlowLayout>);
    const node = element("window");
    const ref = frame("window").ref;
    const original = useWindows.getState().windows["p02a:registration-control"];
    fireEvent.click(screen.getByText("window count 0"));
    act(() => {
      useWindows.getState().setRect("p02a:registration-control", { x: original.rect.x + 1 });
      useWindows.getState().focus("p02a:registration-control");
      useWorkspace.getState().setPaneFocus(WINDOW);
      useWorkspace.getState().reorderPane(WINDOW, -1);
      useWorkspace.getState().setPaneArrangement("tiled");
      useWorkspace.getState().setPaneArrangement("horizontal");
    });
    expect(element("window")).toBe(node);
    expect(frame("window").ref).toBe(ref);
    expect(screen.getByText("window count 1")).toBeTruthy();
    expect(useWindows.getState().windows["p02a:registration-control"].payload).toBe(original.payload);
    expect(paneEventTarget(eventAt(node))).toEqual(WINDOW);
    expect(paneKey(WINDOW)).toBe("window:p02a:registration-control");
  });

  it("refuses a stale same-key frame without its current lease", () => {
    render(<PaneFlowLayout><ControlledFrame name="old" target={CORE_PANE} />
      <ControlledFrame name="new" target={CORE_PANE} /></PaneFlowLayout>);
    expect(paneEventTarget(eventAt(element("old")))).toBeNull();
    act(() => { useWorkspace.getState().togglePaneZoom(CORE_PANE); });
    expect(frame("old").restoreZoom()).toBe(false);
    expect(useWorkspace.getState().paneZoom).toEqual(CORE_PANE);
  });

  it.each(["hidden", "inert"])("retains the %s refusal on a current registered frame", (attribute) => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    const node = element("core");
    const event = eventAt(node);
    node.setAttribute(attribute, "");
    expect(paneEventTarget(event)).toBeNull();
    node.removeAttribute(attribute);
    expect(paneEventTarget(event)).toEqual(CORE_PANE);
  });

  it("retains overlay, consumed event, editor and captured pointer refusals", () => {
    const view = render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    const node = element("core");
    const event = eventAt(node);
    const overlay = document.createElement("div");
    overlay.setAttribute("data-esc-overlay", "");
    document.body.append(overlay);
    expect(paneEventTarget(event)).toBeNull();
    overlay.remove();
    event.preventDefault();
    expect(paneEventTarget(event)).toBeNull();
    expect(paneEventTarget(event, true)).toEqual(CORE_PANE);
    const input = screen.getByLabelText("core local draft");
    if (!(input instanceof HTMLElement)) throw new Error("Missing controlled editor");
    expect(paneEventTarget(eventAt(input))).toBeNull();
    const current = eventAt(node);
    Object.defineProperty(node, "hasPointerCapture", { configurable: true, value: () => true });
    fireEvent.gotPointerCapture(node, { pointerId: 7 });
    expect(paneEventTarget(current)).toBeNull();
    fireEvent.lostPointerCapture(node, { pointerId: 7 });
    expect(paneEventTarget(current)).toEqual(CORE_PANE);
    view.unmount();
    expect(paneEventTarget(current)).toBeNull();
  });

  it("refuses an unregistered DOM lookalike in the actual current root", () => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    const root = element("core").closest("[data-pane-flow-root]");
    if (!(root instanceof HTMLElement)) throw new Error("Missing actual root");
    const unknown = document.createElement("div");
    unknown.dataset.paneHost = "core";
    unknown.tabIndex = -1;
    root.append(unknown);
    expect(paneEventTarget(eventAt(unknown))).toBeNull();
  });

  it("does not give an outside-provider frame a lease by moving its DOM under a live root", () => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} /></PaneFlowLayout>);
    render(<ControlledFrame name="outside" target={CORE_PANE} />);
    const root = element("core").closest("[data-pane-flow-root]");
    if (!(root instanceof HTMLElement)) throw new Error("Missing actual root");
    root.append(element("outside"));
    act(() => { useWorkspace.getState().togglePaneZoom(CORE_PANE); });
    expect(frame("outside").restoreZoom()).toBe(false);
    expect(useWorkspace.getState().paneZoom).toEqual(CORE_PANE);
  });

  it("refuses a current A lease beneath live B without delegating or mutating zoom", () => {
    render(<PaneFlowLayout><ControlledFrame name="a-core" target={CORE_PANE} />
      <ControlledFrame name="a-companion" target={COMPANION_PANE} /></PaneFlowLayout>);
    render(<PaneFlowLayout><ControlledFrame name="b-core" target={CORE_PANE} />
      <ControlledFrame name="b-companion" target={COMPANION_PANE} /></PaneFlowLayout>);
    const node = element("a-core");
    const originalParent = node.parentElement;
    const rootB = element("b-core").closest("[data-pane-flow-root]");
    if (!originalParent || !(rootB instanceof HTMLElement)) throw new Error("Missing actual provider roots");
    const currentRef = frame("a-core").ref;
    expect(paneEventTarget(eventAt(node))).toEqual(CORE_PANE);
    expect(paneEventTarget(eventAt(element("b-core")))).toEqual(CORE_PANE);
    act(() => { useWorkspace.getState().togglePaneZoom(COMPANION_PANE); });
    const state = useWorkspace.getState();
    const scroll = rootB.scrollLeft;
    const active = document.activeElement;
    rootB.append(node);
    try {
      expect(frame("a-core").ref).toBe(currentRef);
      expect(node.closest("[data-pane-flow-root]")).toBe(rootB);
      expect(frame("a-core").restoreZoom()).toBe(false);
      expect(useWorkspace.getState()).toBe(state);
      expect(useWorkspace.getState().paneZoom).toEqual(COMPANION_PANE);
      expect(rootB.scrollLeft).toBe(scroll);
      expect(document.activeElement).toBe(active);
    } finally {
      originalParent.append(node);
    }
    // The same still-current A attachment restores through its own controller.
    let restored = false;
    act(() => { restored = frame("a-core").restoreZoom(); });
    expect(frame("a-core").ref).toBe(currentRef);
    expect(restored).toBe(true);
    expect(useWorkspace.getState().paneZoom).toBeNull();
  });

  it("allows the current core controller to restore itself and another zoomed pane", () => {
    render(<PaneFlowLayout><ControlledFrame name="core" target={CORE_PANE} />
      <ControlledFrame name="companion" target={COMPANION_PANE} /></PaneFlowLayout>);
    const node = element("core");
    const currentRef = frame("core").ref;
    act(() => { useWorkspace.getState().togglePaneZoom(CORE_PANE); });
    let restored = false;
    act(() => { restored = frame("core").restoreZoom(); });
    expect(restored).toBe(true);
    expect(useWorkspace.getState().paneZoom).toBeNull();
    act(() => { useWorkspace.getState().togglePaneZoom(COMPANION_PANE); });
    expect(frame("core").hidden).toBe(true);
    expect(frame("companion").zoomed).toBe(true);
    expect(element("core")).toBe(node);
    expect(frame("core").ref).toBe(currentRef);
    act(() => { restored = frame("core").restoreZoom(); });
    expect(restored).toBe(true);
    expect(useWorkspace.getState().paneZoom).toBeNull();
  });

});
