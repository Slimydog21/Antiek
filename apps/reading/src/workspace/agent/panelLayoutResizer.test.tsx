/** panelLayoutResizer.test.tsx — SPR-07 M5: PanelLayout hosts the resizer between the inset panes, and only there. */
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("../useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

import { awaitWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { isConfirmedAgentOwner } from "./turnLifecycle";

import { PanelLayout } from "../PanelLayout";
import { useWorkspace } from "../WorkspaceStore";
import { usePaneWidthStore } from "./paneWidthStore";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true, configurable: true,
    value: (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }),
  });
});
beforeEach(async () => {
  setWorkspaceOwner(null);
  setWorkspaceOwner("panel-layout-resizer-unit-owner");
  const owner = workspaceOwnerSession();
  expect(await awaitWorkspaceOwnerSession(owner)).toBe(true);
  await waitFor(() => {
    expect(isConfirmedAgentOwner(owner)).toBe(true);
    expect(usePaneWidthStore.getState().ready).toBe(true);
  });
  tierRef.current = "xl"; useWorkspace.getState().reset(); useWorkspace.getState().setLayoutPreset("omarchy-inset"); usePaneWidthStore.getState().reset(); window.localStorage.clear();
});
afterEach(() => {
  try {
    cleanup(); useWorkspace.getState().reset(); useWorkspace.getState().setLayoutPreset("docked"); window.localStorage.removeItem("antiek.workspace.layout-preset");
  } finally {
    setWorkspaceOwner(null);
  }
});

const SEP = '[role="separator"][aria-label="Resize the agents pane"]';
function mount(path = "/read/doc-1") {
  return render(<MemoryRouter initialEntries={[path]}><PanelLayout mainSlot={<p>route</p>} /></MemoryRouter>);
}

describe("PanelLayout × PaneResizer", () => {
  it("renders the separator between the panes in the inset; ArrowLeft widens the right pane by 32 px; the right pane carries the controlled id", async () => {
    const { container } = mount();
    await waitFor(() => expect(container.querySelector(SEP)).not.toBeNull());
    const right = container.querySelector<HTMLElement>('[data-pane="right"]')!;
    expect(right.id).toBe("cockpit-right-pane");
    expect(right.style.width).toBe("320px");
    fireEvent.keyDown(container.querySelector(SEP)!, { key: "ArrowLeft" });
    expect(container.querySelector<HTMLElement>('[data-pane="right"]')!.style.width).toBe("352px");
    expect(container.querySelector<HTMLElement>('[data-pane="right"]')!.className).toContain("transition-[width]");
    // Order: left pane, separator, right pane.
    const kids = [...container.querySelector("[data-layout-preset]")!.children];
    expect(kids.indexOf(container.querySelector(SEP)!)).toBe(kids.indexOf(right) - 1);
  });

  it("is absent while a pane is fullscreen, in writing, and at tier sm", async () => {
    const { container } = mount();
    await waitFor(() => expect(container.querySelector(SEP)).not.toBeNull());
    act(() => useWorkspace.getState().setFullscreenPane("left"));
    expect(container.querySelector(SEP)).toBeNull();
    act(() => useWorkspace.getState().setFullscreenPane(null));
    await waitFor(() => expect(container.querySelector(SEP)).not.toBeNull());
    cleanup();
    const writing = mount("/write/d-1");
    await waitFor(() => expect(writing.container.querySelector('[data-pane="right"]')).not.toBeNull());
    await act(async () => { await Promise.resolve(); });
    expect(writing.container.querySelector(SEP)).toBeNull();
    cleanup();
    tierRef.current = "sm";
    const sm = mount();
    expect(sm.container.querySelector(SEP)).toBeNull();
  });

  it("the docked preset has no separator", async () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const { container } = mount();
    await act(async () => { await Promise.resolve(); });
    expect(container.querySelector(SEP)).toBeNull();
  });
});
