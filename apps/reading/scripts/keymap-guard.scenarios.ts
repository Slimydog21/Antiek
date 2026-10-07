import { createElement, Fragment, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { LemonModal } from "../src/components/lemon/LemonModal";
import { WriteEditor } from "../src/modes/Write/Editor/Editor";
import { KEYMAP, ACTIONS, currentPlatform, isActiveOn, readPrefix, validateKeymap, type ActionId } from "../src/components/hotkeys/keymap";
import { createActionHandlers } from "../src/workspace/shortcuts";
import { readKeyboardOwnership } from "../src/workspace/keyboardOwnership";
import { useWorkspace, disablePersistence } from "../src/workspace/WorkspaceStore";
import { useTabTrees } from "../src/workspace/tabTreeStore";
import { createInMemoryTabTreeAdapter } from "../src/workspace/tabTree";
import { prefixState } from "../src/components/hotkeys/prefixState";

export async function until(predicate: () => boolean, message: string, timeout = 3000): Promise<void> {
  const end = performance.now() + timeout;
  while (!predicate()) {
    if (performance.now() > end) throw new Error(message);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 80));
function check(ok: unknown, message: string): asserts ok { if (!ok) throw new Error(message); }
function visible(selector: string): boolean {
  return [...document.querySelectorAll<HTMLElement>(selector)].some((el) => !!el.getClientRects().length && !el.closest('[hidden]') && getComputedStyle(el).visibility !== "hidden");
}
function see(selector: string) { return until(() => visible(selector), `visible effect missing: ${selector}`); }
function bodyFocus() {
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  document.body.tabIndex = -1;
  document.body.focus();
}
async function route(path: string) {
  history.pushState({ key: crypto.randomUUID() }, "", path);
  window.dispatchEvent(new PopStateEvent("popstate", { state: history.state }));
  await settle();
}
let contextRoot: Root | null = null;
let contextHost: HTMLDivElement | null = null;
function clearContext() {
  contextRoot?.unmount(); contextRoot = null;
  contextHost?.remove(); contextHost = null;
}
function mountContext(element: ReturnType<typeof createElement>) {
  clearContext();
  contextHost = document.createElement("div"); document.body.append(contextHost);
  contextRoot = createRoot(contextHost); contextRoot.render(element);
}
async function reset() {
  clearContext();
  document.querySelectorAll<HTMLElement>("[data-guard-narrow]").forEach((el) => { el.style.removeProperty("max-width"); el.removeAttribute("data-guard-narrow"); });
  document.querySelectorAll("#guard-text").forEach((el) => el.remove());
  prefixState.disarm();
  for (const button of document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button[aria-label="Close"]')) button.click();
  await settle();
  disablePersistence();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  await route("/read/guard-a");
  await see('[data-pane="left"]');
  await until(() => !!document.querySelector('[aria-label="Contents"]'), "reader fixture did not load");
  bodyFocus();
}
async function tabs(active: "a" | "b" | "c" = "b", child = false) {
  const state = useTabTrees.getState();
  state.setTabTreeAdapter(createInMemoryTabTreeAdapter());
  await useTabTrees.getState().ensureMothership("reading");
  for (const id of ["a", "b", "c"]) {
    useTabTrees.getState().spawnTab("reading", child && id === "c" ? "guard-tab-a" : null, {
      tab_id: `guard-tab-${id}`, kind: "reader", ref: `guard-${id}`, mothership: "reading", activate: false,
    }, "route");
  }
  useTabTrees.getState().activateTab("reading", `guard-tab-${active}`, "route");
  await route(`/read/guard-${active}`);
  useWorkspace.getState().setFocusedPane("left");
  await settle(); bodyFocus();
}
function readerAt(id: string) {
  return until(() => location.pathname === `/read/guard-${id}` && document.body.textContent!.includes(`Guard book ${id.toUpperCase()}`), `tab action did not show Guard book ${id.toUpperCase()} at /read/guard-${id}`);
}
function openPanels() {
  const s = useWorkspace.getState(); s.setLayoutPreset("docked");
  s.open("ProjectTree", {}, { id: "guard-panel-a", mode: "docked-left", title: "Guard panel A" });
  s.open("AISidecar", {}, { id: "guard-panel-b", mode: "docked-right", title: "Guard panel B" });
  s.focus("guard-panel-a");
}
function focusedPanelB() {
  return until(() => !!document.querySelector('[role="region"][aria-label="Guard panel B"]:not(.opacity-95)') && !!document.querySelector('[role="region"][aria-label="Guard panel A"].opacity-95'), "panel.focus: visible focus did not move from A to B");
}
interface Scenario { prepare?: () => void | Promise<void>; effect: () => void | Promise<void>; }
function launcherVisible(): boolean {
  return [...document.querySelectorAll('[role="dialog"]')].some((dialog) => dialog.getClientRects().length > 0 && dialog.querySelector("h2")?.textContent === "More");
}
function door(path: string): Scenario {
  return { effect: async () => {
    await until(() => location.pathname === path && !!document.querySelector(`[data-product-id="${path === "/" ? "research" : path === "/library" ? "read" : path.slice(1)}"]`), `door failed to show ${path}`);
    check(!launcherVisible(), `unrelated activation for ${path} opened the More launcher`);
  } };
}
export const SCENARIOS = {
  "palette.toggle": { effect: () => see('[data-keymap-owner="palette.toggle"]') },
  "keysheet.toggle": { effect: () => see('[data-keymap-owner="keysheet.toggle"]') },
  "projecttree.toggle": { effect: () => see('[role="region"][aria-label="Project"]') },
  "aisidecar.toggle": { effect: () => see('[role="region"][aria-label="AI"]') },
  "panel.focusPrev": { prepare: openPanels, effect: focusedPanelB },
  "panel.focusNext": { prepare: openPanels, effect: focusedPanelB },
  "panel.closeFloating": {
    prepare: () => { useWorkspace.getState().open("ProjectTree", {}, { id: "guard-float", mode: "floating", title: "Guard floating panel" }); useWorkspace.getState().focus("guard-float"); },
    effect: () => until(() => !document.querySelector('[role="region"][aria-label="Guard floating panel"]'), "panel.closeFloating: floating panel stayed visible"),
  },
  "pane.focusLeft": { prepare: () => useWorkspace.getState().setFocusedPane("right"), effect: () => check(document.activeElement?.getAttribute("data-pane") === "left", "pane.focusLeft: left pane did not receive DOM focus") },
  "pane.focusRight": { prepare: () => useWorkspace.getState().setFocusedPane("left"), effect: () => check(document.activeElement?.getAttribute("data-pane") === "right", "pane.focusRight: right pane did not receive DOM focus") },
  "pane.fullscreen": { prepare: () => useWorkspace.getState().setFocusedPane("left"), effect: () => see('[data-fullscreen-chip]') },
  "layout.togglePreset": { effect: () => until(() => !document.querySelector('[data-layout-preset="omarchy-inset"]') && !!document.querySelector('[data-orientation="bottom"]'), "layout.togglePreset: docked layout did not replace cockpit") },
  "tab.next": { prepare: () => tabs(), effect: () => readerAt("c") },
  "tab.prev": { prepare: () => tabs(), effect: () => readerAt("a") },
  "tab.new": { effect: () => see('[data-keymap-owner="tab.new"]') },
  "tab.parent": { prepare: () => tabs("c", true), effect: () => readerAt("a") },
  "tab.visitChild": { prepare: () => tabs("a", true), effect: () => readerAt("c") },
  "tab.close": { prepare: () => tabs(), effect: () => until(() => location.pathname !== "/read/guard-b" && !document.querySelector('[data-document-strip] [role="tab"][aria-selected="true"]')?.textContent?.includes("Guard book B"), "tab.close: closed tab B still on screen") },
  "tab.reopen": { prepare: async () => { await tabs(); useTabTrees.getState().closeActiveTab("reading", "prune"); await settle(); }, effect: () => readerAt("b") },
  "tab.treeToggle": { prepare: () => tabs(), effect: () => see('[data-tab-tree-panel]') },
  "project.select": { effect: () => see('[data-keymap-owner="project.select"]') },
  // SPR-02 M5: opens the same Switcher (narrowed to Open only when the
  // places flag is on; the guard runs with default flags, so the plain
  // Switcher is the visible effect either way).
  "switcher.open": { effect: () => see('[data-keymap-owner="palette.toggle"]') },
  "reader.tocToggle": {
    prepare: async () => {
      const reader = document.querySelector<HTMLElement>('[data-testid="book-reader-root"]');
      check(reader, "reader.tocToggle: real reader missing");
      reader.setAttribute("data-guard-narrow", ""); reader.style.maxWidth = "600px";
      await until(() => !visible("[data-reader-toc]"), "reader.tocToggle: fixture must start with folded contents");
    },
    effect: () => see('[aria-label="Contents"][data-open="true"]'),
  },
  "inbox.toggle": { effect: () => see('[data-keymap-owner="inbox.toggle"]') },
  "door.research": door("/"),
  "door.read": door("/library"),
  "door.write": door("/write"),
  "door.speak": door("/speak"),
  "door.home": door("/home"),
  "door.more": { effect: () => until(launcherVisible, "visible effect missing: More launcher") },
  "door.researchHome": door("/"),
  "door.readLibrary": door("/library"),
} satisfies Record<ActionId, Scenario>;

function viewState() {
  const ws = useWorkspace.getState();
  return JSON.stringify({ path: location.pathname, panels: Object.keys(ws.panels), preset: ws.layoutPreset,
    fullscreen: ws.fullscreenPane, pane: ws.focusedPane, focusedPanel: ws.focusedPanelId,
    treePanel: useTabTrees.getState().treePanelOpen,
    active: useTabTrees.getState().trees.reading?.active_tab_id,
    dialogs: [...document.querySelectorAll('[aria-modal="true"]')].map((el) => el.getAttribute("aria-labelledby")),
    inbox: visible('[data-keymap-owner="inbox.toggle"]'),
  });
}
let beforeView = "";
let afterSequence = 0;
export async function prepare(id: string, context = "default") {
  const row = KEYMAP.find((r) => r.id === id); check(row, `unknown row ${id}`);
  await reset();
  const scenario: Scenario | undefined = SCENARIOS[row.action];
  check(scenario, `POPULATION/COVERAGE ${row.id}/${row.action}: no executable scenario`);
  await scenario.prepare?.(); await settle(); bodyFocus();
  if (context === "text") {
    const input = document.createElement("input"); input.id = "guard-text"; input.value = "fixture text";
    document.body.append(input); input.focus();
  }
  if (context === "modal") {
    mountContext(createElement(LemonModal, { open: true, title: "Guard modal", onClose: clearContext, children: "Unrelated dialog owns its keys" }));
    await see('[aria-modal="true"]');
  }
  if (context === "editor") {
    mountContext(createElement(WriteEditor, { deliverableId: "guard-piece", sectionId: "guard-section", initialContent: "<p>Guard editor text.</p>" }));
    await see('[contenteditable="true"]');
    document.querySelector<HTMLElement>('[contenteditable="true"]')!.focus();
  }
  beforeView = viewState();
  afterSequence = readKeyboardOwnership().traces.at(-1)?.sequence ?? 0;
  const ownership = readKeyboardOwnership();
  for (const id of ["workspace.prefix", "workspace.direct"]) check(ownership.registrations.filter((r) => r.id === id).length === 1, `EXCLUSIVE OWNER ${id}: expected one installation, got ${ownership.registrations.filter((r) => r.id === id).length}`);
  return { row, prefix: readPrefix(), context };
}
export async function verify(id: string, expectedEffect = true) {
  const row = KEYMAP.find((r) => r.id === id); check(row, `unknown row ${id}`);
  const traces = readKeyboardOwnership().traces.filter((t) => t.sequence > afterSequence);
  check(traces.length && traces.every((t) => t.trusted), `BEHAVIOUR ${id}/${row.action}: trusted keys required`);
  for (const trace of traces) check(trace.eligible.length <= 1, `EXCLUSIVE OWNER ${trace.eligible.join(" vs ")} key=${trace.key} context=${trace.context} row=${id}/${row.action}`);
  if (row.status === "unimplemented") {
    check(!Object.hasOwn(createActionHandlers(() => {}), row.action), `POPULATION/COVERAGE ${id}/${row.action}: unimplemented action has a handler`);
    check(!traces.some((t) => t.actions.length) && beforeView === viewState(), `BEHAVIOUR ${id}/${row.action}: pressed and produced an effect despite declaring itself unimplemented`);
    document.getElementById("guard-text")?.remove();
    return { id, action: row.action, outcome: "pressed and correctly did nothing (declared unimplemented)", traces };
  }
  if (expectedEffect) {
    check(traces.some((t) => t.actions.some((a) => a.row === id && a.action === row.action && a.handled)), `BEHAVIOUR ${id}/${row.action}: no handled action from installed owner`);
    const scenario: Scenario = SCENARIOS[row.action];
    try { await scenario.effect(); } catch (error) { throw new Error(`BEHAVIOUR ${id}/${row.action}: ${String(error)}`); }
  } else {
    check(!traces.some((t) => t.actions.length), `BEHAVIOUR ${id}/${row.action}: action escaped excluded context`);
    check(beforeView === viewState(), `BEHAVIOUR ${id}/${row.action}: visible app state changed in excluded context`);
  }
  document.getElementById("guard-text")?.remove();
  return { id, action: row.action, traces };
}
export function population(exercisedRows: string[], sheetRows: string[]) {
  const rows = KEYMAP.filter((r) => isActiveOn(r, currentPlatform()));
  const problems = validateKeymap(rows, Object.keys(createActionHandlers(() => { throw new Error("coverage must not execute a handler"); })), {
    platforms: [currentPlatform()], coverage: { scenarios: Object.keys(SCENARIOS), exercisedRows, sheetRows },
  });
  for (const action of Object.keys(SCENARIOS)) if (!KEYMAP.some((r) => r.action === action)) problems.push({ kind: "missing-scenario", row: action, detail: `scenario action ${action} lost every KEYMAP row` });
  check(!problems.length, `POPULATION/COVERAGE ${JSON.stringify(problems)}`);
  return { rows: rows.length, actions: Object.keys(ACTIONS).length };
}
export function manifest() { return KEYMAP.filter((r) => isActiveOn(r, currentPlatform())); }
export { readKeyboardOwnership };

function DialogStack() {
  const [upper, setUpper] = useState(true);
  const [lower, setLower] = useState(true);
  return createElement(Fragment, {},
    lower ? createElement(LemonModal, { open: true, title: "Guard lower", onClose: () => setLower(false), children: "Lower dialog" }) : null,
    upper ? createElement(LemonModal, { open: true, title: "Guard upper", onClose: () => setUpper(false), children: "Upper dialog" }) : null,
  );
}
export async function setupDialogs() {
  await reset(); mountContext(createElement(DialogStack));
  await until(() => document.querySelectorAll('[aria-modal="true"]').length === 2, "two real dialogs did not mount");
  afterSequence = readKeyboardOwnership().traces.at(-1)?.sequence ?? 0;
}
export async function verifyDialogs(remaining: number) {
  await until(() => document.querySelectorAll('[aria-modal="true"]').length === remaining, `modal.escape: expected ${remaining} visible dialogs after Escape`);
  const traces = readKeyboardOwnership().traces.filter((t) => t.sequence > afterSequence);
  for (const trace of traces) check(trace.trusted && trace.eligible.length === 1 && trace.eligible[0].startsWith("modal.escape#"), `EXCLUSIVE OWNER ${trace.eligible.join(" vs ")} key=${trace.key} context=${trace.context}`);
  check(traces.length > 0, "modal.escape: no trusted Escape trace");
  afterSequence = traces.at(-1)!.sequence;
  return traces;
}
export async function setupFrame() {
  await reset();
  contextHost = document.createElement("div"); document.body.append(contextHost);
  const frame = document.createElement("iframe");
  frame.sandbox.add("allow-scripts"); frame.srcdoc = '<p>Opaque-origin keyboard fixture</p><input autofocus aria-label="Frame text">';
  const loaded = new Promise<void>((resolve) => { frame.onload = () => resolve(); });
  contextHost.append(frame); await loaded; frame.focus();
  beforeView = viewState(); afterSequence = readKeyboardOwnership().traces.at(-1)?.sequence ?? 0;
}
export function verifyFrame() {
  check(!readKeyboardOwnership().traces.some((t) => t.sequence > afterSequence), "EXCLUSIVE OWNER workspace: key escaped cross-origin iframe into parent");
  check(beforeView === viewState(), "BEHAVIOUR iframe: parent app changed");
  return "iframe key stayed outside parent dispatcher";
}
export function verifyObserver() {
  const traces = readKeyboardOwnership().traces.filter((t) => t.sequence > afterSequence);
  check(traces.some((t) => t.trusted && t.observers.includes("write.undo-observer")), "write.undo-observer: trusted undo was not observed");
  check(traces.every((t) => t.eligible.length === 0 && t.actions.length === 0), "write.undo-observer was counted as an action owner");
  return traces;
}
export async function customStart() {
  await reset(); beforeView = viewState(); afterSequence = readKeyboardOwnership().traces.at(-1)?.sequence ?? 0;
}
export async function customEffect() {
  await until(() => location.pathname === "/library", "custom.guard: saved binding did not navigate after reload");
  const traces = readKeyboardOwnership().traces.filter((t) => t.sequence > afterSequence);
  check(traces.some((t) => t.trusted && t.actions.some((a) => a.action === "custom:guard.custom")), "custom.guard: no trusted dispatcher action");
  return traces;
}
export { setPrefix } from "../src/components/hotkeys/keymap";

export function verifyMoreClick() { return until(launcherVisible, "More click did not open the visible launcher"); }
