import { useWorkspace } from "./WorkspaceStore";

/**
 * The companion pane's visibility rule, kept apart from companionStore so
 * the keyboard dispatcher (entry chunk) can ask it without loading the
 * store, which ships with the lazy pane.
 */

/** The docked-preset mount: the companion is this right-dock panel. */
export const COMPANION_PANEL_ID = "companion:main";

/** Is the companion on screen? The key handlers' shared visibility rule:
 *  they no-op honestly where there is no pane (never a dead key in a
 *  surface without it). */
export function companionVisible(): boolean {
  const ws = useWorkspace.getState();
  if (ws.layoutPreset === "omarchy-inset") return true;
  return Boolean(ws.panels[COMPANION_PANEL_ID]);
}
