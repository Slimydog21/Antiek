/**
 * cockpitKeysStage3.test.tsx — the lane-A cockpit key decision (forensic
 * defects 10, 12, 13 of FORENSIC-KIMI-DESIGN-2026-09-26), red-first.
 *
 * The decision (docs/decisions/mothership-keys-herdr-prefix.md, "Cockpit
 * keys"): n/p and ctrl+alt+]/[ cycle the tabs of the FOCUSED pane (left =
 * document tabs, right = agent tabs, or block tabs in writing; neither
 * focused = left); i / ctrl+alt+i are the attention inbox, reserved and a
 * no-op until it ships; the layout preset moves to prefix+shift+i with no
 * chord; c / ctrl+alt+c are "new tab", reserved until the picker ships;
 * close is prefix+shift+x alone; the ctrl+alt+c close chord is gone.
 *
 * The dispatcher runs with REAL handlers against the real stores.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";

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
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import KeySheet from "../components/hotkeys/KeySheet";
import {
  ACTIONS,
  KEYMAP,
  KEYMAP_DECISION,
  RESERVED_FOR_LATER,
  codeToKey,
  eventMatchesCombo,
  validateKeymap,
} from "../components/hotkeys/keymap";
import { NOTES } from "../components/hotkeys/keymapView";
import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { COMPANION_PANEL_ID, useCompanion } from "./companionStore";
import { mothershipForPath } from "./documentSpace";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { createActionHandlers, installShortcuts, SHORTCUT_EVENTS } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
const comp = () => useCompanion.getState();
const M = () => mothershipForPath(window.location.pathname, window.location.search);
const activeDoc = () => tabs().trees[M()]?.active_tab_id ?? null;

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

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  comp().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
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

/**
 * The cockpit at /read/doc-9 with two document siblings (c1 active, c2) on
 * the left and two agent tabs (inv-a, inv-b active) on the right.
 */
async function seedCockpit(preset: "omarchy-inset" | "docked" = "omarchy-inset") {
  window.history.replaceState({}, "", "/read/doc-9");
  ws().setLayoutPreset(preset);
  render(
    <BrowserRouter>
      <PanelLayout mainSlot={<p>route content</p>} />
    </BrowserRouter>,
  );
  await waitFor(() => expect(activeDoc()).not.toBeNull());
  const m = M();
  const rootId = activeDoc()!;
  act(() => {
    tabs().spawnTab(m, rootId, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: false });
    tabs().spawnTab(m, rootId, { tab_id: "c2", kind: "reader", ref: "doc-9", mothership: m, activate: false });
    tabs().activateTab(m, "c1");
    comp().openAgentTab({ kind: "research-thread", investigationId: "inv-a", title: "Question A" });
    comp().openAgentTab({ kind: "research-thread", investigationId: "inv-b", title: "Question B" });
  });
  expect(activeDoc()).toBe("c1");
  expect(comp().activeTabId).toBe("agent:thread:inv-b");
  return { m };
}

// ─── n / p: the focused pane's tabs ───────────────────────────────────────

describe("n/p and ctrl+alt+]/[ cycle the tabs of the FOCUSED pane", () => {
  it("with neither pane focused they act on the LEFT (document) tabs", async () => {
    await seedCockpit();
    expect(ws().focusedPane).toBeNull();
    prefixed("n");
    expect(activeDoc()).toBe("c2");
    prefixed("p");
    expect(activeDoc()).toBe("c1");
    // The agent tabs did not move.
    await act(async () => {});
    expect(comp().activeTabId).toBe("agent:thread:inv-b");
  });

  it("left pane focused: prefix n/p and the bracket chords cycle the document tabs", async () => {
    await seedCockpit();
    act(() => ws().setFocusedPane("left"));
    prefixed("n");
    expect(activeDoc()).toBe("c2");
    key(document.body, "ctrl+alt+]"); // wraps
    expect(activeDoc()).toBe("c1");
    key(document.body, "ctrl+alt+[");
    expect(activeDoc()).toBe("c2");
    prefixed("p");
    expect(activeDoc()).toBe("c1");
    await act(async () => {});
    expect(comp().activeTabId).toBe("agent:thread:inv-b");
  });

  it("right pane focused: the same keys cycle the AGENT tabs and never the document tabs", async () => {
    await seedCockpit();
    act(() => ws().setFocusedPane("right"));
    prefixed("n"); // wraps from the last agent tab to the first
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-a"));
    key(document.body, "ctrl+alt+]");
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-b"));
    key(document.body, "ctrl+alt+[");
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-a"));
    prefixed("p");
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-b"));
    expect(activeDoc()).toBe("c1");
  });

  it("focus that MOVES between the panes retargets the keys (the pane's own focus capture)", async () => {
    await seedCockpit();
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    const left = document.querySelector<HTMLElement>('[data-pane="left"]')!;
    act(() => right.focus());
    expect(ws().focusedPane).toBe("right");
    key(document.body, "ctrl+alt+]");
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-a"));
    expect(activeDoc()).toBe("c1");
    act(() => left.focus());
    expect(ws().focusedPane).toBe("left");
    key(document.body, "ctrl+alt+]");
    expect(activeDoc()).toBe("c2");
    expect(comp().activeTabId).toBe("agent:thread:inv-a");
  });

  it("docked preset: a focused companion panel is the right pane; any other focus is the left", async () => {
    await seedCockpit("docked");
    act(() => {
      ws().open("Companion", {}, { mode: "docked-right", title: "Agents", id: COMPANION_PANEL_ID });
      ws().focus(COMPANION_PANEL_ID);
    });
    prefixed("n");
    await waitFor(() => expect(comp().activeTabId).toBe("agent:thread:inv-a"));
    expect(activeDoc()).toBe("c1");
    // Focus moves to a left-dock panel: the keys go back to the left.
    act(() => {
      ws().open("ProjectTree", {}, { mode: "docked-left", title: "Project", id: "probe:left" });
      ws().focus("probe:left");
    });
    prefixed("n");
    expect(activeDoc()).toBe("c2");
  });

  it("none of them fire from a text field (the prefix never arms there)", async () => {
    await seedCockpit();
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    for (const k of ["n", "p"]) {
      key(input, "ctrl+b");
      expect(prefixState.isArmed()).toBe(false);
      expect(key(input, k).defaultPrevented).toBe(false);
    }
    expect(activeDoc()).toBe("c1");
  });
});

// ─── c, i, x: what was taken back ─────────────────────────────────────────

describe("close is prefix+shift+x alone; ctrl+alt+c and prefix c open the new-tab picker and close nothing", () => {
  it("ctrl+alt+c closes nothing: it fires tab.new (the picker), so the key is consumed", async () => {
    const { m } = await seedCockpit();
    const fired = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    const e = key(document.body, "ctrl+alt+c");
    window.removeEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    expect(tabs().trees[m]!.nodes["c1"]).toBeTruthy();
    expect(tabs().heldClose).toBeNull();
    expect(fired).toHaveBeenCalledTimes(1);
    expect(e.defaultPrevented).toBe(true);
  });

  it("prefix c closes nothing either: c is 'new tab' and opens the picker", async () => {
    const { m } = await seedCockpit();
    const fired = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    prefixed("c");
    window.removeEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    expect(tabs().trees[m]!.nodes["c1"]).toBeTruthy();
    expect(tabs().heldClose).toBeNull();
    expect(fired).toHaveBeenCalledTimes(1);
    expect(prefixState.isArmed()).toBe(false);
  });

  it("prefix shift+x closes the active tab (held 10 s behind the toast's Undo)", async () => {
    const { m } = await seedCockpit();
    prefixed("shift+x");
    expect(tabs().trees[m]!.nodes["c1"]).toBeUndefined();
    expect(tabs().heldClose?.token.tab_id).toBe("c1");
  });

  it("the table: tab.close is bound ONLY to prefix+shift+x, and no row binds ctrl+alt+c to a close", () => {
    const closeRows = KEYMAP.filter((r) => r.action === "tab.close");
    expect(closeRows.map((r) => r.prefixKey ?? r.chord)).toEqual(["shift+x"]);
    expect(KEYMAP.some((r) => r.chord === "ctrl+alt+c" && r.action === "tab.close")).toBe(false);
    expect(KEYMAP.find((r) => r.prefixKey === "c")?.action).toBe("tab.new");
    expect(KEYMAP.find((r) => r.chord === "ctrl+alt+c")?.action).toBe("tab.new");
  });
});

describe("the layout preset moves to prefix+shift+i (no chord); i is the attention inbox", () => {
  it("prefix shift+i toggles docked ⇄ inset", () => {
    prefixed("shift+i");
    expect(ws().layoutPreset).toBe("omarchy-inset");
    prefixed("shift+i");
    expect(ws().layoutPreset).toBe("docked");
  });

  it("prefix i and ctrl+alt+i no longer toggle the preset; the chord is left to the page", () => {
    prefixed("i");
    expect(ws().layoutPreset).toBe("docked");
    const e = key(document.body, "ctrl+alt+i");
    expect(ws().layoutPreset).toBe("docked");
    expect(e.defaultPrevented).toBe(false);
  });

  it("the table: the preset has one key and no chord; i and ctrl+alt+i are the inbox's", () => {
    const presetRows = KEYMAP.filter((r) => r.action === "layout.togglePreset");
    expect(presetRows.map((r) => r.prefixKey ?? `chord:${r.chord}`)).toEqual(["shift+i"]);
    expect(KEYMAP.find((r) => r.prefixKey === "i")?.action).toBe("inbox.toggle");
    expect(KEYMAP.find((r) => r.chord === "ctrl+alt+i")?.action).toBe("inbox.toggle");
  });

  it("the declared-unimplemented inbox has no handler", () => {
    const handlers = createActionHandlers(vi.fn() as never);
    expect(Object.hasOwn(handlers, "inbox.toggle")).toBe(false);
    // tab.new is no longer reserved: it fires the picker's toggle.
    const fired = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    expect(handlers["tab.new"]()).not.toBe(false);
    window.removeEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, fired);
    expect(fired).toHaveBeenCalledTimes(1);
  });
});

describe("the key sheet tells the truth about reserved keys", () => {
  function sheetRow(action: string): HTMLElement {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    return document.body.querySelector<HTMLElement>(`[data-keymap-action="${action}"]`)!;
  }

  it("the attention inbox row shows prefix i and ctrl+alt+i and says it is not built yet", () => {
    const row = sheetRow("inbox.toggle");
    expect(row).toBeTruthy();
    expect(row.querySelector('[data-keymap-row="prefix-inbox"]')).toBeTruthy();
    expect(row.querySelector('[data-keymap-row="chord-inbox"]')).toBeTruthy();
    expect(row.getAttribute("data-keymap-pending")).toBe("true");
    expect(row.textContent).toMatch(/not built yet/i);
  });

  it("the new-tab row shows prefix c and ctrl+alt+c and describes the picker (no longer pending)", () => {
    const row = sheetRow("tab.new");
    expect(row.querySelector('[data-keymap-row="prefix-tab-new"]')).toBeTruthy();
    expect(row.querySelector('[data-keymap-row="chord-tab-new"]')).toBeTruthy();
    expect(row.getAttribute("data-keymap-pending")).toBeNull();
    expect(row.textContent).toMatch(/new-tab picker/i);
    expect(row.textContent).not.toMatch(/not built yet/i);
  });

  it("the project row shows prefix shift+p and ctrl+alt+p and describes the registry pick", () => {
    const row = sheetRow("project.select");
    expect(row.querySelector('[data-keymap-row="prefix-project-select"]')).toBeTruthy();
    expect(row.querySelector('[data-keymap-row="chord-project-select"]')).toBeTruthy();
    expect(row.getAttribute("data-keymap-pending")).toBeNull();
    expect(row.textContent).toMatch(/account projects/i);
  });

  it("the n/p row names the focused-pane rule; the close row names the toast's Undo", () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    const next = document.body.querySelector<HTMLElement>('[data-keymap-action="tab.next"]')!;
    expect(next.textContent).toMatch(/focused pane/i);
    const close = document.body.querySelector<HTMLElement>('[data-keymap-action="tab.close"]')!;
    expect(close.textContent).toMatch(/undo/i);
    expect(close.textContent).not.toMatch(/in the strip/i);
  });

  it("built actions carry no pending mark", () => {
    const row = sheetRow("pane.fullscreen");
    expect(row.getAttribute("data-keymap-pending")).toBeNull();
  });
});

describe("the table after the decision", () => {
  const handlerIds = Object.keys(createActionHandlers((() => {}) as never));

  it("passes the guard: no duplicate, no handler-less action, no reserved key taken", () => {
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
    expect([...handlerIds].sort()).toEqual([...new Set(KEYMAP.filter((row) => row.status !== "unimplemented").map((row) => row.action))].sort());
  });

  it("n/p + ctrl+alt+]/[ are one focused-pane action pair; the ,/. companion pair is gone", () => {
    const byKey = (k: string) => KEYMAP.find((r) => r.prefixKey === k || r.chord === k)?.action;
    expect(byKey("n")).toBe("tab.next");
    expect(byKey("ctrl+alt+]")).toBe("tab.next");
    expect(byKey("p")).toBe("tab.prev");
    expect(byKey("ctrl+alt+[")).toBe("tab.prev");
    for (const k of [",", ".", "ctrl+alt+,", "ctrl+alt+."]) expect(byKey(k), k).toBeUndefined();
    expect(Object.keys(ACTIONS)).not.toContain("companion.nextTab");
    expect(Object.keys(ACTIONS)).not.toContain("tab.nextSibling");
  });

  it("f / ctrl+alt+f stay pane fullscreen and h / l stay pane focus", () => {
    const byKey = (k: string) => KEYMAP.find((r) => r.prefixKey === k || r.chord === k)?.action;
    expect(byKey("f")).toBe("pane.fullscreen");
    expect(byKey("ctrl+alt+f")).toBe("pane.fullscreen");
    expect(byKey("h")).toBe("pane.focusLeft");
    expect(byKey("l")).toBe("pane.focusRight");
  });

  it("the reserved list still refuses the later sprints' keys", () => {
    // SPR-01 M6 took the digits (the numbered arrangements own them now);
    // the rest stay reserved.
    for (const k of ["w", "m", "r", "a"]) expect(RESERVED_FOR_LATER.prefixKeys).toContain(k);
    for (const k of ["1", "9"]) expect(RESERVED_FOR_LATER.prefixKeys).not.toContain(k);
    expect(RESERVED_FOR_LATER.chords).not.toContain("ctrl+alt+1");
    expect(RESERVED_FOR_LATER.chords).not.toContain("ctrl+alt+9");
    const probe = validateKeymap(
      [...KEYMAP, { id: "probe", action: "palette.toggle", prefixKey: "w", scope: "outside-text", origin: "D2", decision: KEYMAP_DECISION }],
      handlerIds,
    );
    expect(probe).toContainEqual(expect.objectContaining({ kind: "reserved-key", row: "probe" }));
  });
});

// ─── defect 12: the Konsole note ──────────────────────────────────────────

describe("ctrl+alt+u: no false desktop-collision claim (DESIGN-MODEL §2 settled it)", () => {
  it("the key sheet does not tell the operator ctrl+alt+u is a KDE-global Konsole grab", () => {
    const note = NOTES["tab.parent"] ?? "";
    expect(note).not.toMatch(/Konsole|KDE|global/i);
  });
});

// ─── defect 13: CODE_KEYS ─────────────────────────────────────────────────

describe("the physical-key map knows Minus, Equal and Quote", () => {
  it("codeToKey maps them to - = '", () => {
    expect(codeToKey("Minus")).toBe("-");
    expect(codeToKey("Equal")).toBe("=");
    expect(codeToKey("Quote")).toBe("'");
  });

  it("a ctrl+alt chord on them matches the physical key, whatever the OS composed", () => {
    for (const [code, k] of [["Minus", "-"], ["Equal", "="], ["Quote", "'"]] as const) {
      const e = new KeyboardEvent("keydown", { code, key: "–", ctrlKey: true, altKey: true });
      expect(eventMatchesCombo(e, `ctrl+alt+${k}`), code).toBe(true);
    }
  });
});
