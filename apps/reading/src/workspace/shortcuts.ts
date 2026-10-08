import { registerKeyboardOwner, traceKeyboardAction } from "./keyboardOwnership";
/**
 * The keymap dispatcher: the ONE window-level owner of every global key.
 *
 * Mounted once, in AppShell, via `useWorkspaceShortcuts()`. It reads the one
 * table, `components/hotkeys/keymap.ts` (rows, origins, scopes, the prefix),
 * and runs each row's action from {@link createActionHandlers}. No other
 * keydown listener in the app may claim a global combo; the ones that remain
 * are scoped to an element or to an open overlay (Esc, arrows, Tab).
 *
 * Two listeners, one dispatcher:
 *
 *   capture phase  the PREFIX ENGINE. The prefix (ctrl+b by default) arms
 *                  only from a non-text, non-modal focus. While armed, the
 *                  next key belongs to the keymap and to nothing else: it is
 *                  consumed (preventDefault + stopPropagation), runs its
 *                  prefix row if one exists, and disarms. Esc disarms. There
 *                  is no timeout (herdr/tmux semantics). The prefix lapses
 *                  without taking the key if focus has meanwhile moved into
 *                  a field or a dialog, and when the window loses focus,
 *                  because then the next key is not the keymap's to take.
 *
 *   bubble phase   DIRECT KEYS: the ctrl+alt chords, the legacy ⌘ combos and
 *                  "?". Bubble phase, so an element that owns a key first
 *                  (the Write editor's own shortcuts, a WorkspaceWindow's
 *                  arrows, the hotkey capture box) handles it and marks it
 *                  defaultPrevented, and the dispatcher then leaves it alone.
 *
 * Focus decides what may fire (see keymap.ts "scope"):
 *   default  every row.
 *   text     an input, textarea, select, contenteditable or the capture box:
 *            only "anywhere" rows (⌘K, ⌘⇧P, the ctrl+alt chords). The prefix
 *            does not arm, "?" types a "?", ⌘B stays bold.
 *   modal    focus inside an aria-modal dialog: only the dialog's own toggle
 *            (its data-keymap-owner), so ⌘K closes the palette and "?" closes
 *            the key sheet. Everything else belongs to the dialog.
 * A cross-origin iframe (the arXiv embed) never delivers its keys to this
 * window, so nothing fires while focus is inside one.
 */

import { useEffect, useRef } from "react";
import type { NavigateFunction } from "react-router-dom";

import { useWorkspace } from "./WorkspaceStore";
import { companionVisible } from "./companionVisibility";
import { companionHandle } from "./companionHandle";
import { isWorkspaceOwnerSession, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { WRITE_OUTLINE_PANEL_ID, useWriteOutline, writeOutlineVisible } from "./writeOutlineStore";
import { mothershipForPath } from "./mothershipForPath";
import type { Mothership } from "./tabTree";
import { tabTreeHandle } from "./tabTreeHandle";
import { readCustomHotkeys } from "./persistence";
import { READER_TOC_TOGGLE_EVENT } from "./readerEvents";
import { emitProductActivate, normalizeBinding } from "../components/hotkeys/bindings";
import {
  ACTIONS,
  KEYMAP,
  chordTypesText,
  currentPlatform,
  eventMatchesCombo,
  isActiveOn,
  isLoneModifier,
  parseCombo,
  readPrefix,
  type ActionId,
  type ActionMeta,
  type KeymapRow,
} from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";

/** Event names emitted/consumed via window.dispatchEvent. Components
 *  that own their own toggle state listen for these instead of being
 *  driven directly by the workspace store. */
export const SHORTCUT_EVENTS = {
  PALETTE_TOGGLE: "antiek:palette:toggle",
  AISIDECAR_TOGGLE: "antiek:aisidecar:toggle",
  /** SPR-08: toggle the hotkey HUD/cheat-sheet (the "?" overlay). */
  HELP_TOGGLE: "antiek:help:toggle",
  /** Toggle the new-tab picker (prefix+c / ctrl+alt+c; NewTabPicker). */
  NEWTAB_TOGGLE: "antiek:newtab:toggle",
  /** Toggle the account-project picker (prefix+shift+p / ctrl+alt+p;
   *  ProjectPicker). */
  PROJECT_SELECT_TOGGLE: "antiek:project-select:toggle",
} as const;

// ─────────────────────────────────────────────────────────────────────
// SPR-08 EXTENSION SEAM — custom per-entity bindings
// ─────────────────────────────────────────────────────────────────────
//
// Custom per-entity bindings are user DATA, not keymap rows: a runtime map
// the dispatcher consults only after no keymap row matched, only from a
// non-text, non-modal focus. The custom-hotkeys hook (`useCustomHotkeys`) pushes the
// current map here via `setCustomHotkeys`; the handler reads it. Precedence
// (documented in bindings.ts `detectConflict`): a custom binding can NEVER
// shadow a built-in/product/sub-action — the assign affordance refuses such
// an assignment — and `resolveExtended` checks product/sub-action FIRST, so
// even a stale custom binding can never win over a built-in/product combo.

/** One resolved custom binding the handler can fire. */
export interface CustomHotkeyBinding {
  /** Stable id (the binding's own id). */
  id: string;
  /** Canonical ⌘+key combo spec, e.g. "mod+j". */
  spec: string;
  /** Route to navigate to when fired. */
  route: string;
  /** The bound entity id (investigation/document/deliverable/project). */
  entityId: string;
}

let customBindings: CustomHotkeyBinding[] = [];

/** Runtime updater — the custom-hotkeys hook calls this whenever the
 *  persisted map changes so the live handler sees new/removed bindings
 *  without a remount. */
export function setCustomHotkeys(bindings: CustomHotkeyBinding[]): void {
  customBindings = bindings.map((b) => ({
    ...b,
    spec: normalizeBinding(b.spec),
  }));
}

/** Read the current custom bindings (test/inspection helper). */
export function getCustomHotkeys(): CustomHotkeyBinding[] {
  return customBindings;
}

/**
 * Hydrate the live custom-binding map from the persisted blob.
 *
 * WHY THIS LIVES IN `installShortcuts` (the reload-persistence proof):
 * `useCustomHotkeys` pushes the map via `setCustomHotkeys` while a consumer
 * (an <AssignHotkey> surface) is mounted — but on a FRESH page load no such
 * consumer is mounted yet, so `customBindings` would start empty and a
 * persisted custom press would silently do nothing until the operator
 * happened to open an assign surface. That breaks M2's "press it after a
 * reload → still navigates". So the always-mounted shortcut handler reads
 * the persisted blob on install and seeds the live map. Once a consumer
 * mounts it takes over (idempotent — same data). Reading bindings the user
 * personally set is data, not instruction, so this respects the
 * data/instruction boundary the daemon work flagged.
 */
function hydrateCustomFromStorage(): void {
  setCustomHotkeys(readCustomHotkeys().bindings);
}

/** Exported for element-scoped key guards (PanelLayout's fullscreen-pane Esc
 *  restore ignores Esc pressed while typing, mirroring the dispatcher's
 *  outside-text rule without adding a global key). */
export function isTextEditing(t: Element | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  // isContentEditable, plus the attribute for environments that do not
  // compute it (jsdom); the attribute check also covers descendants.
  if (t.isContentEditable || t.closest('[contenteditable]:not([contenteditable="false"])')) {
    return true;
  }
  // (The SPR-08 hotkey-capture box needs no case here: it sits in a modal,
  // which owns every key, and it stops its keys at the element.)
  return false;
}

export type FocusContext =
  | { kind: "default" }
  | { kind: "text" }
  | { kind: "modal"; owner: string | null; text: boolean };

/** Where a key event lands, for the scope rules above. */
export function focusContext(target: EventTarget | null): FocusContext {
  let el: Element | null = target instanceof Element ? target : null;
  if (!el || el === document.body || el === document.documentElement) {
    el = document.activeElement;
  }
  const bodyish = !el || el === document.body || el === document.documentElement;
  const modal =
    (el && el.closest('[aria-modal="true"]')) ||
    (bodyish ? document.querySelector('[aria-modal="true"]') : null);
  if (modal) {
    const owner =
      modal.getAttribute("data-keymap-owner") ??
      modal.querySelector("[data-keymap-owner]")?.getAttribute("data-keymap-owner") ??
      null;
    return { kind: "modal", owner, text: isTextEditing(el) };
  }
  return isTextEditing(el) ? { kind: "text" } : { kind: "default" };
}

function scopeAllows(row: KeymapRow, ctx: FocusContext): boolean {
  if (ctx.kind === "default") return true;
  if (ctx.kind === "text") return row.scope === "anywhere";
  return row.action === ctx.owner && (row.scope === "anywhere" || !ctx.text);
}

function hasAnyModifier(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey || e.altKey || e.shiftKey;
}

/** The canonical combo for a keydown, for the custom-binding lookup:
 *  ⌘E → "mod+e", ⌥J → "alt+j". Null for a lone modifier or a bare key. */
function comboSpecFor(e: KeyboardEvent): string | null {
  const key = e.key.toLowerCase();
  if (["meta", "control", "shift", "alt"].includes(key)) return null;
  const parts: string[] = [];
  if (e.metaKey || e.ctrlKey) parts.push("mod");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  if (parts.length === 0) return null;
  parts.push(key);
  return normalizeBinding(parts.join("+"));
}

/** Toggle the ProjectTree panel docked-left. */
function toggleProjectTree() {
  const ws = useWorkspace.getState();
  const id = "shortcuts:projecttree";
  if (ws.panels[id]) {
    ws.close(id);
  } else {
    ws.open("ProjectTree", {}, { mode: "docked-left", title: "Project", id });
  }
}

/** Toggle the AISidecar panel via the workspace store. Exported so every
 *  "Ask"/"Toggle AI sidecar" affordance (SceneChrome action bar,
 *  CommandPalette) goes through the SAME toggle as the ⌘/ key. (It no longer
 *  also fires AISIDECAR_TOGGLE: nothing, not even a story, listens for it.) */
export const AISIDECAR_PANEL_ID = "shortcuts:aisidecar";
export function toggleAISidecar() {
  const ws = useWorkspace.getState();
  if (ws.panels[AISIDECAR_PANEL_ID]) {
    ws.close(AISIDECAR_PANEL_ID);
  } else {
    ws.open(
      "AISidecar",
      {},
      { mode: "docked-right", title: "AI", id: AISIDECAR_PANEL_ID },
    );
  }
}

/** Close the focused floating panel. False (the key is not ours) otherwise,
 *  so ⌘W falls through to the browser's close-tab. */
function closeFocusedFloat(): boolean {
  const ws = useWorkspace.getState();
  const fid = ws.focusedPanelId;
  if (!fid) return false;
  const p = ws.panels[fid];
  if (!p || p.mode !== "floating") return false;
  ws.close(fid);
  return true;
}

/** Cycle focus across visible panels (docked + floating, ignoring popout). */
function cycleFocus(direction: 1 | -1) {
  const ws = useWorkspace.getState();
  const visible = [
    ...ws.dockLeftIds,
    ...ws.floatingIds,
    ...ws.dockBottomIds,
    ...ws.dockRightIds,
  ];
  if (visible.length === 0) return;
  const cur = ws.focusedPanelId
    ? visible.indexOf(ws.focusedPanelId)
    : -1;
  const next = (cur + direction + visible.length) % visible.length;
  ws.focus(visible[next]);
}

/**
 * Cockpit pane focus (C3). In the omarchy-inset preset: move DOM focus to
 * the named inset pane and set its focus ring. Honest no-op when that pane
 * is not on screen (hidden by the other pane's fullscreen, or no cockpit
 * mounted): there is nowhere for focus to go,
 * and pretending otherwise would focus an invisible element. In the docked
 * preset the keys are never dead: they cycle the dock areas through the
 * existing cycleFocus mechanics (left = previous, right = next).
 */
function focusPane(side: "left" | "right") {
  const ws = useWorkspace.getState();
  if (ws.layoutPreset !== "omarchy-inset") {
    cycleFocus(side === "left" ? -1 : 1);
    return;
  }
  if (ws.fullscreenPane && ws.fullscreenPane !== side) return;
  const el = document.querySelector<HTMLElement>(`[data-pane="${side}"]`);
  if (!el) return;
  // A pane fullscreen hides stays mounted (PanelLayout), so "present" is
  // not "on screen": never focus a hidden pane.
  if (el.closest("[hidden]")) return;
  ws.setFocusedPane(side);
  el.focus();
}

/**
 * Which pane the tab keys act on (the lane-A cockpit decision): the FOCUSED
 * pane, as herdr's tabs belong to their pane; the left when neither is.
 *   inset   the pane shown alone by fullscreen, else the pane with the focus
 *           ring (PanelLayout sets it as focus enters a pane).
 *   docked  "right" while a right-dock panel has focus (the companion, the
 *           outline), otherwise "left".
 */
function tabKeySide(): "left" | "right" {
  const ws = useWorkspace.getState();
  if (ws.layoutPreset === "omarchy-inset") return ws.fullscreenPane ?? ws.focusedPane ?? "left";
  return ws.focusedPanelId !== null && ws.dockRightIds.includes(ws.focusedPanelId) ? "right" : "left";
}

/** Writing with the outline visible: the right pane holds block tabs (C5),
 *  the piece's own blocks, which cycle but never close. */
function rightPaneHoldsBlocks(): boolean {
  if (mothershipForPath(window.location.pathname, window.location.search) !== "writing") return false;
  const ws = useWorkspace.getState();
  return writeOutlineVisible(ws.layoutPreset, Boolean(ws.panels[WRITE_OUTLINE_PANEL_ID]));
}

/** Act on the companion present at the keystroke, before another account,
 *  project, or pane can replace it. A lazy/unconfirmed pane admits no key;
 *  suspension keeps its state, but does not queue a key for later delivery. */
function onAgentTabs(run: (store: NonNullable<(typeof companionHandle)["store"]>) => void): void {
  if (rightPaneHoldsBlocks() || !companionVisible()) return;
  const store = companionHandle.store;
  const owner = workspaceOwnerSession();
  if (!store || owner.subject === null || !isWorkspaceOwnerSession(owner)) return;
  run(store);
}

/**
 * Right-pane tab cycling. In writing mode with the outline pane visible it
 * cycles the outline's block tabs (C5); everywhere else the companion's
 * agent tabs (C4), only while the companion is visible: an honest no-op
 * otherwise. The stores' cycles wrap across ALL tabs, so visual overflow is
 * never a boundary.
 */
function cycleRightPaneTab(direction: 1 | -1) {
  if (rightPaneHoldsBlocks()) {
    useWriteOutline.getState().cycle(direction);
    return;
  }
  onAgentTabs((c) => c.getState().cycleAgentTab(direction));
}

/**
 * Document tab-tree keys (D6). They act on the CURRENT route's mothership
 * tree, and only once that tree has loaded — an honest no-op before then
 * (never a dead key in a surface whose tree is not up). The store's own
 * no-op cases (a root has no parent, a leaf has no children, no siblings)
 * stay silent by the model's semantics.
 */
type TabTreeStore = NonNullable<(typeof tabTreeHandle)["store"]>;

function tabTreeKey(run: (store: TabTreeStore, mothership: Mothership) => void) {
  const mothership = mothershipForPath(window.location.pathname, window.location.search);
  const store = tabTreeHandle.store;
  if (!store) return;
  const s = store.getState();
  if (!s.loaded[mothership] || !s.trees[mothership]) return;
  run(store, mothership);
}

/** Runs an action. Returning false means "not mine after all": the key is
 *  left to the browser and nothing is prevented. */
export type KeyHandler = (e: KeyboardEvent) => boolean | void;

/** n/p and ctrl+alt+]/[: the focused pane's next or previous tab. */
function cycleTab(direction: 1 | -1) {
  if (tabKeySide() === "right") cycleRightPaneTab(direction);
  else tabTreeKey((t, m) => t.getState().cycleSibling(m, direction));
}

/**
 * prefix+shift+x: close the focused pane's active tab, behind the 10 s
 * Undo. Left: the document tab and its branches (§2a's default, prune).
 * Right: the active agent tab (a view act; the agent is untouched). Block
 * tabs in writing are the piece's blocks and never close: a no-op there,
 * and never a close of the left tab instead.
 */
function closeTab() {
  if (tabKeySide() === "right") onAgentTabs((c) => c.getState().closeActiveAgentTab());
  else tabTreeKey((t, m) => t.getState().closeActiveTab(m, "prune"));
}

/** prefix+shift+t: reopen the focused pane's last closed tab (the undo
 *  inside the hold, the most recent retired tab after it). */
function reopenTab() {
  if (tabKeySide() === "right") onAgentTabs((c) => c.getState().reopenLastClosedAgentTab());
  else tabTreeKey((t, m) => t.getState().undoLastClose(m));
}

/** The reader's contents: the mounted reader answers the event by
 *  cancelling it, so a key with no reader on screen stays the page's. */
function toggleReaderToc(): boolean {
  const e = new CustomEvent(READER_TOC_TOGGLE_EVENT, { cancelable: true });
  return !window.dispatchEvent(e);
}

/** Toggle the new-tab picker. Exported so every "new tab" affordance (the
 *  document strip's + button, the prefix+c key) goes through the SAME
 *  toggle. NewTabPicker (mounted once in AppShell) listens and opens. */
export function toggleNewTabPicker(): void {
  window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.NEWTAB_TOGGLE));
}

/** Toggle the account-project picker. Exported so the sidebar's project row
 *  and the prefix+shift+p key share one path. */
export function toggleProjectPicker(): void {
  window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE));
}

/**
 * prefix+a / ctrl+alt+a (SPR-07): open the selected project's agent pane,
 * or focus its composer when it is already open. The pane ships with the
 * lazy companion chunk, so the opener is import()ed (entryChunk.test.ts
 * forbids a static ./agent/ import here). In writing the right pane holds
 * the outline's block tabs (F7): the key is not ours, an honest no-op.
 */
function openAgentPaneKey(): boolean {
  if (rightPaneHoldsBlocks()) return false;
  void import("./agent/openAgentPane").then(({ openAgentPaneFromKey }) => openAgentPaneFromKey());
  return true;
}

/**
 * One handler per keymap action. keymap.test.ts fails if a table row names
 * an action missing here; the Record type makes tsc fail first.
 */
export function createActionHandlers(navigate: NavigateFunction) {
  // A product door: navigate (when it has a route) AND emit the activation a
  // click emits, so the mascot cannot tell a key from a click. Every action
  // whose metadata names a product is a door.
  const doors: Partial<Record<ActionId, KeyHandler>> = {};
  for (const id of Object.keys(ACTIONS) as ActionId[]) {
    const meta: ActionMeta = ACTIONS[id];
    if (!meta.productId) continue;
    doors[id] = () => {
      if (meta.route) navigate(meta.route);
      emitProductActivate({
        productId: meta.productId!,
        ...(meta.actionId ? { actionId: meta.actionId } : {}),
        route: meta.route,
        source: "hotkey",
      });
    };
  }
  return {
    ...doors,
    "palette.toggle": () => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE));
    },
    // SPR-02 M5 — the same Switcher, opened (not toggled) with the Open
    // section's query preset. The palette ignores the detail when the
    // places flag is off, so the key degrades to the plain Switcher.
    "switcher.open": () => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE, { detail: { query: "in:open" } }));
    },
    "keysheet.toggle": () => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    },
    "projecttree.toggle": () => toggleProjectTree(),
    "aisidecar.toggle": () => toggleAISidecar(),
    "panel.focusPrev": () => cycleFocus(-1),
    "panel.focusNext": () => cycleFocus(1),
    "panel.closeFloating": () => closeFocusedFloat(),
    "pane.focusLeft": () => focusPane("left"),
    "pane.focusRight": () => focusPane("right"),
    "pane.fullscreen": () => useWorkspace.getState().toggleFullscreenPane(),
    "layout.togglePreset": () => useWorkspace.getState().toggleLayoutPreset(),
    "tab.next": () => cycleTab(1),
    "tab.prev": () => cycleTab(-1),
    "tab.new": () => toggleNewTabPicker(),
    "tab.parent": () => tabTreeKey((t, m) => t.getState().goToParent(m)),
    "tab.visitChild": () => tabTreeKey((t, m) => t.getState().visitChildOfActive(m)),
    // Close follows pane focus like n/p. On the left it is §2a's default
    // outcome, the tab and its branches (prune), held 10 s behind the
    // toast's Undo; "Close only this" (lift_children) is the tree panel's
    // Shift+Delete and has no key.
    "tab.close": () => closeTab(),
    "tab.reopen": () => reopenTab(),
    "reader.tocToggle": () => toggleReaderToc(),
    "tab.treeToggle": () => tabTreeHandle.store?.getState().toggleTreePanel(),
    "project.select": () => toggleProjectPicker(),
    "agent.openPane": () => openAgentPaneKey(),
  } satisfies Partial<Record<ActionId, KeyHandler>>;
}

function consume(e: KeyboardEvent): void {
  e.preventDefault();
  e.stopPropagation();
}

export interface InstallOptions {
  /** Test seam: replace some action handlers (e.g. with counters). */
  handlers?: Partial<Record<ActionId, KeyHandler>>;
}

/**
 * Install the dispatcher. Returns the uninstall fn.
 *
 * `navigate` is required for the product doors and custom bindings; pass
 * `useNavigate()`'s return value from inside AppShell.
 */
export function installShortcuts(
  navigate: NavigateFunction,
  opts: InstallOptions = {},
): () => void {
  // Seed the live custom-binding map from the persisted blob on every mount,
  // so a custom hotkey set in a previous session fires after a reload
  // WITHOUT waiting for an <AssignHotkey> surface to mount (SPR-08 M2).
  hydrateCustomFromStorage();
  // A custom binding assigned in another tab lands in localStorage; re-hydrate
  // on the cross-tab `storage` signal so this tab's handler sees it too.
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key.endsWith("custom-hotkeys")) hydrateCustomFromStorage();
  };

  const handlers: Partial<Record<ActionId, KeyHandler>> = {
    ...createActionHandlers(navigate),
    ...opts.handlers,
  };
  const platform = currentPlatform();
  const rows = KEYMAP.filter((r) => isActiveOn(r, platform));
  const prefixRows = rows.filter((r) => r.prefixKey);
  const directRows = rows.filter((r) => r.chord);

  function run(row: KeymapRow, e: KeyboardEvent): boolean {
    const handler = handlers[row.action];
    if (!handler) throw new Error(`keymap row ${row.id}: missing handler ${row.action}`);
    const handled = handler(e) !== false;
    traceKeyboardAction(e, row.id, row.action, handled);
    return handled;
  }

  function onCapture(e: KeyboardEvent) {
    if (e.isComposing) return;
    const isPrefix = eventMatchesCombo(e, readPrefix());
    if (prefixState.isArmed()) {
      // Shift (for prefix+?) and other lone modifiers are part of the next
      // key, not the next key.
      if (isLoneModifier(e)) return;
      // Focus moved into a field or a dialog since the prefix armed (a
      // click): the key is theirs, and the prefix just lapses.
      if (focusContext(e.target).kind !== "default") return prefixState.disarm();
      consume(e);
      // A held prefix auto-repeats; it stays armed and the repeats go nowhere.
      if (isPrefix && e.repeat) return;
      prefixState.disarm();
      if (e.key === "Escape" || isPrefix) return;
      const row = prefixRows.find((r) => eventMatchesCombo(e, r.prefixKey!));
      if (row && row.status !== "unimplemented") run(row, e);
      return;
    }
    // Never steal the prefix from text (ctrl+b moves the caret on macOS) or
    // from a dialog.
    if (!isPrefix || focusContext(e.target).kind !== "default") return;
    consume(e);
    // A repeat of a prefix that was just cancelled is swallowed, not re-armed
    // and never passed on (on a Mac, ctrl+b would reach the ⌘B row).
    if (!e.repeat) prefixState.arm();
  }

  function directCandidate(e: KeyboardEvent) {
    if (e.defaultPrevented || e.isComposing) return null;
    const ctx = focusContext(e.target);
    const row = directRows.find((r) => eventMatchesCombo(e, r.chord!));
    if (row) {
      if (row.status === "unimplemented") return null;
      if (!scopeAllows(row, ctx)) return null;
      if (ctx.kind !== "default" && parseCombo(row.chord!).alt && chordTypesText(e)) return null;
      if (ctx.kind !== "default" && platform === "mac" && e.ctrlKey && !e.metaKey && !e.altKey) return null;
      return { row };
    }
    if (ctx.kind !== "default" || !hasAnyModifier(e)) return null;
    const spec = comboSpecFor(e);
    const custom = spec ? customBindings.find((b) => b.spec === spec) : undefined;
    return custom ? { custom } : null;
  }

  function onBubble(e: KeyboardEvent) {
    const candidate = directCandidate(e);
    if (!candidate) return;
    if (candidate.row) {
      if (run(candidate.row, e)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
      return;
    }
    const { custom } = candidate;
    e.preventDefault();
    navigate(custom.route);
    traceKeyboardAction(e, custom.id, `custom:${custom.id}`, true);
    emitProductActivate({
      productId: "custom", route: custom.route, entityId: custom.entityId, source: "hotkey",
    });
  }

  const onBlur = () => prefixState.disarm();

  window.addEventListener("storage", onStorage);
  const removePrefix = registerKeyboardOwner(window, {
    id: "workspace.prefix", scope: "global-prefix", capture: true,
    eligible: (e) => !e.isComposing && !isLoneModifier(e) && focusContext(e.target).kind === "default"
      && (prefixState.isArmed() || eventMatchesCombo(e, readPrefix())),
  }, onCapture);
  const removeDirect = registerKeyboardOwner(window, {
    id: "workspace.direct", scope: "global-direct",
    eligible: (e) => directCandidate(e) !== null,
  }, onBubble);
  window.addEventListener("blur", onBlur);
  return () => {
    window.removeEventListener("storage", onStorage);
    removePrefix();
    removeDirect();
    window.removeEventListener("blur", onBlur);
    prefixState.disarm();
  };
}

/**
 * Hook form for mounting inside AppShell. Installs once: the latest
 * `navigate` is read through a ref, because react-router hands out a new
 * function on every location change and reinstalling would drop an armed
 * prefix and reorder the window listeners.
 */
export function useWorkspaceShortcuts(navigate: NavigateFunction) {
  const ref = useRef(navigate);
  useEffect(() => {
    ref.current = navigate;
  }, [navigate]);
  useEffect(() => {
    const stable = ((...args: unknown[]) =>
      (ref.current as (...a: unknown[]) => unknown)(...args)) as NavigateFunction;
    return installShortcuts(stable);
  }, []);
}
