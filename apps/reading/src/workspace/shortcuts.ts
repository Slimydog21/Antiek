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
 *   ⌘K       toggle command palette          → window.dispatchEvent("antiek:palette:toggle")
 *   ⌘B       toggle ProjectTree panel        → workspace open/close
 *   ⌘/       toggle AISidecar panel          → workspace open/close
 *   ⌘⇧P      same as ⌘K (Linear muscle memory)
 *   ⌘W       close focused floating panel    → workspace.close(focusedPanelId)
 *   ⌘[ / ⌘]  cycle focused panel             → workspace.focus(prev/next)
 *   G then I    /my-research                 (chord, 800ms window)
 *   G then W    /wrestle
 *   G then N    /notebooks
 *
 * Chords use a single in-module pending-key state; if the second key
 * doesn't arrive within `CHORD_WINDOW_MS` the pending state resets.
 */

import { useEffect } from "react";
import type { NavigateFunction } from "react-router-dom";

import { useWorkspace } from "./WorkspaceStore";
import {
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
  emitProductActivate,
  normalizeBinding,
} from "../components/hotkeys/bindings";

const CHORD_WINDOW_MS = 800;

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
// bindings, checked AFTER the isTextEditing guard and BEFORE / alongside
// the built-in handling, WITHOUT touching the built-in branches. The
// custom-hotkeys hook (`useCustomHotkeys`) pushes the current map here via
// `setCustomHotkeys`; the handler reads it. Precedence (documented in
// bindings.ts `detectConflict`): custom bindings can NEVER shadow a
// built-in — the assign affordance refuses such an assignment — so even if
// a stale custom binding somehow matched a built-in spec, the built-in
// branch wins because the handler checks built-ins for combos and resolves
// the custom map only for chord follow-ups / single keys that are NOT
// already a built-in. We additionally guard at lookup time (see
// `resolveExtended`).

/** One resolved custom binding the handler can fire. */
export interface CustomHotkeyBinding {
  /** Stable id (the binding's own id). */
  id: string;
  /** Canonical binding spec, e.g. "g 1" or "j". */
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

function isTextEditing(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (t.isContentEditable) return true;
  // SPR-08 sharpen — the hotkey-capture box is a role="textbox" <div> that is
  // actively reading raw keypresses (including "?" and "g"). Treat it as text
  // editing so the global HUD/chord handlers bail while it is open; otherwise
  // "?" pops the HUD over the capture modal and "?"/"g" can never be bound.
  if (t.closest("[data-hotkey-capture]")) return true;
  return false;
}

function isMod(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey;
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
const AISIDECAR_PANEL_ID = "shortcuts:aisidecar";
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
 * `navigate` is required for chord-based route nav (G+I etc.); pass
 * `useNavigate()`'s return value from inside AppShell.
 */
export function installShortcuts(navigate: NavigateFunction): () => void {
  let pendingChord: { key: string; timer: ReturnType<typeof setTimeout> } | null = null;

  function clearChord() {
    if (pendingChord) {
      clearTimeout(pendingChord.timer);
      pendingChord = null;
    }
  }

  /** Resolve a fully-typed chord/combo spec against the product table +
   *  the custom map. Returns true if it fired. Built-ins are handled by
   *  their own branches above/below; this only fires NEW (product/sub-
   *  action/custom) bindings, so it can never override a built-in. */
  function resolveExtended(spec: string): boolean {
    const norm = normalizeBinding(spec);
    // Product activation — navigate AND emit the shared activation event
    // (the SPR-10 contract: identical to a click).
    const prod = PRODUCT_BINDINGS.find((b) => normalizeBinding(b.spec) === norm);
    if (prod) {
      // A product with a route navigates; a routeless product (More opens the
      // launcher, no nav) only emits. Either way it fires the shared activate
      // event so a click and a hotkey are indistinguishable (SPR-10 contract).
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

    // Chord follow-up: if a chord is pending, the second key resolves
    // immediately + we don't check the other handlers.
    if (pendingChord) {
      const k = e.key.toLowerCase();
      const first = pendingChord.key;
      clearChord();
      if (first === "g") {
        if (k === "i") {
          e.preventDefault();
          // SPR-05: the one multi-research monitor (was /investigations).
          navigate("/my-research");
          return;
        }
        if (k === "w") {
          e.preventDefault();
          navigate("/wrestle");
          return;
        }
        if (k === "n") {
          e.preventDefault();
          navigate("/notebooks");
          return;
        }
        if (k === "r") {
          e.preventDefault();
          // Built-in "go home" — ALSO fires Research product activation so a
          // hotkey is interchangeable with clicking the Research product.
          navigate("/");
          emitProductActivate({
            productId: "research",
            route: "/",
            source: "hotkey",
          });
          return;
        }
        // SPR-08: product / sub-action / custom chords on the `g` prefix.
        if (resolveExtended(`g ${k}`)) {
          e.preventDefault();
          return;
        }
      }
      // chord didn't resolve; fall through to normal handling
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

    // Single-letter chord starters (only if no modifier).
    if (!e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) {
      const k = e.key.toLowerCase();
      if (k === "g") {
        const timer = setTimeout(clearChord, CHORD_WINDOW_MS);
        pendingChord = { key: "g", timer };
        return;
      }
      // SPR-08: single-key CUSTOM bindings (e.g. the user assigned plain
      // "j" to an investigation). Resolved only against the custom map —
      // never built-ins or chord starters — so it can't shadow `g` or any
      // built-in. `resolveExtended` checks product/sub-action first, but
      // those are all `g`-chords, so a single key only ever hits custom.
      if (k.length === 1 && resolveExtended(k)) {
        e.preventDefault();
        return;
      }
    }
  }

  window.addEventListener("keydown", handler);
  return () => {
    window.removeEventListener("keydown", handler);
    clearChord();
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
