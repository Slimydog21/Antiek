/**
 * GearSwitch.test.tsx — SPR-04 M2/M3/M4/M5: the surface, driven by real
 * KeyboardEvents through the real dispatcher with the real stores (the
 * in-memory tab tree adapter, useSelection, the context tree store fed by
 * the real pre-backend feeder over a stubbed fetch, useCompanion,
 * useWorkspace). Verifier lenses from the sprint page: gear truthfulness
 * (a stale tree never shows a selection that is not in it) and modal scope
 * (typing never reaches an editor underneath).
 */
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { prefixState } from "../../components/hotkeys/prefixState";
import { setFeatureFlag } from "../../lib/featureFlags";
import { PROJECTS, SUMMARIES_ACYCLIC, tabs as fixtureTabs } from "../contracts/fixtures.test.helpers";
import { useSelection } from "../contracts/selection";
import { EMPTY_TREE, useContextTreeStore } from "../contracts/treeStore";
import { useCompanion } from "../companionStore";
import { readKeyboardOwnership } from "../keyboardOwnership";
import { pinPlatform, press, unpinPlatform } from "../keymapTestKit";
import { clearTabProject } from "../persistence";
import { focusContext, installShortcuts, toggleGearSwitch } from "../shortcuts";
import { createInMemoryTabTreeAdapter } from "../tabTree";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { useWorkspace } from "../WorkspaceStore";
import { GearSwitchHost } from "./GearSwitchHost";
import { BrowserRouter } from "react-router-dom";
import { DocumentTabStrip } from "../DocumentTabStrip";
import { ProjectPicker } from "../ProjectPicker";

const dialog = () => document.querySelector<HTMLElement>('[data-gear-switch]');
const chip = (root: ParentNode = document) => root.querySelector<HTMLButtonElement>("[data-gear-chip]")!;
const tabsIn = (root: ParentNode) => [...root.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
const cursorTab = () => dialog()!.querySelector<HTMLButtonElement>('[role="tab"][tabindex="0"]');
const tabbables = (root: ParentNode) => [...root.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])')].filter((el) => el.tabIndex >= 0);

function respond(body: unknown, status = 200) {
  return Promise.resolve({ ok: status < 300, status, json: async () => body, text: async () => JSON.stringify(body) } as Response);
}

/** The pre-backend feeder's two reads, answered from the shared fixtures. */
function stubApi(opts: { hang?: boolean } = {}) {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    const url = String(input);
    if (opts.hang) return new Promise<Response>(() => {});
    if (/\/projects(\?|$)/.test(url)) return respond({ projects: PROJECTS });
    if (/\/investigations(\?|$)/.test(url)) return respond({ count: SUMMARIES_ACYCLIC.length, investigations: SUMMARIES_ACYCLIC });
    return respond({}, 404);
  });
}

async function keys(...specs: string[]) {
  await act(async () => {
    for (const spec of specs) press(window, spec, "mac");
  });
}

async function key(target: EventTarget, init: KeyboardEventInit) {
  let e!: KeyboardEvent;
  await act(async () => {
    e = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    target.dispatchEvent(e);
  });
  return e;
}

async function mountTopbar(ui = <GearSwitchHost surface="topbar" />) {
  const r = render(ui);
  await waitFor(() => expect(chip()).toBeTruthy(), { timeout: 5000 });
  await waitFor(() => expect(useContextTreeStore.getState().tree.status).toBe("ready"));
  return r;
}

async function open() {
  await act(async () => toggleGearSwitch());
  await waitFor(() => expect(dialog()).toBeTruthy());
}

function resetStores() {
  const t = useTabTrees.getState();
  t.resetTabTrees();
  t.setTabTreeAdapter(createInMemoryTabTreeAdapter());
  t.selectProject(TAB_PROJECT_ID);
  clearTabProject();
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
}

// The host lazy-loads the surface; the first transform of that chunk
// takes longer than a waitFor, so warm the module cache once.
beforeAll(() => import("./GearSwitch"));

beforeEach(() => {
  pinPlatform("mac");
  setFeatureFlag("nav.switcher", true);
  resetStores();
  stubApi();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setFeatureFlag("nav.switcher", null);
  document.documentElement.removeAttribute("data-motion");
  prefixState.disarm();
  resetStores();
  unpinPlatform();
  document.body.innerHTML = "";
});

describe("M2 — the surface: a11y, focus, notch, hygiene", () => {
  it("closed: one chip, one tabbable, aria-haspopup dialog; open: a modal dialog owning gear.toggle with a level-1 tablist", async () => {
    await mountTopbar();
    expect(tabbables(document.body)).toHaveLength(1);
    expect(chip().getAttribute("aria-haspopup")).toBe("dialog");
    expect(chip().getAttribute("aria-expanded")).toBe("false");
    expect(chip().textContent).toContain("Default project");
    await open();
    const d = dialog()!;
    expect(d.getAttribute("role")).toBe("dialog");
    expect(d.getAttribute("aria-modal")).toBe("true");
    expect(d.getAttribute("aria-label")).toBe("Switch gear");
    expect(d.getAttribute("data-keymap-owner")).toBe("gear.toggle");
    expect(d.getAttribute("data-gear")).toBe("1");
    expect(chip().getAttribute("aria-expanded")).toBe("true");
    expect(chip().getAttribute("aria-controls")).toBe(d.id);
    const list = d.querySelector('[role="tablist"]')!;
    expect(list.getAttribute("aria-level")).toBe("1");
    expect(list.getAttribute("aria-orientation")).toBe("horizontal");
    expect(list.getAttribute("aria-label")).toBe("Projects");
    const tabs = tabsIn(d);
    expect(tabs.map((t) => t.textContent)).toEqual(["Default project", "Varda diligence", "Second project"]);
    expect(tabs.filter((t) => t.tabIndex === 0)).toHaveLength(1);
    expect(document.activeElement).toBe(cursorTab());
    expect(cursorTab()!.getAttribute("aria-selected")).toBe("true");
    expect(tabs.map((t) => t.id)).toEqual(["gear-tab-project-default", "gear-tab-project-p1", "gear-tab-project-p2"]);
    expect(focusContext(document.activeElement)).toEqual({ kind: "modal", owner: "gear.toggle", text: false });
    // The hop keeps the roving tabindex and the focus on one tab.
    await key(d, { key: "ArrowRight" });
    expect(cursorTab()!.id).toBe("gear-tab-project-p1");
    expect(document.activeElement).toBe(cursorTab());
    expect(tabsIn(d).filter((t) => t.tabIndex === 0)).toHaveLength(1);
    expect(d.textContent).toContain("Gear 1 of 3");
  });

  it("outside mousedown closes and restores the opener's focus", async () => {
    await mountTopbar();
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    await open();
    expect(document.activeElement).not.toBe(opener);
    await act(async () => { fireEvent.mouseDown(document.querySelector("[data-gear-backdrop]")!); });
    await waitFor(() => expect(dialog()).toBeNull());
    expect(document.activeElement).toBe(opener);
    expect(chip().getAttribute("aria-expanded")).toBe("false");
  });

  it("Escape reaches the gear.escape owner while focus is inside, and not when it is outside", async () => {
    await mountTopbar();
    await open();
    expect(readKeyboardOwnership().registrations.filter((r) => r.id === "gear.escape")).toHaveLength(1);
    const outside = document.createElement("input");
    document.body.append(outside);
    outside.focus();
    await key(window, { key: "Escape" });
    expect(dialog()).toBeTruthy();
    cursorTab()!.focus();
    await key(window, { key: "Escape" });
    await waitFor(() => expect(dialog()).toBeNull());
    expect(readKeyboardOwnership().registrations.filter((r) => r.id === "gear.escape")).toHaveLength(0);
  });

  it("the notch sets on an accepted key and clears after the fast beat; never under reduced motion", async () => {
    await mountTopbar();
    await open();
    vi.useFakeTimers();
    const d = dialog()!;
    expect(vi.getTimerCount()).toBe(0);
    expect(d.getAttribute("data-notch")).toBeNull();
    await key(d, { key: "ArrowRight" });
    expect(d.getAttribute("data-notch")).toBe("true");
    await act(async () => { vi.advanceTimersByTime(79); });
    expect(d.getAttribute("data-notch")).toBe("true");
    await act(async () => { vi.advanceTimersByTime(1); });
    expect(d.getAttribute("data-notch")).toBeNull();
    // Backspace at gear 1 is the clunk at the end of travel: a notch too.
    await key(d, { key: "Backspace" });
    expect(d.getAttribute("data-notch")).toBe("true");
    await act(async () => { vi.advanceTimersByTime(80); });
    expect(d.getAttribute("data-notch")).toBeNull();
    document.documentElement.setAttribute("data-motion", "reduce");
    await key(d, { key: "ArrowLeft" });
    expect(d.getAttribute("data-notch")).toBeNull();
    // jsdom's HTMLElement.focus() queues a 0 ms selectionchange tick through
    // the fake clock (Selection-impl._associateRange); the notch timer is
    // 80 ms, so flushing 0 ms leaves only ours, and there must be none.
    vi.advanceTimersByTime(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("unmount mid-interaction leaves no timer, no owner attribute and no gear.escape registration", async () => {
    const r = await mountTopbar();
    await open();
    vi.useFakeTimers();
    await key(dialog()!, { key: "ArrowRight" });
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    r.unmount();
    vi.advanceTimersByTime(0); // jsdom's selectionchange tick from the opener-focus restore
    expect(vi.getTimerCount()).toBe(0);
    expect(document.querySelector("[data-keymap-owner]")).toBeNull();
    expect(readKeyboardOwnership().registrations.some((x) => x.id === "gear.escape")).toBe(false);
  });

  it("zen budget: the zen host is one click-only chip (one tabbable) that reads the store's state", async () => {
    render(<GearSwitchHost surface="zen" />);
    await waitFor(() => expect(chip()).toBeTruthy());
    expect(tabbables(document.body)).toHaveLength(1);
    expect(document.querySelector("[data-gear-switch]")).toBeNull();
    // No feeder is mounted by a zen chip: the tree is honestly unfed.
    expect(useContextTreeStore.getState().tree).toBe(EMPTY_TREE);
    expect(chip().textContent).toBe("Projects not loaded");
  });

  it("two hosts: one toggle opens exactly one dialog (the topbar's); the zen chip opens the same one; a zen unmount leaves it open", async () => {
    await mountTopbar(<div data-host="topbar"><GearSwitchHost surface="topbar" /></div>);
    const zenRoot = document.createElement("div");
    zenRoot.dataset.host = "zen";
    document.body.append(zenRoot);
    const zen = render(<GearSwitchHost surface="zen" />, { container: zenRoot });
    await waitFor(() => expect(chip(zenRoot)).toBeTruthy());
    expect(document.querySelectorAll("[data-gear-chip]")).toHaveLength(2);
    expect(chip(zenRoot).textContent).toBe(chip(document.querySelector('[data-host="topbar"]')!).textContent);
    await open();
    expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    expect(dialog()!.closest('[data-host="topbar"]')).toBeTruthy();
    expect(zenRoot.querySelector('[role="dialog"]')).toBeNull();
    await act(async () => { fireEvent.click(chip(zenRoot)); });
    await waitFor(() => expect(dialog()).toBeNull());
    await act(async () => { fireEvent.click(chip(zenRoot)); });
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    zen.unmount();
    expect(dialog()).toBeTruthy();
    expect(document.querySelectorAll("[data-gear-chip]")).toHaveLength(1);
  });

  it("feed: the topbar host mounts the one feeder (loading at once); its last unmount returns the tree to EMPTY_TREE", async () => {
    stubApi({ hang: true });
    const r = render(<GearSwitchHost surface="topbar" />);
    await waitFor(() => expect(chip()).toBeTruthy());
    expect(useContextTreeStore.getState().tree.status).toBe("loading");
    expect(chip().textContent).toBe("Loading projects");
    r.unmount();
    expect(useContextTreeStore.getState().tree).toBe(EMPTY_TREE);
  });

  it("chip copy: a stale persisted project shows the status, never a name that is not in the tree", async () => {
    await mountTopbar();
    expect(chip().textContent).toContain("Default project");
    await act(async () => { useTabTrees.getState().selectProject("ghost"); });
    expect(useSelection.getState().selection.projectId).toBe("ghost");
    expect(chip().textContent).toBe("Project not in the list");
    await open();
    expect(dialog()!.textContent).toContain("Project not in the list");
    expect(tabsIn(dialog()!).every((t) => t.getAttribute("aria-selected") === "false")).toBe(true);
    expect(tabsIn(dialog()!)).toHaveLength(3);
  });

  it("gear 1 Enter on the current project clicks into gear 2 (Investigations, never Sub-projects); an empty gear 2 says why", async () => {
    await mountTopbar();
    await open();
    await key(dialog()!, { key: "Enter" });
    expect(dialog()!.getAttribute("data-gear")).toBe("2");
    const list = dialog()!.querySelector('[role="tablist"]')!;
    expect(list.getAttribute("aria-level")).toBe("2");
    expect(list.getAttribute("aria-label")).toBe("Investigations");
    expect(dialog()!.textContent).not.toContain("Sub-project");
    expect(tabsIn(dialog()!).map((t) => t.id)).toEqual(["gear-tab-subproject-inv-root", "gear-tab-subproject-inv-orphan", "gear-tab-subproject-inv-member"]);
    expect(document.activeElement).toBe(cursorTab());
    await key(dialog()!, { key: "Backspace" });
    expect(dialog()!.getAttribute("data-gear")).toBe("1");
    expect(cursorTab()!.id).toBe("gear-tab-project-default");
  });
});

describe("M3 — the keymap rows through the real dispatcher", () => {
  let uninstall: (() => void) | null = null;
  const calls: Record<string, number> = {};
  const counted = (id: string) => () => { calls[id] = (calls[id] ?? 0) + 1; };

  beforeEach(() => {
    for (const k of Object.keys(calls)) delete calls[k];
    uninstall = installShortcuts(vi.fn() as never, {
      handlers: { "pane.focusLeft": counted("pane.focusLeft"), "pane.focusRight": counted("pane.focusRight"), "tab.next": counted("tab.next") },
    });
  });
  afterEach(() => {
    uninstall?.();
    uninstall = null;
  });

  it("ctrl+alt+shift+w opens the switch and closes it again; prefix+w (ctrl+b, w) opens it too", async () => {
    await mountTopbar();
    await keys("ctrl+alt+shift+w");
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(document.activeElement).toBe(cursorTab());
    await keys("ctrl+alt+shift+w");
    await waitFor(() => expect(dialog()).toBeNull());
    await keys("ctrl+b", "w");
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(prefixState.isArmed()).toBe(false);
  });

  it("from a textarea the prefix does nothing and the chord still opens", async () => {
    await mountTopbar();
    const area = document.createElement("textarea");
    document.body.append(area);
    area.focus();
    await keys("ctrl+b", "w");
    expect(dialog()).toBeNull();
    expect(prefixState.isArmed()).toBe(false);
    await keys("ctrl+alt+shift+w");
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(dialog()!.contains(document.activeElement)).toBe(true);
  });

  it("modal scope: with the switch open, ctrl+alt+h never reaches pane.focusLeft, ctrl+b never arms, and a textarea beneath receives nothing", async () => {
    await mountTopbar();
    const area = document.createElement("textarea");
    area.setAttribute("aria-label", "beneath");
    document.body.append(area);
    area.focus();
    await keys("ctrl+alt+shift+w");
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(focusContext(document.activeElement)).toEqual({ kind: "modal", owner: "gear.toggle", text: false });
    await keys("ctrl+alt+h", "ctrl+alt+l", "ctrl+alt+]");
    expect(calls).toEqual({});
    await keys("ctrl+b");
    expect(prefixState.isArmed()).toBe(false);
    expect(document.querySelector("[data-prefix-chip], [data-prefix-armed]")).toBeNull();
    await keys("ctrl+b", "h");
    expect(calls).toEqual({});
    expect(dialog()).toBeTruthy();
    // Keys land on the focused tab, never on the editor underneath.
    for (const k of ["a", "b", "ArrowRight"]) await key(document.activeElement!, { key: k });
    expect(document.activeElement?.tagName).toBe("BUTTON");
    expect(dialog()!.contains(document.activeElement)).toBe(true);
    expect(area.value).toBe("");
    expect(area).not.toBe(document.activeElement);
    // The chord closes it and focus returns to the textarea.
    await keys("ctrl+alt+shift+w");
    await waitFor(() => expect(dialog()).toBeNull());
    expect(document.activeElement).toBe(area);
  });

  it("the flag off: the key is inert and nothing mounts", async () => {
    setFeatureFlag("nav.switcher", false);
    render(<GearSwitchHost surface="topbar" />);
    await act(async () => {});
    expect(document.querySelector("[data-gear-chip]")).toBeNull();
    await keys("ctrl+alt+shift+w");
    await act(async () => {});
    expect(document.querySelector("[data-gear-switch]")).toBeNull();
    expect(document.querySelector("[data-gear-chip]")).toBeNull();
  });
});

describe("M4 — gear actions through the surface", () => {
  let uninstall: (() => void) | null = null;
  beforeEach(() => {
    uninstall = installShortcuts(vi.fn() as never);
  });
  afterEach(() => {
    uninstall?.();
    uninstall = null;
  });

  it("gear 1 Enter on another project opens the picker with that row focused; Enter there picks it and the switch clicks into gear 2", async () => {
    await mountTopbar(<><GearSwitchHost surface="topbar" /><ProjectPicker /></>);
    await open();
    await key(dialog()!, { key: "ArrowRight" });
    expect(cursorTab()!.id).toBe("gear-tab-project-p1");
    await key(dialog()!, { key: "Enter" });
    const picker = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-keymap-owner="project.select"]');
      expect(el).toBeTruthy();
      return el!;
    });
    expect(dialog()).toBeTruthy(); // the switch stays open beneath
    const row = await waitFor(() => {
      const b = [...picker.querySelectorAll("button")].find((x) => x.textContent?.includes("Varda diligence"));
      expect(b).toBeTruthy();
      return b!;
    });
    await waitFor(() => expect(document.activeElement).toBe(row));
    await act(async () => { fireEvent.click(row); });
    await waitFor(() => expect(document.querySelector('[data-keymap-owner="project.select"]')).toBeNull());
    expect(useTabTrees.getState().projectId).toBe("p1");
    await waitFor(() => expect(dialog()!.getAttribute("data-gear")).toBe("2"));
    expect(dialog()!.querySelector('[role="tablist"]')!.getAttribute("aria-label")).toBe("Investigations");
    expect(dialog()!.textContent).toContain("Investigations aren't linked to projects yet");
    expect(dialog()!.contains(document.activeElement)).toBe(true);
    expect(focusContext(document.activeElement).kind).toBe("modal");
  });

  it("gear 2 Enter keeps the dialog open: after the strip consumes the navIntent, focus is still inside and the context is modal", async () => {
    window.history.replaceState({}, "", "/");
    await mountTopbar(<BrowserRouter><GearSwitchHost surface="topbar" /><DocumentTabStrip /></BrowserRouter>);
    await open();
    await key(dialog()!, { key: "Enter" });
    expect(dialog()!.getAttribute("data-gear")).toBe("2");
    expect(cursorTab()!.id).toBe("gear-tab-subproject-inv-root");
    await key(dialog()!, { key: "Enter" });
    await waitFor(() => expect(useTabTrees.getState().trees.research?.root_order).toEqual(["root:research:/inv/inv-root"]));
    await waitFor(() => expect(useTabTrees.getState().navIntent).toBeNull());
    await waitFor(() => expect(window.location.pathname).toBe("/inv/inv-root"));
    expect(useSelection.getState().selection).toEqual({ projectId: "default", subProjectId: "inv-root" });
    expect(dialog()).toBeTruthy();
    expect(dialog()!.getAttribute("data-gear")).toBe("3");
    expect(dialog()!.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(cursorTab());
    expect(focusContext(document.activeElement)).toEqual({ kind: "modal", owner: "gear.toggle", text: false });
  });

  /** The companion's real tabs (the feed reads useCompanion, not a fixture list). */
  function openCompanionTabs() {
    for (const t of fixtureTabs()) {
      useCompanion.getState().openAgentTab({ kind: t.kind, title: t.title, ...(t.investigationId ? { investigationId: t.investigationId } : {}), ...(t.documentId ? { documentId: t.documentId } : {}) });
    }
  }

  it("gear 3: drill to depth 3, then Backspace lands focus on the gear-2 tab that is selected", async () => {
    openCompanionTabs();
    await mountTopbar();
    await open();
    await key(dialog()!, { key: "Enter" }); // gear 2, inv-root
    await key(dialog()!, { key: "Enter" }); // gear 3 under inv-root
    await waitFor(() => expect(useSelection.getState().selection.subProjectId).toBe("inv-root"));
    await waitFor(() => expect(cursorTab()!.id).toBe("gear-tab-subproject-inv-child-2"));
    expect(dialog()!.querySelector('[role="tablist"]')!.getAttribute("aria-level")).toBe("3");
    expect(tabsIn(dialog()!).map((t) => t.id)).toEqual([
      "gear-tab-subproject-inv-child-2", "gear-tab-subproject-inv-child",
      "gear-tab-agent-inv-child", "gear-tab-agent-agent:dialogue", "gear-tab-agent-inv-unknown", "gear-tab-agent-inv-member",
    ]);
    expect(dialog()!.textContent).toContain("Across projects");
    await key(dialog()!, { key: "ArrowRight" });
    await key(dialog()!, { key: "Enter" }); // drill into inv-child (depth 3 on the path)
    await waitFor(() => expect(useSelection.getState().selection.subProjectId).toBe("inv-child"));
    expect(dialog()!.getAttribute("data-gear")).toBe("3");
    await waitFor(() => expect(tabsIn(dialog()!).map((t) => t.id)).toEqual([
      "gear-tab-agent-inv-child", "gear-tab-agent-agent:dialogue", "gear-tab-agent-inv-unknown", "gear-tab-agent-inv-member",
    ]));
    expect(chip().textContent).toContain("Question inv-child");
    await key(dialog()!, { key: "Backspace" });
    expect(dialog()!.getAttribute("data-gear")).toBe("2");
    const back = cursorTab()!;
    expect(back.id).toBe("gear-tab-subproject-inv-root");
    expect(back.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(back);
    expect(tabsIn(dialog()!).filter((t) => t.getAttribute("aria-selected") === "true")).toHaveLength(1);
  });

  it("gear 3 agent: the dialog closes and the opener gets focus BEFORE the companion changes (close → focus → effect)", async () => {
    openCompanionTabs();
    useCompanion.getState().activateAgentTab("agent:dialogue");
    await mountTopbar(<><div data-pane="right" tabIndex={-1} /><GearSwitchHost surface="topbar" /></>);
    const opener = document.createElement("button");
    opener.textContent = "opener";
    document.body.append(opener);
    opener.focus();
    const order: string[] = [];
    const origFocus = HTMLElement.prototype.focus;
    vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(function (this: HTMLElement, ...a) {
      if (this === opener) order.push("focus-opener");
      return origFocus.apply(this, a);
    });
    const unsub = useCompanion.subscribe((s, p) => { if (s.activeTabId !== p.activeTabId) order.push(`companion:${s.activeTabId}`); });
    const unsubSel = useSelection.subscribe((s, p) => { if (s.selection.agentId !== p.selection.agentId) order.push(`agent:${s.selection.agentId}`); });
    const observer = new MutationObserver(() => { if (!dialog() && !order.includes("closed")) order.push("closed"); });
    observer.observe(document.body, { childList: true, subtree: true });
    try {
      await open();
      await key(dialog()!, { key: "Enter" });
      await key(dialog()!, { key: "Enter" });
      await waitFor(() => expect(cursorTab()!.id).toBe("gear-tab-subproject-inv-child-2"));
      await key(dialog()!, { key: "End" });
      expect(cursorTab()!.id).toBe("gear-tab-agent-inv-member");
      await key(dialog()!, { key: "ArrowLeft" });
      await key(dialog()!, { key: "ArrowLeft" });
      await key(dialog()!, { key: "ArrowLeft" });
      expect(cursorTab()!.id).toBe("gear-tab-agent-inv-child");
      await key(dialog()!, { key: "Enter" });
      await waitFor(() => expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child"));
      await waitFor(() => expect(dialog()).toBeNull());
      // The unmount commit removes the dialog and runs the opener-focus
      // cleanup in one flushSync; the MutationObserver reports the removal
      // on its own microtask, so the two are asserted as one "close" step
      // that precedes every store write of the effect.
      expect(new Set(order.slice(0, 2))).toEqual(new Set(["closed", "focus-opener"]));
      expect(order[2]).toBe("agent:inv-child");
      expect(order).toContain("companion:agent:thread:inv-child");
      expect(order.indexOf("focus-opener")).toBeLessThan(order.indexOf("companion:agent:thread:inv-child"));
      expect(useSelection.getState().selection).toEqual({ projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
      expect(useWorkspace.getState().focusedPane).toBe("right");
    } finally {
      observer.disconnect();
      unsub();
      unsubSel();
      vi.restoreAllMocks();
    }
  });
});
