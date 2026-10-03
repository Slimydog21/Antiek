/** Verifier probes for any head (untracked scratch copy). Lines prefixed "H". */
import { afterEach, beforeAll, beforeEach, describe, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useEffect, useState } from "react";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
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

import { KEYMAP, validateKeymap } from "../components/hotkeys/keymap";
import type { KeymapRow } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { installShortcuts, toggleAISidecar } from "./shortcuts";
import { pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
function key(target: EventTarget, spec: string) { act(() => { press(target, spec, "mac"); }); }
function keyRaw(target: EventTarget, init: KeyboardEventInit) { act(() => { pressKey(target, init); }); }

let mounts = 0;
let paletteToggles = 0;
function Stateful() {
  const [text, setText] = useState("");
  useEffect(() => { mounts += 1; }, []);
  useEffect(() => {
    const on = () => { paletteToggles += 1; };
    window.addEventListener("antiek:palette:toggle", on);
    return () => window.removeEventListener("antiek:palette:toggle", on);
  }, []);
  return <input data-testid="route-input" value={text} onChange={(e) => setText(e.target.value)} />;
}
function typeDraft(input: HTMLInputElement) {
  act(() => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, "draft");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => { input.blur(); });
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  ws().reset();
  ws().setLayoutPreset("docked");
  uninstall = installShortcuts(vi.fn() as never);
  mounts = 0;
  paletteToggles = 0;
});
afterEach(() => {
  uninstall?.(); uninstall = null; cleanup(); prefixState.disarm();
  ws().reset(); ws().setLayoutPreset("docked");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  unpinPlatform(); document.body.innerHTML = "";
});

function openTwo() {
  ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
  ws().open("Notes", {}, { mode: "docked-right", id: "p:right", title: "Right" });
}
const tree = () => <PanelLayout mainSlot={<Stateful />} />;
function mount() { return render(tree()); }
const panes = (c: HTMLElement) => c.querySelectorAll("[data-pane]").length;

describe("verifier probes (any head)", () => {
  it("H1 right-pane fullscreen", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { container, getByTestId } = mount();
    typeDraft(getByTestId("route-input") as HTMLInputElement);
    key(document.body, "ctrl+b"); key(document.body, "l");
    key(document.body, "ctrl+b"); key(document.body, "f");
    const right = container.querySelector<HTMLElement>('[data-pane="right"]');
    console.log("H1 fullscreen=", ws().fullscreenPane, "right width=", right?.style.width,
      "right shrink-0=", right?.className.includes("shrink-0"),
      "mainSlot present=", !!container.querySelector('[data-testid="route-input"]'));
    key(document.body, "mod+k");
    console.log("H1 palette toggles while right fullscreen=", paletteToggles);
    key(document.body, "ctrl+b"); key(document.body, "f");
    const after = container.querySelector<HTMLInputElement>('[data-testid="route-input"]');
    console.log("H1 after restore text=", JSON.stringify(after?.value), "mounts=", mounts);
  });

  it("H2 preset toggle remounts", () => {
    openTwo();
    const { container, getByTestId } = mount();
    const input = getByTestId("route-input") as HTMLInputElement;
    typeDraft(input);
    key(document.body, "ctrl+b"); key(document.body, "i");
    const after = container.querySelector<HTMLInputElement>('[data-testid="route-input"]');
    console.log("H2 preset=", ws().layoutPreset, "mounts=", mounts, "same node=", after === input, "text=", JSON.stringify(after?.value));
  });

  it("H3 docked default: prefix+f with no docks, then mod+/ sidecar", () => {
    const { container } = mount();
    key(document.body, "ctrl+b"); key(document.body, "f");
    console.log("H3 fullscreen after f with no docks=", ws().fullscreenPane);
    act(() => { toggleAISidecar(); });
    const rd = container.querySelector<HTMLElement>('[aria-label="Right dock"]');
    console.log("H3 dockRightIds=", JSON.stringify(ws().dockRightIds), "right dock width=", rd?.style.width);
  });

  it("H4 stale focusedPane across a tier change", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { container, rerender } = mount();
    key(document.body, "ctrl+b"); key(document.body, "l");
    console.log("H4 focusedPane=", ws().focusedPane);
    tierRef.current = "md";
    rerender(tree());
    console.log("H4 md panes before f=", panes(container));
    key(document.body, "ctrl+b"); key(document.body, "f");
    console.log("H4 fullscreen=", ws().fullscreenPane, "panes=", panes(container),
      "mainSlot present=", !!container.querySelector('[data-testid="route-input"]'));
  });

  it("H4b stale focusedPane after closing the right panel (xl)", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { container } = mount();
    key(document.body, "ctrl+b"); key(document.body, "l");
    act(() => { ws().close("p:right"); });
    key(document.body, "ctrl+b"); key(document.body, "f");
    console.log("H4b fullscreen=", ws().fullscreenPane, "panes=", panes(container),
      "mainSlot present=", !!container.querySelector('[data-testid="route-input"]'));
  });

  it("H5 Esc from body", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    mount();
    key(document.body, "ctrl+b"); key(document.body, "f");
    keyRaw(document.body, { key: "Escape", code: "Escape" });
    console.log("H5 active=", document.activeElement?.tagName, "fullscreen after Esc on body=", ws().fullscreenPane);
  });

  it("H6 ring and role", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { container, queryByRole } = mount();
    key(document.body, "ctrl+b"); key(document.body, "h");
    const b = document.createElement("button");
    document.body.appendChild(b);
    act(() => { b.focus(); });
    const left = container.querySelector<HTMLElement>('[data-pane="left"]')!;
    console.log("H6 ring stays=", left.className.includes("ring-focus"), "role=", left.getAttribute("role"),
      "region found=", !!queryByRole("region", { name: "Primary pane" }));
  });

  it("H7 lg/md pane counts", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    tierRef.current = "lg";
    const a = mount();
    console.log("H7 lg panes=", panes(a.container));
    a.unmount();
    tierRef.current = "md";
    const b = mount();
    console.log("H7 md panes=", panes(b.container));
  });

  it("H8 validateKeymap and reserved rows", () => {
    const extra: KeymapRow[] = [
      { id: "probe-f", action: "palette.toggle", chord: "mod+f", scope: "anywhere", origin: "legacy-SPR-08" },
      { id: "probe-left", action: "palette.toggle", chord: "mod+arrowleft", scope: "anywhere", origin: "legacy-SPR-08" },
    ];
    const handlers = [...new Set(KEYMAP.map((r) => r.action))];
    console.log("H8 probes=", JSON.stringify(validateKeymap([...KEYMAP, ...extra], handlers)));
    const rows = KEYMAP.filter((r) => ["f", "i", "shift+i"].includes(r.prefixKey ?? "") || ["ctrl+alt+f", "ctrl+alt+i"].includes(r.chord ?? ""));
    console.log("H8 f/i rows=", JSON.stringify(rows.map((r) => [r.id, r.action, r.prefixKey ?? r.chord])));
  });
});
