/**
 * paneFlow.mountIdentity.legacy.test.tsx — SPR-01 M1 landing, composition
 * proof asked for by Undertaker v2: with the pane-flow flag OFF (the state
 * every user is in after this PR), switching the cockpit preset keeps the
 * route host's DOM node and its scroll position. 22 files moved since the
 * packet's base; this test is the composition's own evidence, not a
 * cherry-picked one.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true, configurable: true,
      value: (query: string) => ({ matches: false, media: query, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false }),
    });
  }
});
vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));
vi.mock("./RightPaneForMode", () => ({ default: () => <div data-companion-pane="stub" /> }));

import { PanelLayout } from "./PanelLayout";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";

const ws = () => useWorkspace.getState();

function mountScrollableHost() {
  const view = render(
    <PanelLayout mainSlot={<div data-testid="reader-host" style={{ height: 100, overflow: "auto" }}><div style={{ height: 1000 }}>long document</div></div>} />,
  );
  const host = view.getByTestId("reader-host");
  host.scrollTop = 120;
  return { view, host };
}

beforeEach(() => { disablePersistence(); ws().reset(); window.localStorage.clear(); });
afterEach(() => { cleanup(); ws().reset(); });

describe("flag OFF — the cockpit presets keep the route host mounted", () => {
  it("starts legacy", () => {
    expect(ws().paneArrangement).toBe("legacy");
  });

  it("docked → omarchy-inset → docked keeps the same DOM node and its scrollTop", () => {
    const { host } = mountScrollableHost();
    expect(host.scrollTop).toBe(120);
    act(() => { ws().setLayoutPreset("omarchy-inset"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
    act(() => { ws().setLayoutPreset("docked"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
    expect(host.textContent).toBe("long document");
  });

  it("fullscreen on and off keeps the node and scroll", () => {
    const { host } = mountScrollableHost();
    act(() => { ws().setLayoutPreset("omarchy-inset"); ws().setFullscreenPane("left"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
    act(() => { ws().setFullscreenPane(null); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
  });
});
