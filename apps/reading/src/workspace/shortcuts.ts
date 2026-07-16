/**
 * Keyboard shortcut module for the workspace shell.
 *
 * Mounted once at the AppShell level via `useWorkspaceShortcuts()`.
 * The handler ignores key events when the active element is an
 * `<input>`, `<textarea>`, or contenteditable so the operator can
 * type without the shortcuts intercepting.
 *
 * Convention: macOS Cmd vs Linux/Windows Ctrl — `mod` matches either.
 *
 * SPR-08 — UNIFORM ⌘+key. The old vim g-chords are GONE: every product,
 * sub-action and built-in destination is a single ⌘+key combo (one modifier,
 * one keypress, no sequence and no timing window). The leader-key sequence
 * machinery (the pending-key state, its clear fn, and its window constant)
 * has been removed entirely — see the no-chord grep guard in the spec.
 *
 *   ⌘K       toggle command palette          → window.dispatchEvent("antiek:palette:toggle")
 *   ⌘B       toggle ProjectTree panel        → workspace open/close
 *   ⌘/       toggle AISidecar panel          → workspace open/close
 *   ⌘⇧P      same as ⌘K (Linear muscle memory)
 *   ⌘W       close focused floating panel    → workspace.close(focusedPanelId)
 *   ⌘[ / ⌘]  cycle focused panel             → workspace.focus(prev/next)
 *   ?        toggle the keyboard HUD
 *   ⌘J       Research (/)         ⌘E Read (/library)   ⌘Y Write (/write)
 *   ⌘U       Speak (/speak)       ⌘O Home (/home)      ⌘I More (launcher)
 *   ⌘G       Research home        ⌘; Read · library
 *
 *   (⌘M would shadow macOS minimize-window and ⌘H macOS hide-app — both are
 *    in RESERVED_COMBOS, so More takes the free safe letter ⌘I instead.)
 *
 * The product/sub-action combos live in the binding tables in
 * `components/hotkeys/bindings.ts`; `resolveExtended` fires them so a click
 * and a hotkey emit the IDENTICAL `antiek:product:activate` event.
 */

import { useEffect } from "react";
import type { NavigateFunction } from "react-router-dom";

import { useWorkspace } from "./WorkspaceStore";
import { readCustomHotkeys } from "./persistence";
import {
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
  emitProductActivate,
  normalizeBinding,
} from "../components/hotkeys/bindings";

/** Event names emitted/consumed via window.dispatchEvent. Components
 *  that own their own toggle state listen for these instead of being
 *  driven directly by the workspace store. */
export const SHORTCUT_EVENTS = {
  PALETTE_TOGGLE: "antiek:palette:toggle",
  AISIDECAR_TOGGLE: "antiek:aisidecar:toggle",
  /** SPR-08: toggle the hotkey HUD/cheat-sheet (the "?" overlay). */
  HELP_TOGGLE: "antiek:help:toggle",
} as const;

// ─────────────────────────────────────────────────────────────────────
// SPR-08 EXTENSION SEAM — custom per-entity bindings
// ─────────────────────────────────────────────────────────────────────
//
// The injection point the sprint asked for: a runtime map of custom
// bindings, checked AFTER the isTextEditing guard and inside the same
// mod-combo branch as the product/sub-action lookup, WITHOUT touching the
// built-in branches. The custom-hotkeys hook (`useCustomHotkeys`) pushes the
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
  const persisted = readCustomHotkeys().bindings;
  setCustomHotkeys(
    persisted.map((b) => ({
      id: b.id,
      spec: b.spec,
      route: b.route,
      entityId: b.entityId,
    })),
  );
}

function isTextEditing(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (t.isContentEditable) return true;
  // SPR-08 — the hotkey-capture box is a role="textbox" <div> that is
  // actively reading raw keypresses (including "?"). Treat it as text editing
  // so the global HUD handler bails while it is open; otherwise "?" pops the
  // HUD over the capture modal and can never be bound.
  if (t.closest("[data-hotkey-capture]")) return true;
  return false;
}

function isMod(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey;
}

/** Does the event carry ANY modifier (mod / alt / shift)? Used to gate the
 *  combo-resolution branch: a custom binding may legitimately be `alt+j`, so
 *  the resolver runs for any modifier, not only Cmd/Ctrl. */
function hasAnyModifier(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey || e.altKey || e.shiftKey;
}

/** Build the canonical combo spec for a keydown event, e.g. ⌘E → "mod+e",
 *  ⌘⇧P → "mod+shift+p", ⌥J → "alt+j". `mod` collapses Cmd/Ctrl. Single-char
 *  keys are lower-cased; named keys (`/`, `[`) pass through. Returns null
 *  when the keydown is a lone modifier (no real key yet) or carries no
 *  modifier at all (a bare key is never a combo we resolve). */
function comboSpecFor(e: KeyboardEvent): string | null {
  const key = e.key.toLowerCase();
  // Ignore a lone modifier keydown (e.g. ⌘ down with no real key yet).
  if (["meta", "control", "shift", "alt"].includes(key)) return null;
  const parts: string[] = [];
  if (isMod(e)) parts.push("mod");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  if (parts.length === 0) return null; // bare key — not a combo
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

/** Toggle the AISidecar panel via the workspace store. S8-full
 *  refactored AISidecar into a real PanelKind; ⌘/ opens it docked-
 *  right or closes it via `workspace.open` / `workspace.close`
 *  exactly like ⌘B does for ProjectTree.
 *
 *  The custom-event dispatch is kept for backward-compat with any
 *  Storybook stories that listen for the event directly. */
export const AISIDECAR_PANEL_ID = "shortcuts:aisidecar";
function toggleAISidecar() {
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
  window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.AISIDECAR_TOGGLE));
}

/** Close the focused floating panel; no-op otherwise. */
function closeFocusedFloat() {
  const ws = useWorkspace.getState();
  const fid = ws.focusedPanelId;
  if (!fid) return;
  const p = ws.panels[fid];
  if (!p || p.mode !== "floating") return;
  ws.close(fid);
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
 * Install the keyboard shortcut handler. Returns the unsubscribe fn.
 *
 * `navigate` is required for the product/sub-action/custom combo nav; pass
 * `useNavigate()`'s return value from inside AppShell.
 */
export function installShortcuts(navigate: NavigateFunction): () => void {
  // Seed the live custom-binding map from the persisted blob on every mount,
  // so a custom hotkey the operator set in a previous session fires after a
  // reload WITHOUT waiting for an <AssignHotkey> surface to mount (M2).
  hydrateCustomFromStorage();
  // A custom binding assigned in another tab lands in localStorage; re-hydrate
  // on the cross-tab `storage` signal so this tab's handler sees it too.
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key.endsWith("custom-hotkeys")) hydrateCustomFromStorage();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }

  /** Resolve a fully-formed ⌘+key combo spec against the product +
   *  sub-action tables + the custom map. Returns true if it fired. The
   *  built-in combos are handled by their own branches in `handler`; this
   *  only fires NEW (product/sub-action/custom) bindings, and it checks
   *  product/sub-action BEFORE custom so a custom binding can never override
   *  one (defence-in-depth on top of detectConflict's assign-time block). */
  function resolveExtended(spec: string): boolean {
    const norm = normalizeBinding(spec);
    // Product activation — navigate AND emit the shared activation event
    // (the click≡hotkey contract: identical to a click).
    const prod = PRODUCT_BINDINGS.find((b) => normalizeBinding(b.spec) === norm);
    if (prod) {
      // A product with a route navigates; a routeless product (More opens the
      // launcher, no nav) only emits. Either way it fires the shared activate
      // event so a click and a hotkey are indistinguishable.
      if (prod.route) navigate(prod.route);
      emitProductActivate({
        productId: prod.productId!,
        route: prod.route,
        source: "hotkey",
      });
      return true;
    }
    const sub = SUBACTION_BINDINGS.find((b) => normalizeBinding(b.spec) === norm);
    if (sub && sub.route) {
      navigate(sub.route);
      emitProductActivate({
        productId: sub.productId!,
        actionId: sub.actionId,
        route: sub.route,
        source: "hotkey",
      });
      return true;
    }
    // Custom per-entity binding.
    const custom = customBindings.find((b) => b.spec === norm);
    if (custom) {
      navigate(custom.route);
      emitProductActivate({
        productId: "custom",
        route: custom.route,
        entityId: custom.entityId,
        source: "hotkey",
      });
      return true;
    }
    return false;
  }

  function handler(e: KeyboardEvent) {
    if (isTextEditing(e.target)) return;

    // ? — toggle the hotkey HUD (Shift+/ on most layouts). Guarded by
    // isTextEditing above so it never fires while the operator is typing.
    if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
      return;
    }

    if (isMod(e)) {
      // ⌘K — command palette toggle (also ⌘⇧P for Linear muscle memory)
      if (e.key === "k" || (e.shiftKey && (e.key === "P" || e.key === "p"))) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE));
        return;
      }
      // ⌘B — toggle ProjectTree
      if (e.key === "b") {
        e.preventDefault();
        toggleProjectTree();
        return;
      }
      // ⌘/ — toggle AI sidecar
      if (e.key === "/") {
        e.preventDefault();
        toggleAISidecar();
        return;
      }
      // ⌘[ / ⌘] — cycle focused panel
      if (e.key === "[") {
        e.preventDefault();
        cycleFocus(-1);
        return;
      }
      if (e.key === "]") {
        e.preventDefault();
        cycleFocus(1);
        return;
      }
      // ⌘W — close focused floating panel (only when one is focused;
      // otherwise the native ⌘W = close tab passes through)
      if (e.key === "w") {
        const ws = useWorkspace.getState();
        const fid = ws.focusedPanelId;
        if (fid && ws.panels[fid]?.mode === "floating") {
          e.preventDefault();
          closeFocusedFloat();
        }
        return;
      }
    }

    // Product / sub-action / custom modifier combos (the uniform ⌘+key
    // scheme; a custom binding may also be ⌥+key, so this runs for ANY
    // modifier). The built-in combos above already returned, so this only
    // ever resolves a product/sub-action/custom binding — never a built-in,
    // and resolveExtended checks product/sub-action BEFORE custom so a custom
    // binding can never shadow one.
    if (hasAnyModifier(e)) {
      const spec = comboSpecFor(e);
      if (spec && resolveExtended(spec)) {
        e.preventDefault();
        return;
      }
    }
  }

  window.addEventListener("keydown", handler);
  return () => {
    window.removeEventListener("keydown", handler);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

/**
 * Hook form for mounting inside AppShell.
 *
 *   import { useWorkspaceShortcuts } from "./workspace/shortcuts";
 *
 *   function AppShell({ children }) {
 *     useWorkspaceShortcuts();
 *     return ...
 *   }
 *
 * The hook depends on the React Router context, so it MUST be called
 * inside a `<Router>` subtree (AppShell qualifies).
 */
export function useWorkspaceShortcuts(navigate: NavigateFunction) {
  useEffect(() => installShortcuts(navigate), [navigate]);
}
