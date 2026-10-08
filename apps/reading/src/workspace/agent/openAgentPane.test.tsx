import { awaitWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
/**
 * openAgentPane.test.tsx — SPR-07 J4 by keyboard (repair C1). The REAL
 * dispatcher (installShortcuts) and the REAL PanelLayout in the inset preset:
 * ctrl+alt+a and prefix+a open the selected project's agent pane as a
 * companion tab with focus in its composer; a second press focuses, never
 * duplicates; a left-pane fullscreen is cleared first so the composer is on
 * screen; in writing the outline keeps the right pane and the key does
 * nothing. The companion chunk is lazy, so every assertion waits for it.
 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));
vi.mock("../useViewportTier", () => ({ useViewportTier: () => "xl" }));

import { prefixState } from "../../components/hotkeys/prefixState";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { PanelLayout } from "../PanelLayout";
import { useCompanion } from "../companionStore";
import { useWorkspace } from "../WorkspaceStore";
import { installShortcuts } from "../shortcuts";
import { pinPlatform, press, unpinPlatform } from "../keymapTestKit";
import { agentTabIdFor } from "./agentPaneId";
import { useAgentPaneStore } from "./agentPaneStore";
import { useAgentThreads } from "./agentThreadStore";

beforeAll(() => {
  Element.prototype.getClientRects = function () {
    return (this.closest("[hidden]") ? [] : [{}]) as unknown as DOMRectList;
  };
  Object.defineProperty(window, "matchMedia", {
    writable: true, configurable: true,
    value: (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }),
  });
});

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const comp = () => useCompanion.getState();

beforeEach(async () => {
  setWorkspaceOwner(null);
  setWorkspaceOwner("unit-agent-pane");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  pinPlatform("mac");
  ws().reset();
  ws().setLayoutPreset("omarchy-inset");
  comp().reset();
  useAgentPaneStore.getState().reset();
  useAgentThreads.getState().reset();
  window.sessionStorage.clear();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  try {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  comp().reset();
  useTabTrees.getState().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  } finally { setWorkspaceOwner(null); }
});

function mountInset(path = "/read/doc-1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <PanelLayout mainSlot={<p>route content</p>} />
    </MemoryRouter>,
  );
}

const composer = () => document.querySelector<HTMLTextAreaElement>("[data-agent-pane] textarea");

async function paneWithFocus(): Promise<HTMLTextAreaElement> {
  await waitFor(() => expect(composer()).not.toBeNull(), { timeout: 5000 });
  await waitFor(() => expect(document.activeElement).toBe(composer()));
  return composer()!;
}

describe("the chord opens the pane with focus in the composer (J4 by keyboard)", () => {
  it("ctrl+alt+a from the left pane opens the selected project's agent tab, focus lands in the composer", async () => {
    const { container } = mountInset();
    await waitFor(() => expect(container.querySelector("[data-companion-pane]")).toBeTruthy());
    container.querySelector<HTMLElement>('[data-pane="left"]')!.focus();
    act(() => { press(window, "ctrl+alt+a", "mac"); });
    const textarea = await paneWithFocus();
    const id = agentTabIdFor(`p:${TAB_PROJECT_ID}`);
    const tab = comp().tabs.find((t) => t.id === id);
    expect(tab).toMatchObject({ scope: "project", projectId: TAB_PROJECT_ID, agentId: `p:${TAB_PROJECT_ID}` });
    expect(comp().activeTabId).toBe(id);
    expect(textarea.closest("[data-agent-pane]")!.getAttribute("data-agent-id")).toBe(`p:${TAB_PROJECT_ID}`);
    expect(container.querySelector('[data-pane="right"]')!.contains(textarea)).toBe(true);
  });

  it("prefix+a (ctrl+b, a) opens it too; a second press focuses the same tab and never duplicates", async () => {
    const { container } = mountInset();
    await waitFor(() => expect(container.querySelector("[data-companion-pane]")).toBeTruthy());
    container.querySelector<HTMLElement>('[data-pane="left"]')!.focus();
    act(() => { press(window, "ctrl+b", "mac"); });
    act(() => { press(window, "a", "mac"); });
    const textarea = await paneWithFocus();
    expect(comp().tabs).toHaveLength(1);
    // Focus leaves the composer (the left pane); the chord brings it back
    // without a second tab.
    container.querySelector<HTMLElement>('[data-pane="left"]')!.focus();
    expect(document.activeElement).not.toBe(textarea);
    act(() => { press(window, "ctrl+alt+a", "mac"); });
    await waitFor(() => expect(document.activeElement).toBe(composer()));
    expect(comp().tabs).toHaveLength(1);
  });

  it("a left-pane fullscreen is cleared first, so the composer is on screen, never under [hidden]", async () => {
    const { container } = mountInset();
    await waitFor(() => expect(container.querySelector("[data-companion-pane]")).toBeTruthy());
    act(() => { ws().setFocusedPane("left"); ws().setFullscreenPane("left"); });
    expect(container.querySelector('[data-pane="right"]')!.closest("[hidden]")).not.toBeNull();
    act(() => { press(window, "ctrl+alt+a", "mac"); });
    const textarea = await paneWithFocus();
    expect(ws().fullscreenPane).toBeNull();
    expect(textarea.closest("[hidden]")).toBeNull();
  });

  it("in writing the outline keeps the right pane: the key opens nothing (F7, an honest no-op)", async () => {
    // The dispatcher reads window.location (mothershipForPath); the router
    // drives the layout. Both say "writing" here.
    window.history.pushState({}, "", "/write/piece-1");
    try {
      const { container } = mountInset("/write/piece-1");
      await waitFor(() => expect(container.querySelector('[data-pane="right"]')).toBeTruthy());
      const e = press(window, "ctrl+alt+a", "mac");
      expect(e.defaultPrevented).toBe(false);
      await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
      expect(comp().tabs).toHaveLength(0);
      expect(composer()).toBeNull();
    } finally {
      window.history.pushState({}, "", "/");
    }
  });
});

describe("the #pane=agent:<id> deep link opens the right agent on load (M5, repair C12)", () => {
  it("#pane=agent:p:<selected project> opens that project's pane with the composer focused", async () => {
    mountInset(`/read/doc-1#pane=agent:p:${TAB_PROJECT_ID}`);
    const textarea = await paneWithFocus();
    const id = agentTabIdFor(`p:${TAB_PROJECT_ID}`);
    expect(comp().tabs.find((t) => t.id === id)).toMatchObject({ scope: "project", projectId: TAB_PROJECT_ID, agentId: `p:${TAB_PROJECT_ID}` });
    expect(comp().activeTabId).toBe(id);
    expect(textarea.closest("[data-agent-pane]")!.getAttribute("data-agent-id")).toBe(`p:${TAB_PROJECT_ID}`);
    expect(comp().tabs).toHaveLength(1);
  });

  it("#pane=agent:p:proj-9 (another project) opens that project's tab, active, behind the hidden-tab placeholder — the link never switches the selection (frozen writer census)", async () => {
    const { container } = mountInset("/read/doc-1#pane=agent:p:proj-9");
    await waitFor(() => expect(container.querySelector("[data-agent-hidden-placeholder]")).toBeTruthy(), { timeout: 5000 });
    const id = agentTabIdFor("p:proj-9");
    expect(comp().tabs.find((t) => t.id === id)).toMatchObject({ scope: "project", projectId: "proj-9", agentId: "p:proj-9" });
    expect(comp().activeTabId).toBe(id);
    expect(container.querySelector("[data-agent-hidden-placeholder]")!.textContent).toContain("proj-9");
    expect(composer()).toBeNull();
  });

  it("#pane=agent:x:3 opens that cross-project pane; an unrelated hash opens nothing", async () => {
    mountInset("/read/doc-1#pane=agent:x:3");
    await paneWithFocus();
    expect(comp().tabs.map((t) => t.id)).toEqual([agentTabIdFor("x:3")]);
    expect(comp().tabs[0]).toMatchObject({ scope: "cross-project", agentId: "x:3" });
    cleanup();
    comp().reset();
    const { container } = mountInset("/read/doc-1#other");
    await waitFor(() => expect(container.querySelector("[data-companion-pane]")).toBeTruthy());
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(comp().tabs).toHaveLength(0);
  });
});
