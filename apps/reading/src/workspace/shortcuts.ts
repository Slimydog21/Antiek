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

const CHORD_WINDOW_MS = 800;

/** Event names emitted/consumed via window.dispatchEvent. Components
 *  that own their own toggle state listen for these instead of being
 *  driven directly by the workspace store. */
export const SHORTCUT_EVENTS = {
  PALETTE_TOGGLE: "antiek:palette:toggle",
  AISIDECAR_TOGGLE: "antiek:aisidecar:toggle",
} as const;

function isTextEditing(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (t.isContentEditable) return true;
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

  function handler(e: KeyboardEvent) {
    if (isTextEditing(e.target)) return;

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
          navigate("/");
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
    if (!e.metaKey && !e.ctrlKey && !e.altKey) {
      const k = e.key.toLowerCase();
      if (k === "g") {
        const timer = setTimeout(clearChord, CHORD_WINDOW_MS);
        pendingChord = { key: "g", timer };
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
