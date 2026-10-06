/**
 * VERIFIER PROBES (untracked scratch extraction only; never committed).
 * Q-probes re-test the auditor's C2C3 claims on each head.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { useEffect, useState } from "react";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true, configurable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }),
  });
});
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));
vi.mock("./PanelLayoutPanel", () => ({ PanelLayoutPanel: ({ id }: { id: string }) => <div data-panel={id}>{id}</div> }));

import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
function key(target: EventTarget, spec: string) { act(() => { press(target, spec, "mac"); }); }
function keyRaw(target: EventTarget, init: KeyboardEventInit) { act(() => { pressKey(target, init); }); }

let mounts = 0;
function Route() {
  const [v, setV] = useState("");
  useEffect(() => { mounts += 1; }, []);
  return <input data-testid="field" value={v} onChange={(e) => setV(e.target.value)} />;
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  mounts = 0;
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  ws().reset();
  ws().setLayoutPreset("docked");
  uninstall = installShortcuts(vi.fn() as never);
});
afterEach(() => {
  uninstall?.(); cleanup(); prefixState.disarm(); ws().reset(); ws().setLayoutPreset("docked");
  window.localStorage.removeItem("antiek.workspace.layout-preset"); unpinPlatform(); document.body.innerHTML = "";
});

describe("Q verify", () => {
  it("Q1 DOCKED (default preset): prefix+f with no docks is invisible, then mod+/ opens a sidecar that stays at 0px", () => {
    const { container } = render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "ctrl+b"); key(document.body, "f");
    const rightDock = container.querySelector<HTMLElement>('[aria-label="Right dock"]')!;
    // eslint-disable-next-line no-console
    console.log("Q1 after prefix+f (no docks): fullscreenPane=", ws().fullscreenPane);
    key(document.body, "mod+/");
    // eslint-disable-next-line no-console
    console.log("Q1 after mod+/: dockRightIds=", JSON.stringify(ws().dockRightIds), "right dock width=", rightDock.style.width);
    expect(rightDock.style.width).not.toBe("0px");
  });

  it("Q2 INSET at lg: focus right, then a left dock opens (right collapses), then prefix+f", () => {
    tierRef.current = "lg";
    ws().setLayoutPreset("omarchy-inset");
    const { container } = render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "mod+/"); // sidecar -> right dock
    key(document.body, "ctrl+b"); key(document.body, "l");
    // eslint-disable-next-line no-console
    console.log("Q2 focusedPane after prefix+l:", ws().focusedPane, "panes=", container.querySelectorAll("[data-pane]").length);
    key(document.body, "ctrl+b"); key(document.body, "b"); // project tree -> left dock
    // eslint-disable-next-line no-console
    console.log("Q2 panes after left dock opens at lg:", container.querySelectorAll("[data-pane]").length, "focusedPane=", ws().focusedPane);
    key(document.body, "ctrl+b"); key(document.body, "f");
    // eslint-disable-next-line no-console
    console.log("Q2 after prefix+f: fullscreenPane=", ws().fullscreenPane, "panes rendered=", container.querySelectorAll("[data-pane]").length);
    expect(container.querySelectorAll("[data-pane]").length).toBeGreaterThan(0);
  });

  it("Q3 ctrl+alt+i pressed while typing in a route field toggles the preset and wipes the typed text", () => {
    const { getByTestId } = render(<PanelLayout mainSlot={<Route />} />);
    const f = getByTestId("field") as HTMLInputElement;
    act(() => { f.focus(); fireEvent.change(f, { target: { value: "unsaved draft" } }); });
    expect((getByTestId("field") as HTMLInputElement).value).toBe("unsaved draft");
    keyRaw(f, { key: "i", code: "KeyI", ctrlKey: true, altKey: true });
    // eslint-disable-next-line no-console
    console.log("Q3 preset=", ws().layoutPreset, "mounts=", mounts, "field value=", JSON.stringify((document.querySelector('[data-testid="field"]') as HTMLInputElement | null)?.value));
    expect((document.querySelector('[data-testid="field"]') as HTMLInputElement).value).toBe("unsaved draft");
  });

  it("Q4 an aria-modal dialog blocks the preset keys (open modal dialogs are NOT reachable by the key path)", () => {
    const { getByTestId } = render(
      <PanelLayout mainSlot={<div role="dialog" aria-modal="true"><button data-testid="in-modal">x</button></div>} />,
    );
    act(() => { (getByTestId("in-modal") as HTMLButtonElement).focus(); });
    keyRaw(getByTestId("in-modal"), { key: "i", code: "KeyI", ctrlKey: true, altKey: true });
    key(getByTestId("in-modal"), "ctrl+b"); key(getByTestId("in-modal"), "i");
    // eslint-disable-next-line no-console
    console.log("Q4 preset after chord+prefix inside aria-modal:", ws().layoutPreset);
    expect(ws().layoutPreset).toBe("docked");
  });

  it("Q5 DOCKED: Esc from body after prefix+f does not restore (layout-root onKeyDown in docked too)", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "ctrl+b"); key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    keyRaw(document.activeElement ?? document.body, { key: "Escape", code: "Escape" });
    // eslint-disable-next-line no-console
    console.log("Q5 docked fullscreenPane after Esc from", document.activeElement?.tagName, "=", ws().fullscreenPane);
    expect(ws().fullscreenPane).toBeNull();
  });

  it("Q6 INSET xl: right-pane fullscreen geometry (width style and where it sits)", () => {
    ws().open("Notes", {}, { mode: "docked-right", id: "p:right", title: "Right" });
    ws().setLayoutPreset("omarchy-inset");
    const { container } = render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "ctrl+b"); key(document.body, "l");
    key(document.body, "ctrl+b"); key(document.body, "f");
    const right = container.querySelector<HTMLElement>('[data-pane="right"]');
    const frame = container.querySelector<HTMLElement>('[data-layout-preset="omarchy-inset"]')!;
    // eslint-disable-next-line no-console
    console.log("Q6 fullscreen=", ws().fullscreenPane, "right width=", right?.style.width, "right class has flex-1:", right?.className.includes("flex-1"), "frame children=", frame.children.length, "frame justify:", frame.className);
    expect(right?.style.width).not.toBe("320px");
  });
});
