/**
 * cockpitB2.keys.test.tsx — lane A stage B2: the critic's round-2 findings
 * on A1 (worktree at 3862455ab) that live in the keys, the close/reopen
 * path and the fullscreen Esc, red-first.
 *
 *   1  prefix+shift+x follows pane focus like n/p: with the RIGHT pane
 *      focused it closes the active AGENT tab (behind the 10 s Undo) and
 *      never prunes the left tab.
 *   2  one Esc reaches exactly one handler: an open overlay takes the Esc
 *      and fullscreen stays; the next Esc exits fullscreen. The tree popover
 *      closes on Esc from any focus, before fullscreen does.
 *   3  Back/Forward to a closed branch's history entry re-spawns it as a
 *      CHILD with its original origin (kept, now under test).
 *   4  closing the last open tab goes to the mode's home, so the screen and
 *      the strip agree.
 *   6  prefix+shift+t reopens the last closed tab of the focused pane:
 *      inside the 10 s hold it undoes; after it, it restores the most recent
 *      retired tab of that side.
 *
 * The dispatcher runs with REAL handlers against the real stores.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { BrowserRouter, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  getDeliverable: vi.fn(async () => {
    throw new Error("HTTP 404");
  }),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

import KeySheet from "../components/hotkeys/KeySheet";
import { KEYMAP, validateKeymap } from "../components/hotkeys/keymap";
import { NOTES } from "../components/hotkeys/keymapView";
import { prefixState } from "../components/hotkeys/prefixState";
import { LemonDropdown } from "../components/lemon/LemonDropdown";
import { LemonModal } from "../components/lemon/LemonModal";
import { LemonSelect } from "../components/lemon/LemonSelect";
import { toast } from "../components/lemon/LemonToast";
import FloatMenu from "../modes/shared/FloatMenu/FloatMenu";
import type { FloatMenuSelection } from "../modes/shared/FloatMenu/useFloatMenuSelection";
import { PanelLayout } from "./PanelLayout";
import { branchNavigation } from "./branchNavigation";
import { COMPANION_PANEL_ID, useCompanion } from "./companionStore";
import { mothershipForPath } from "./documentSpace";
import { useWorkspace } from "./WorkspaceStore";
import { checkInvariants } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
import { createActionHandlers, installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
const comp = () => useCompanion.getState();
const M = () => mothershipForPath(window.location.pathname, window.location.search);
const activeDoc = () => tabs().trees[M()]?.active_tab_id ?? null;
const navRef: { current: NavigateFunction | null } = { current: null };
let uninstall: (() => void) | null = null;

function Probe() {
  const loc = useLocation();
  navRef.current = useNavigate();
  return <span data-testid="location">{loc.pathname + loc.search}</span>;
}
const where = () => screen.getByTestId("location").textContent;

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

function prefixed(k: string): void {
  key(document.body, "ctrl+b");
  key(document.body, k);
}

function esc(target: EventTarget = document.body): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true });
  act(() => {
    target.dispatchEvent(e);
  });
  return e;
}

async function flush(n = 6) {
  for (let i = 0; i < n; i++) await act(async () => {});
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  ws().reset();
  ws().setLayoutPreset("omarchy-inset");
  tabs().resetTabTrees();
  comp().reset();
  uninstall = installShortcuts(((to: unknown) => navRef.current?.(to as string)) as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  vi.useRealTimers();
  vi.restoreAllMocks();
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  comp().reset();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

function mount(path: string, extra: React.ReactNode = null) {
  window.history.replaceState({}, "", path);
  return render(
    <BrowserRouter>
      <Probe />
      <PanelLayout mainSlot={<p>route content</p>} />
      {extra}
    </BrowserRouter>,
  );
}

/** /read/doc-9 with two document children (c1 active, c2) on the left and
 *  two agent tabs (inv-a, inv-b active) on the right. */
async function seedCockpit(preset: "omarchy-inset" | "docked" = "omarchy-inset") {
  ws().setLayoutPreset(preset);
  mount("/read/doc-9");
  await waitFor(() => expect(activeDoc()).not.toBeNull());
  const m = M();
  const rootId = activeDoc()!;
  act(() => {
    tabs().spawnTab(m, rootId, { tab_id: "c1", kind: "reader", ref: "doc-1", mothership: m, activate: false });
    tabs().spawnTab(m, rootId, { tab_id: "c2", kind: "reader", ref: "doc-2", mothership: m, activate: false });
    tabs().activateTab(m, "c1");
    comp().openAgentTab({ kind: "research-thread", investigationId: "inv-a", title: "Question A" });
    comp().openAgentTab({ kind: "research-thread", investigationId: "inv-b", title: "Question B" });
  });
  await flush();
  return { m, rootId };
}

// ─── 1: close follows pane focus ──────────────────────────────────────────

describe("B2-1 prefix+shift+x closes the focused pane's tab", () => {
  it("right pane focused (inset): the active AGENT tab closes behind a 10 s Undo; the left tab stays", async () => {
    const { m } = await seedCockpit();
    const undoSpy = vi.spyOn(toast, "undo");
    act(() => ws().setFocusedPane("right"));
    prefixed("shift+x");
    await waitFor(() => expect(comp().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-a"]));
    // Never a prune of the left tab.
    expect(tabs().trees[m]!.nodes["c1"]).toBeTruthy();
    expect(activeDoc()).toBe("c1");
    expect(tabs().heldClose).toBeNull();
    // The same 10 s Undo the strip's close offers, and it puts the tab back.
    expect(undoSpy).toHaveBeenCalledTimes(1);
    expect(undoSpy.mock.calls[0][0]).toMatch(/Question B/);
    act(() => undoSpy.mock.calls[0][1]());
    expect(comp().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-a", "agent:thread:inv-b"]);
    expect(comp().activeTabId).toBe("agent:thread:inv-b");
  });

  it("docked: a focused companion panel is the right pane, so the agent tab closes", async () => {
    const { m } = await seedCockpit("docked");
    act(() => {
      ws().open("Companion", {}, { mode: "docked-right", title: "Agents", id: COMPANION_PANEL_ID });
      ws().focus(COMPANION_PANEL_ID);
    });
    prefixed("shift+x");
    await waitFor(() => expect(comp().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-a"]));
    expect(tabs().trees[m]!.nodes["c1"]).toBeTruthy();
  });

  it("left pane focused: it still prunes the document tab (unchanged)", async () => {
    const { m } = await seedCockpit();
    act(() => ws().setFocusedPane("left"));
    prefixed("shift+x");
    expect(tabs().trees[m]!.nodes["c1"]).toBeUndefined();
    await flush();
    expect(comp().tabs).toHaveLength(2);
  });

  it("writing, right pane focused: the outline's block tabs cannot close, so nothing closes anywhere", async () => {
    mount("/write/A");
    await waitFor(() => expect(tabs().trees.writing?.active_tab_id ?? null).not.toBeNull());
    const piece = tabs().trees.writing!.active_tab_id!;
    act(() => {
      comp().openAgentTab({ kind: "dialogue" });
      ws().setFocusedPane("right");
    });
    prefixed("shift+x");
    await flush();
    expect(tabs().trees.writing!.nodes[piece]).toBeTruthy();
    expect(tabs().heldClose).toBeNull();
    expect(comp().tabs).toHaveLength(1);
  });
});

// ─── 2: one Esc, one handler ──────────────────────────────────────────────

function DropdownProbe() {
  return (
    <LemonDropdown trigger={<button type="button">More</button>}>
      {({ close }) => (
        <button type="button" role="menuitem" onClick={close}>
          Item
        </button>
      )}
    </LemonDropdown>
  );
}

function SelectProbe() {
  const [v, setV] = useState<string | null>(null);
  return <LemonSelect aria-label="Pick" value={v} onChange={setV} options={[{ value: "a", label: "A" }]} />;
}

function ModalProbe() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open dialog
      </button>
      <LemonModal open={open} onClose={() => setOpen(false)} title="A dialog">
        <p>inside</p>
      </LemonModal>
    </>
  );
}

describe("B2-2 fullscreen Esc: one Esc reaches exactly one handler", () => {
  it("an open LemonDropdown takes the Esc; fullscreen stays; the next Esc exits it", async () => {
    mount("/read/doc-9", <DropdownProbe />);
    await flush();
    act(() => ws().setFullscreenPane("left"));
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.queryByRole("menu")).not.toBeNull();
    act(() => (document.activeElement as HTMLElement | null)?.blur());
    esc();
    await flush();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(ws().fullscreenPane).toBe("left");
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });

  it("an open LemonSelect takes the Esc first", async () => {
    mount("/read/doc-9", <SelectProbe />);
    await flush();
    act(() => ws().setFullscreenPane("left"));
    fireEvent.click(screen.getByRole("combobox", { name: "Pick" }).querySelector("button")!);
    expect(screen.queryByRole("listbox")).not.toBeNull();
    esc();
    await flush();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(ws().fullscreenPane).toBe("left");
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });

  it("an open dialog takes the Esc, even with focus back on body", async () => {
    mount("/read/doc-9", <ModalProbe />);
    await flush();
    act(() => ws().setFullscreenPane("right"));
    fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    act(() => (document.activeElement as HTMLElement | null)?.blur());
    esc();
    await flush();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(ws().fullscreenPane).toBe("right");
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });

  it("the selection FloatMenu takes the Esc first", async () => {
    function FloatHost() {
      const [selection, setSelection] = useState<FloatMenuSelection | null>({
        text: "a passage worth chasing",
        rect: { top: 100, left: 100, width: 80, height: 18 },
        provenance: { documentId: "doc-9", chunkId: null },
      });
      // The host's half: the menu collapses the live selection on Esc, and
      // the host's selectionchange then drops it (emulated here).
      useEffect(() => {
        if (!selection) return;
        const onKey = (e: KeyboardEvent) => {
          if (e.key === "Escape") setSelection(null);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
      }, [selection]);
      return <FloatMenu selection={selection} investigationId="read-doc-9" onDeepResearch={() => {}} />;
    }
    act(() => ws().setFullscreenPane("left"));
    mount("/read/doc-9", <FloatHost />);
    await flush();
    expect(document.querySelector("[data-floatmenu]")).not.toBeNull();
    esc();
    await flush();
    expect(document.querySelector("[data-floatmenu]")).toBeNull();
    expect(ws().fullscreenPane).toBe("left");
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });

  it("the tree panel open during fullscreen, focus on body: Esc closes the panel first", async () => {
    mount("/read/doc-9");
    await waitFor(() => expect(activeDoc()).not.toBeNull());
    await flush();
    act(() => ws().setFullscreenPane("left"));
    act(() => tabs().toggleTreePanel());
    await waitFor(() => expect(document.querySelector("[data-tab-tree-panel]")).not.toBeNull());
    act(() => (document.activeElement as HTMLElement | null)?.blur());
    esc();
    await flush();
    expect(tabs().treePanelOpen).toBe(false);
    expect(ws().fullscreenPane).toBe("left");
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });

  it("with nothing open, one Esc from body exits fullscreen (unchanged)", async () => {
    mount("/read/doc-9");
    await flush();
    act(() => ws().setFullscreenPane("left"));
    esc();
    expect(ws().fullscreenPane).toBeNull();
  });
});

// ─── 3: Back/Forward to a closed branch ───────────────────────────────────

describe("B2-3 Back to a closed branch's history entry re-spawns it as a child", () => {
  it("the entry's branch intent files it under its original parent with its original origin", async () => {
    mount("/read/doc-9");
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const readerRoot = tabs().trees.reading!.active_tab_id!;
    const go = branchNavigation(
      "/inv/new-1",
      { pathname: window.location.pathname, search: window.location.search },
      { document_id: "doc-9", kind: "research", page_index: 2 },
    );
    act(() => navRef.current!(go.to, go.options));
    await flush();
    expect(where()).toBe("/inv/new-1?m=reading");
    const firstChild = tabs().trees.reading!.active_tab_id!;
    expect(tabs().trees.reading!.nodes[firstChild].parent_tab_id).toBe(readerRoot);

    // Close the branch: the reader is shown again (a new history entry).
    act(() => tabs().closeActiveTab("reading", "prune"));
    await flush();
    expect(where()).toBe("/read/doc-9");
    expect(tabs().trees.reading!.nodes[firstChild]).toBeUndefined();

    // Back lands on the closed branch's entry: a CHILD again, not a root.
    act(() => navRef.current!(-1));
    await waitFor(() => expect(where()).toBe("/inv/new-1?m=reading"));
    await flush();
    const reading = tabs().trees.reading!;
    const again = reading.nodes[reading.active_tab_id!];
    expect(again.kind).toBe("research");
    expect(again.ref).toBe("/inv/new-1");
    expect(again.parent_tab_id).toBe(readerRoot);
    expect(again.branch_origin).toEqual({
      document_id: "doc-9",
      kind: "research",
      anchor: { document_id: "doc-9", page_index: 2 },
    });
    expect(reading.root_order).toEqual([readerRoot]);
    expect(checkInvariants(reading)).toEqual([]);
  });
});

// ─── 4: closing the last tab goes home ────────────────────────────────────

describe("B2-4 closing the last open tab shows the mode's home", () => {
  it.each([
    ["/read/doc-9", "/library"],
    ["/inv/inv-1", "/"],
    ["/write/A", "/write"],
  ])("%s → %s", async (path, home) => {
    mount(path);
    await waitFor(() => expect(activeDoc()).not.toBeNull());
    await flush();
    const m = M();
    prefixed("shift+x");
    await flush();
    expect(tabs().trees[m]!.active_tab_id).toBeNull();
    expect(where()).toBe(home);
    // The Undo brings the tab and its route back.
    act(() => tabs().undoLastClose(m));
    await flush();
    expect(where()).toBe(path);
  });

  it("a last tab kept in another mode's tree goes to THAT tree's home", async () => {
    mount("/read/doc-9?m=research");
    await waitFor(() => expect(tabs().trees.research?.active_tab_id ?? null).not.toBeNull());
    await flush();
    prefixed("shift+x");
    await flush();
    expect(where()).toBe("/");
  });
});

// ─── 6: prefix+shift+t reopens ────────────────────────────────────────────

describe("B2-6 prefix+shift+t reopens the focused pane's last closed tab", () => {
  it("the table: tab.reopen is prefix+shift+t alone, and the guard passes", () => {
    const rows = KEYMAP.filter((r) => r.action === ("tab.reopen" as never));
    expect(rows.map((r) => r.prefixKey ?? `chord:${r.chord}`)).toEqual(["shift+t"]);
    const handlerIds = Object.keys(createActionHandlers((() => {}) as never));
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
    expect([...handlerIds].sort()).toEqual([...new Set(KEYMAP.filter((row) => row.status !== "unimplemented").map((row) => row.action))].sort());
  });

  it("the key sheet lists it, with the hold-then-retired rule", () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    const row = document.body.querySelector<HTMLElement>('[data-keymap-action="tab.reopen"]');
    expect(row).not.toBeNull();
    expect(row!.querySelector('[data-keymap-row="prefix-tab-reopen"]')).not.toBeNull();
    expect(NOTES["tab.reopen" as never]).toMatch(/10 seconds/);
  });

  it("left, inside the hold: it undoes the close and nothing is ever written", async () => {
    const { m } = await seedCockpit();
    prefixed("shift+x");
    expect(tabs().heldClose?.token.tab_id).toBe("c1");
    const dismiss = vi.spyOn(toast, "dismiss");
    prefixed("shift+t");
    expect(tabs().heldClose).toBeNull();
    expect(tabs().trees[m]!.nodes["c1"]).toBeTruthy();
    expect(activeDoc()).toBe("c1");
    expect((tabs().pendingOps[m] ?? []).some((op) => op.type === "close")).toBe(false);
    // The toast whose Undo the key just ran goes away.
    expect(dismiss).toHaveBeenCalled();
  });

  it("left, after the hold and its undo window: it restores the most recent retired tab, numbers intact", async () => {
    const { m } = await seedCockpit();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const hier = { c1: tabs().trees[m]!.nodes["c1"].hier_number, c2: tabs().trees[m]!.nodes["c2"].hier_number };
    prefixed("shift+x"); // c1
    act(() => vi.advanceTimersByTime(10_000));
    act(() => tabs().activateTab(m, "c2"));
    prefixed("shift+x"); // c2, the most recent
    act(() => vi.advanceTimersByTime(25_000));
    vi.useRealTimers();
    await flush();
    const before = tabs().trees[m]!;
    expect(before.nodes["c1"]).toBeUndefined();
    expect(before.nodes["c2"]).toBeUndefined();

    prefixed("shift+t");
    const after = tabs().trees[m]!;
    expect(after.nodes["c2"]).toBeTruthy();
    expect(after.nodes["c2"].hier_number).toBe(hier.c2);
    expect(after.active_tab_id).toBe("c2");
    expect(after.nodes["c1"]).toBeUndefined();
    expect(checkInvariants(after)).toEqual([]);
    // The restore is an op the next save (and a rebase) carries.
    expect((tabs().pendingOps[m] ?? []).some((op) => op.type === ("restore" as never))).toBe(true);

    prefixed("shift+t");
    const again = tabs().trees[m]!;
    expect(again.nodes["c1"]?.hier_number).toBe(hier.c1);
    expect(checkInvariants(again)).toEqual([]);
  });

  it("right pane focused: it brings back the last closed agent tab, in place", async () => {
    await seedCockpit();
    act(() => ws().setFocusedPane("right"));
    act(() => comp().activateAgentTab("agent:thread:inv-a"));
    prefixed("shift+x");
    await waitFor(() => expect(comp().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-b"]));
    prefixed("shift+t");
    await waitFor(() =>
      expect(comp().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-a", "agent:thread:inv-b"]),
    );
    expect(comp().activeTabId).toBe("agent:thread:inv-a");
  });

  it("with nothing closed it is an honest no-op", async () => {
    const { m } = await seedCockpit();
    const before = tabs().trees[m];
    prefixed("shift+t");
    await flush();
    expect(tabs().trees[m]).toBe(before);
  });
});


describe("A1c project tree at half-screen width", () => {
  it("opens a named visible dialog, keeps fullscreen, and returns focus after Escape", async () => {
    tierRef.current = "md";
    mount("/read/doc-9");
    await flush();
    const origin = screen.getByRole("region", { name: "Primary pane" });
    act(() => { ws().setFullscreenPane("left"); origin.focus(); });
    prefixed("b");
    const dialog = await screen.findByRole("dialog", { name: "Project" });
    expect(dialog.closest("[hidden]")).toBeNull();
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(ws().fullscreenPane).toBe("left");
    esc(document.activeElement ?? document.body);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull());
    expect(document.activeElement).toBe(origin);
    expect(ws().fullscreenPane).toBe("left");
    esc(origin);
    expect(ws().fullscreenPane).toBeNull();
  });

  it("keeps the tree in the visible dock at lg", async () => {
    tierRef.current = "lg";
    mount("/read/doc-9");
    await flush();
    prefixed("b");
    const tree = await screen.findByRole("region", { name: "Project" });
    expect(tree.closest("[hidden]")).toBeNull();
    expect(tree.closest("aside")?.getAttribute("aria-label")).toBe("Left dock");
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
  });
});


describe("A1c Escape ownership", () => {
  it("a dialog opened over a focused floating panel owns the first Escape", async () => {
    mount("/read/doc-9", <ModalProbe />);
    await flush();
    act(() => ws().open("FakeNotebook", {}, { mode: "floating", title: "Notes", id: "notes" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    esc(document.activeElement ?? document.body);
    await flush();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(ws().panels.notes).toBeDefined();
    const panelTitle = screen.getByRole("group", { name: "Notes — panel controls" });
    act(() => panelTitle.focus());
    esc(panelTitle);
    expect(ws().panels.notes).toBeUndefined();
  });

  it("a select consumes Escape without clearing the selected passage", async () => {
    const clearSelection = vi.spyOn(window.getSelection()!, "removeAllRanges");
    mount("/read/doc-9", <>
      <SelectProbe />
      <FloatMenu selection={{ text: "a passage", rect: { top: 100, left: 100, width: 80, height: 18 }, provenance: { documentId: "doc-9", chunkId: null } }} investigationId="read-doc-9" onDeepResearch={() => {}} />
    </>);
    await flush();
    fireEvent.click(screen.getByRole("combobox", { name: "Pick" }).querySelector("button")!);
    clearSelection.mockClear();
    esc();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(clearSelection).not.toHaveBeenCalled();
    esc();
    expect(clearSelection).toHaveBeenCalledOnce();
  });

  it("the expanded path closes before fullscreen even when focus leaves its list", async () => {
    mount("/read/doc-9");
    await waitFor(() => expect(activeDoc()).not.toBeNull());
    let parent = activeDoc()!;
    act(() => {
      for (let i = 0; i < 5; i++) {
        const id = `path-${i}`;
        tabs().spawnTab("reading", parent, { tab_id: id, kind: "reader", ref: `doc-${i}`, mothership: "reading", activate: true });
        parent = id;
      }
      ws().setFullscreenPane("left");
    });
    await flush();
    const trigger = screen.getByRole("button", { name: /Show the whole path/ });
    fireEvent.click(trigger);
    expect(document.querySelector("[data-tab-path-full]")).not.toBeNull();
    expect(document.querySelector("[data-tab-path-full]")?.contains(document.activeElement)).toBe(true);
    act(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
    esc();
    expect(document.querySelector("[data-tab-path-full]")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(ws().fullscreenPane).toBe("left");
    esc(trigger);
    expect(ws().fullscreenPane).toBeNull();
  });
});


describe("A1c agent-tab close focus", () => {
  it("Delete moves focus from the removed tab to the newly active tab", async () => {
    await seedCockpit();
    const tab = screen.getByRole("tab", { name: /Question B/ });
    tab.focus();
    fireEvent.keyDown(tab, { key: "Delete" });
    await flush();
    expect(screen.queryByRole("tab", { name: /Question B/ })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: /Question A/ }));
  });

  it("closing the last focused agent tab focuses New agent", async () => {
    await seedCockpit();
    act(() => comp().closeAgentTabWithUndo("agent:thread:inv-a"));
    const tab = screen.getByRole("tab", { name: /Question B/ });
    tab.focus();
    fireEvent.keyDown(tab, { key: "Delete" });
    await flush();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /new agent/i }));
  });
});


describe("A1c overlay review regressions", () => {
  it("Project above the agent overflow menu owns the first Escape", async () => {
    tierRef.current = "md";
    await seedCockpit();
    const strip = screen.getByRole("tablist", { name: "Agents" });
    Object.defineProperty(strip, "clientWidth", { configurable: true, value: 160 });
    Object.defineProperty(strip, "scrollWidth", { configurable: true, value: 600 });
    fireEvent.scroll(strip);
    const trigger = screen.getByRole("button", { name: /All agents/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeTruthy();
    prefixed("b");
    const dialog = await screen.findByRole("dialog", { name: "Project" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    esc(document.activeElement ?? document.body);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull());
    expect(screen.getByRole("menu")).toBeTruthy();
    esc(document.activeElement ?? document.body);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("a modal above the path menu owns Escape", async () => {
    mount("/read/doc-9", <ModalProbe />);
    await waitFor(() => expect(activeDoc()).not.toBeNull());
    let parent = activeDoc()!;
    act(() => {
      for (let i = 0; i < 5; i++) {
        const id = `modal-path-${i}`;
        tabs().spawnTab("reading", parent, { tab_id: id, kind: "reader", ref: `doc-${i}`, mothership: "reading", activate: true });
        parent = id;
      }
    });
    await flush();
    fireEvent.click(screen.getByRole("button", { name: /Show the whole path/ }));
    fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
    esc(document.activeElement ?? document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector("[data-tab-path-full]")).not.toBeNull();
    esc();
    expect(document.querySelector("[data-tab-path-full]")).toBeNull();
  });

  it("a modal above a selection menu owns Escape", async () => {
    const clearSelection = vi.spyOn(window.getSelection()!, "removeAllRanges");
    mount("/read/doc-9", <>
      <ModalProbe />
      <FloatMenu selection={{ text: "a passage", rect: { top: 100, left: 100, width: 80, height: 18 }, provenance: { documentId: "doc-9", chunkId: null } }} investigationId="read-doc-9" onDeepResearch={() => {}} />
    </>);
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
    clearSelection.mockClear();
    esc(document.activeElement ?? document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(clearSelection).not.toHaveBeenCalled();
  });

  it("resizing an open Project dialog to phone width leaves a visible focus target", async () => {
    tierRef.current = "md";
    mount("/read/doc-9");
    await flush();
    screen.getByRole("region", { name: "Primary pane" }).focus();
    prefixed("b");
    await screen.findByRole("dialog", { name: "Project" });
    act(() => { tierRef.current = "sm"; ws().setFocusedPane("right"); });
    await flush();
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
    expect(document.activeElement).toBe(document.querySelector("[data-cockpit-content]"));
    expect(document.activeElement).not.toBe(document.body);
  });

  it("closing Project returns focus to the visible pane when its origin was hidden", async () => {
    tierRef.current = "md";
    mount("/read/doc-9");
    await flush();
    screen.getByRole("region", { name: "Primary pane" }).focus();
    prefixed("b");
    await screen.findByRole("dialog", { name: "Project" });
    act(() => ws().setFullscreenPane("right"));
    esc(document.activeElement ?? document.body);
    expect(document.activeElement).toBe(screen.getByRole("region", { name: "Agents pane" }));
    expect(ws().fullscreenPane).toBe("right");
  });
});
