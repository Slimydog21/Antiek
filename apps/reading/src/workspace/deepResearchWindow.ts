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
 *     model_id?, region_id?, goal?, research_tier?
 *   }
 *   opts: { id: "wdr_<session_id>", title, mode: "floating" | "full" }
 *
 * This module applies those descriptors through the real windowsStore without
 * reimplementing z-order or MAX_WINDOWS. Browser e2e is non-gating; unit
 * coverage lives on the Python composition side + windowsStore tests.
 */

import { isWindowEligible, openWindow } from "../components/windows/openWindow";
import {
  listEngagementSessions,
  updateEngagementSessionView,
} from "../api/engagement";
import { useWindows } from "./windowsStore";
import type { OpenWindowOptions, WindowMode } from "./windowsStore";

/** Must match substrate.floating_session.window_compose.DEEP_RESEARCH_WINDOW_KIND */
export const DEEP_RESEARCH_WINDOW_KIND = "deep_research_session";

export type DeepResearchSessionPayload = {
  owner_id: string;
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
  /** Residual (jk): closed research tier recorded on session open. */
  research_tier?: "fast" | "deep" | "wrestle" | string;
  /**
   * Residual (afx): highlight → DR window path honesty (parity FloatMenu afw).
   * Always true for openDeepResearchFromHighlight product entry.
   */
  seamless_highlight_dr?: boolean;
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

/** Remove private research chrome as soon as the authenticated owner changes. */
export function reconcileDeepResearchWindowsForOwner(ownerId: string | null): void {
  const expected = (ownerId || "").trim();
  const store = useWindows.getState();
  for (const window of Object.values(store.windows)) {
    if (window.kind !== DEEP_RESEARCH_WINDOW_KIND) continue;
    if (!expected || String(window.payload.owner_id || "").trim() !== expected) {
      store.close(window.id);
    }
  }
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

/** Persist mode authority first, then mirror the accepted mode into window chrome. */
export async function syncDeepResearchWindowModeDurably(
  sessionId: string,
  mode: WindowMode,
  expectedMode: WindowMode,
): Promise<void> {
  const accepted = await updateEngagementSessionView({
    session_id: sessionId,
    mode,
    expected_mode: expectedMode,
  });
  syncDeepResearchWindowMode(
    accepted.session_id,
    accepted.view_mode === "full" ? "full" : "floating",
  );
}

/** Reopen the authenticated owner's durable sessions for one logical asset. */
export async function reopenDeepResearchWindowsForAsset(
  parentAssetId: string,
): Promise<string[]> {
  const response = await listEngagementSessions(parentAssetId, false);
  reconcileDeepResearchWindowsForOwner(response.owner_id);
  return response.sessions.map((session) =>
    openDeepResearchFromHighlight({
      owner_id: session.owner_id,
      asset_id: session.parent_asset_id,
      selection_text: session.selection_text,
      session_id: session.session_id,
      spawn_id: session.spawn_id,
      investigation_id: session.investigation_id,
      status: session.status,
      goal: session.goal,
      model_id: session.model_id ?? undefined,
      mode: session.view_mode === "full" ? "full" : "floating",
      research_tier: session.research_tier ?? undefined,
    }),
  );
}

/**
 * Product path input: a highlight plus session identity from the substrate
 * (Python open_from_highlight / open_deep_research_from_highlight, or API).
 * Does not re-launch research; composes existing openDeepResearchWindow.
 */
export type HighlightDeepResearchInput = {
  owner_id: string;
  asset_id: string;
  selection_text: string;
  session_id: string;
  spawn_id: string;
  investigation_id: string;
  region_id?: string;
  model_id?: string;
  status?: string;
  goal?: string;
  mode?: WindowMode;
  title?: string;
  /** Residual (jk): research tier from session open (fast|deep|wrestle). */
  research_tier?: "fast" | "deep" | "wrestle" | string;
};

/**
 * Product entry: open/focus the deep-research session window for a highlight.
 * Caller supplies reserved session ids (substrate); this only opens the host
 * window with the composition payload (HTML-first).
 * Residual (afx): payload.seamless_highlight_dr always true (highlight entry).
 */
export function openDeepResearchFromHighlight(
  input: HighlightDeepResearchInput,
): string {
  const selection = (input.selection_text || "").trim();
  if (!selection) throw new Error("selection_text is required");
  if (!input.asset_id?.trim()) throw new Error("asset_id is required");
  if (!input.session_id?.trim()) throw new Error("session_id is required");
  if (!input.spawn_id?.trim()) throw new Error("spawn_id is required");

  const short =
    selection.length <= 48 ? selection : `${selection.slice(0, 45)}...`;
  const descriptor: DeepResearchWindowDescriptor = {
    kind: DEEP_RESEARCH_WINDOW_KIND,
    mode: input.mode ?? "floating",
    title: input.title ?? `Deep research: ${short}`,
    id: windowIdForSession(input.session_id),
    session_id: input.session_id,
    parent_asset_id: input.asset_id,
    spawn_id: input.spawn_id,
    payload: {
      owner_id: input.owner_id,
      session_id: input.session_id,
      spawn_id: input.spawn_id,
      investigation_id: input.investigation_id,
      parent_asset_id: input.asset_id,
      selection_text: selection,
      status: input.status ?? "reserved",
      view_format: "html",
      // Residual (afx): highlight → DR path honesty (parity FloatMenu afw).
      seamless_highlight_dr: true,
      ...(input.model_id ? { model_id: input.model_id } : {}),
      ...(input.region_id ? { region_id: input.region_id } : {}),
      ...(input.goal ? { goal: input.goal } : {}),
      ...(input.research_tier
        ? { research_tier: input.research_tier }
        : {}),
    },
  };
  return openDeepResearchWindow(descriptor);
}
