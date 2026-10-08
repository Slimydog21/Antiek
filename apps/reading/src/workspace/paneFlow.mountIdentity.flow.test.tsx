/**
 * paneFlow.mountIdentity.flow.test.tsx — SPR-01 M1 landing, composition proof
 * with the pane-flow flag ON: switching the arrangement (horizontal ⇄ tiled)
 * keeps the route host's DOM node and its scroll position (contract: "Tiled
 * mode retains the same hosts and identities … ratios and topology survive a
 * horizontal roundtrip").
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
vi.hoisted(() => { try { window.localStorage.setItem("antiek.flag.pane.flow", "on"); } catch { /* storage unavailable */ } });

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true, configurable: true,
      value: (query: string) => ({ matches: false, media: query, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false }),
    });
  }
});
vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));
vi.mock("./usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => true }));
vi.mock("./RightPaneForMode", () => ({ default: () => <div data-companion-pane="stub" /> }));

import { PanelLayout } from "./PanelLayout";
import { PaneFlowLayout } from "./PaneFlowLayout";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";

const ws = () => useWorkspace.getState();

function mountScrollableHost() {
  const view = render(
    <PaneFlowLayout>
      <PanelLayout mainSlot={<div data-testid="reader-host" style={{ height: 100, overflow: "auto" }}><div style={{ height: 1000 }}>long document</div></div>} />
    </PaneFlowLayout>,
  );
  const host = view.getByTestId("reader-host");
  host.scrollTop = 120;
  return { view, host };
}

beforeEach(() => { disablePersistence(); ws().reset(); });
afterEach(() => { cleanup(); ws().reset(); });

describe("flag ON — arrangement switches keep the route host mounted", () => {
  it("a fresh user's horizontal default and any chosen arrangement survive reset(), which runs at every sign-in (merged-head check on PR 3754)", () => {
    // Fresh preferences migrate to horizontal, and the store PERSISTS that
    // arrangement at startup; without it the first reset() (the sign-in owner
    // change) would read "preset saved, no arrangement chosen" and fall to
    // legacy. The arrangement key is therefore present before any choice.
    expect(window.localStorage.getItem("antiek.workspace.desktop-pane-arrangement.v1")).not.toBeNull();
    expect(ws().paneArrangement).toBe("horizontal");
    act(() => { ws().reset(); });
    expect(ws().paneArrangement).toBe("horizontal");
    // A chosen arrangement survives too — sign-in, owner switch, "Reset layout".
    act(() => { ws().setPaneArrangement("tiled"); });
    act(() => { ws().reset(); });
    expect(ws().paneArrangement).toBe("tiled");
  });
  it("horizontal → tiled → horizontal keeps the same DOM node and its scrollTop", () => {
    const { host } = mountScrollableHost();
    act(() => { ws().setPaneArrangement("horizontal"); });
    expect(host.scrollTop).toBe(120);
    act(() => { ws().setPaneArrangement("tiled"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
    act(() => { ws().setPaneArrangement("horizontal"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
    expect(host.textContent).toBe("long document");
  });

  it("legacy → horizontal (the operator opting in) keeps the node and scroll", () => {
    const { host } = mountScrollableHost();
    act(() => { ws().setPaneArrangement("legacy"); });
    expect(document.contains(host)).toBe(true);
    act(() => { ws().setPaneArrangement("horizontal"); });
    expect(document.contains(host)).toBe(true);
    expect(host.scrollTop).toBe(120);
  });
});
