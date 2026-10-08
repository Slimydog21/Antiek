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
  it("a chosen arrangement survives reset(), which runs at every sign-in (merged-head check on #3754)", () => {
    // The packet's migration: a persisted layout preset with no arrangement
    // choice stays legacy (the store's startup write persisted a preset), so
    // a fresh store reads legacy even with the flag on …
    expect(ws().paneArrangement).toBe("legacy");
    // … and once the operator chooses tiled (persisted by setPaneArrangement),
    // a reset() — sign-in, owner switch, "Reset layout" — restores TILED from
    // the persisted preference, never a hardcoded legacy.
    act(() => { ws().setPaneArrangement("tiled"); });
    expect(ws().paneArrangement).toBe("tiled");
    act(() => { ws().reset(); });
    expect(ws().paneArrangement).toBe("tiled");
    act(() => { ws().setPaneArrangement("horizontal"); ws().reset(); });
    expect(ws().paneArrangement).toBe("horizontal");
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
