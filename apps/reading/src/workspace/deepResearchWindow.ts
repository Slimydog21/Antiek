/**
 * deepResearchWindow — handoff from Python floating_session window_compose.
 *
 * The pure substrate (`substrate/floating_session/window_compose.py`) builds
 * WindowOpenDescriptor values that match this contract:
 *
 *   kind: "deep_research_session"
 *   payload: {
 *     session_id, spawn_id, investigation_id, parent_asset_id,
 *     selection_text, status, view_format: "html",
 *     model_id?, region_id?, goal?
 *   }
 *   opts: { id: "wdr_<session_id>", title, mode: "floating" | "full" }
 *
 * This module applies those descriptors through the real windowsStore without
 * reimplementing z-order or MAX_WINDOWS. Browser e2e is non-gating; unit
 * coverage lives on the Python composition side + windowsStore tests.
 */

import { isWindowEligible, openWindow } from "../components/windows/openWindow";
import { useWindows } from "./windowsStore";
import type { OpenWindowOptions, WindowMode } from "./windowsStore";

/** Must match substrate.floating_session.window_compose.DEEP_RESEARCH_WINDOW_KIND */
export const DEEP_RESEARCH_WINDOW_KIND = "deep_research_session";

export type DeepResearchSessionPayload = {
  session_id: string;
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  selection_text: string;
  status: string;
  view_format: "html";
  model_id?: string;
  region_id?: string;
  goal?: string;
};

export type DeepResearchWindowDescriptor = {
  kind: typeof DEEP_RESEARCH_WINDOW_KIND;
  mode: WindowMode;
  title: string;
  payload: DeepResearchSessionPayload;
  id: string;
  session_id: string;
  parent_asset_id: string;
  spawn_id: string;
};

/** Stable window id — mirrors Python window_id_for_session. */
export function windowIdForSession(sessionId: string): string {
  const sid = sessionId.trim();
  if (!sid) throw new Error("session_id is required");
  return `wdr_${sid}`;
}

/**
 * Open (or focus) a deep-research session window via the real openWindow path
 * (registry-eligible kind → windowsStore). Call from UI when a highlight
 * session is ready; payload must match the Python composition handoff shape.
 */
export function openDeepResearchWindow(
  descriptor: DeepResearchWindowDescriptor,
): string {
  if (descriptor.kind !== DEEP_RESEARCH_WINDOW_KIND) {
    throw new Error(`expected kind ${DEEP_RESEARCH_WINDOW_KIND}, got ${descriptor.kind}`);
  }
  if (!isWindowEligible(DEEP_RESEARCH_WINDOW_KIND)) {
    throw new Error(
      `kind ${DEEP_RESEARCH_WINDOW_KIND} is not registered in WINDOW_PAGES`,
    );
  }
  const opts: OpenWindowOptions = {
    id: descriptor.id || windowIdForSession(descriptor.session_id),
    title: descriptor.title,
    mode: descriptor.mode,
  };
  // openWindow applies registry title default then opts; stable id focuses.
  return openWindow(
    DEEP_RESEARCH_WINDOW_KIND,
    descriptor.payload as unknown as Record<string, unknown>,
    opts,
  );
}

/** Map session floating⇄full onto windowsStore expand/restore. */
export function syncDeepResearchWindowMode(
  sessionId: string,
  mode: WindowMode,
): void {
  const id = windowIdForSession(sessionId);
  const store = useWindows.getState();
  const win = store.windows[id];
  if (!win) return;
  if (mode === "full") store.expand(id);
  else store.restore(id);
}
